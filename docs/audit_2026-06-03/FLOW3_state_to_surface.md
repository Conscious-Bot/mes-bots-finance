# Flow 3 — State → Surface

**Trace** : DB / state files → 3 surfaces de sortie (dashboard HTML, Telegram commands, Telegram pushes) → user.

**Surfaces couvertes** :
1. Dashboard HTML (rendered + served local)
2. Telegram on-demand (commands /brief, /health, /grade, /pos, /chat, etc.)
3. Telegram push (morning brief, alerts, dead-man's-switch, llm_status transition)

## Surface inventory

| Surface | Trigger | Backend | Output |
|---|---|---|---|
| dashboard.html | timer (PRESAGE_REFRESH=60s) + browser poll Last-Modified 1s | `dashboard/render.py:render()` 5522 LOC | static HTML written to disk |
| `/brief`, `/health`, `/pos`, etc. | Telegram getUpdates (long-poll) | `bot/handlers/*.py` (~35 handlers) | Telegram sendMessage |
| Morning brief push | APScheduler cron `morning_chain` | `intelligence/morning_brief.py:build_brief()` 562 LOC | Telegram sendMessage |
| Bias alerts, kill_criteria, etc. | event-driven (post-resolution, post-position-change) | bot/handlers + intelligence/bias_events | Telegram + DB writes |
| Resilience badge + restitution markers | `dashboard/render._llm_status_badge` + `dashboard/restitution.py` | shared/llm get_llm_status + bot_state.json | rendered chip bottom-right + marker strings in chat/analyze |

## Trace end-to-end (dashboard)

```
dashboard/serve.py:_regen_loop() (line 164)
  loops every INTERVAL=60s :
  → dashboard.render.render() (render.py:4912)
    → reads positions / theses / signals / predictions from DB via _q()
    → reads bot_state.json via shared.storage.load_state()
    → reads price cache (_PX_CACHE) with TTL 30min
    → computes all panels (positions, sizing, sectors, KPIs, theses, signals, etc.)
    → writes dashboard/dashboard.html
  → file mtime updated → browser polls Last-Modified → reloads
```

## Trace end-to-end (Telegram on-demand)

```
bot.main runs polling getUpdates loop (python-telegram-bot)
  → user sends /grade NVDA
  → handler bot/handlers/misc.py:cmd_grade (line 138)
    → calls intelligence.portfolio_grade.compute (or similar)
    → may call LLM (analyze, synthesis, why_matters)
      → if LLM down : LLMUnavailableError → restitution marker via
        dashboard/restitution.format_llm_unavailable_marker
    → notify.send_text or update.message.reply_text
```

## Plugs solidity

| Plug | Status | Notes |
|---|---|---|
| `serve.py` regen loop | **solide** : try/except around render call (line 172), erreur loggée mais loop continue | resilience to single render crash. Mais : SI render crash silencieusement sur un sous-panel et tronque le HTML, browser charge un HTML cassé. Pas de validation post-write. |
| `_q()` DB access (render.py:210) | basic try/except, retourne dict d'erreur ou liste vide | propre |
| `_cached_price_eur` / `_cached_price_native` | TTL 30min cache + fallback None | yfinance ban-safe, mais cache cold start = 30min de prix manquants |
| `notify.send_text` (Telegram sendMessage) | network call, sync within async context | si Telegram down, le call fail silently (catch global) — user voit rien. Pattern 1 (outbound link dead). #100 covers post-J-day. |
| getUpdates polling (inbound) | gère son propre retry / reconnection | Pattern 1 : si thread polling die, process alive mais commands ignored. #100 covers. |
| `bot_state.json` write (load_state/save_state) | atomic via `write_text` then read | OK pour single-writer (bot.main). Mais render.py et bot.main lisent tous deux le state — race possible si render.py lit mid-write. Improbable mais possible. **P3.** |
| `_llm_status_badge` lecture state | defensive try/except → "" si erreur | ✓ aucun marker faux affiché si state corrompu |

## Failure modes

| Surface | Failure | Détection | Récupération | Severity |
|---|---|---|---|---|
| dashboard regen | render() crash partial → HTML tronqué | check serve.log `regen FAILED` | next cycle 60s plus tard | **P2** — pas de validation HTML well-formed avant write. Si un cycle écrit un HTML cassé, browser affiche broken page jusqu'au cycle suivant. |
| serve.py thread death | regen_loop crash | non détecté (thread daemon, silent) | aucun | **P2** — same Pattern 1, mais sur le serve thread. Pas couvert par bot uptime monitor (serve = process différent). |
| serve.py port 8000 used | bind error | crash au startup | manual restart | **P3** — rare, occasional dev artifact |
| dashboard.html write fail | OSError disk full / permissions | error logged, regen loop continues | next cycle | **P3** |
| Telegram sendMessage 429 rate-limit | http error | catch dans notify, silent drop | **gap** : si push critique (alert) drop, jamais retry | **P2** — fragile pour les alerts critiques. healthchecks.io ping NE PASSE PAS par Telegram donc J-day est OK, mais alerts génériques peuvent dropper |
| Telegram sendMessage 401 (bot token revoked) | http error | crash | manuel | **P2** — same as 429 |
| getUpdates 409 (double-bot) | http error | bot crash, launchd restart | **infinite loop** : restart hits 409 again | **P1** silently captured dans #99 (cross-machine), local n'a pas ce cas |
| `restitution` marker affiché alors que LLM up (race condition) | none | next render | **P3** — temporaire de 1 regen cycle max |

## Coupling assessment (3 patterns)

| Pattern | Évaluation |
|---|---|
| **Pattern 1 (liveness ≠ functionality)** | Trois plugs vulnérables : (a) Telegram polling thread death silencieux, (b) Telegram sendMessage silent drop, (c) serve.py regen thread death. Tous couvert par #100 (heartbeat tests link). |
| **Pattern 2 (snapshot drift)** | dashboard.html EST un snapshot — exporté 60s. Si serve.py meurt à T0, l'HTML reste fixe avec des chiffres T0 sans badge "stale". Le browser le sait pas. **Sit-pour-eux Pattern 2 violation à fixer #101.** Le badge `as-of` est dans le contrat Fraicheur & Mouvement (#103) → P3. |
| **Pattern 3 (multi-path)** | dashboard, /brief Telegram, et morning brief Telegram calculent les MÊMES KPIs (Brier, predictions resolved 28d, alpha vs SOXX, etc.) avec **trois sites de query distincts**. Exact Pattern 3 → #102 couvre. |

## Resilience layer integration

| Item | Status |
|---|---|
| LLM badge bottom-right | ✓ live (`_llm_status_badge` in render.py, color-coded dot) |
| restitution markers dans chat.py | ✓ live (`format_llm_unavailable_marker` import) |
| restitution markers dans analyze.py | ✓ live |
| restitution markers dans morning_brief / autres handlers ? | **gap** : non vérifié exhaustivement. Si un handler appelle LLM sans catch LLMUnavailableError → crash propage → user voit "Erreur : LLMUnavailableError: credit_exhausted" en plain text non-encodé. **Trace needed.** |
| llm_status badge réagit au cost_cap_hard | ✓ via `_check_cost_cap` setting state |

## Duplicates dans ce flux

- **render.py est un mur 5522 LOC** : duplications internes likely (panneaux similaires copy-pasted). Détectable seulement par lecture diff. Capture déjà = #66 (refactor render.py → modules).
- **Same KPI computed in 3 places** : dashboard `_grade_panel`, Telegram `/health` `_kpi_compute_all`, morning brief KPI section. Pattern 3 → #102.
- **`from shared import storage` lazy import** apparaît ~20× dans render.py — anti-pattern mais nécessaire (cycle avoid). Acceptable.

## Dead code dans ce flux

- Plusieurs `_*_panel()` dans render.py — chaque panel est une fonction. Si un panel n'est plus appelé dans `render()` (line 4912), c'est dead. Trace nécessaire pour confirmer chacun. Pas un quick win.
- `_perf_dwm`, `_universe_status` apparaissent utilisés mais peuvent avoir des call sites limités. Vérification ponctuelle.

## Action items Flow 3

| Item | Priority | Disposition |
|---|---|---|
| Audit exhaustif handlers Telegram : catch LLMUnavailableError partout où LLM est appelé | **P1** | Sweep grep `from shared import llm` + check chaque handler. Si gap, ajouter marker. ~30min. Important avant J-day si on a un crash en chat pendant la review du Brier J-day. |
| serve.py regen_loop thread health monitoring | **P2** | Couvert par #100. |
| dashboard HTML well-formed validation post-write | **P2** | Petit (parse via lxml HEAD ?), améliore Pattern 2 detection |
| Telegram sendMessage retry on 429 | **P2** | Sans retry on perd des alerts. Wrap notify.send_text avec backoff. Petit. |
| render.py 5522 LOC duplications internes | P3 | #66 |
| 3 sites de query KPI | P3 | #102 |

**P1 ici** : sweep des handlers Telegram pour catch LLMUnavailableError. Pas exhaustivement vérifié. À faire avant J-day si possible (cheap).
