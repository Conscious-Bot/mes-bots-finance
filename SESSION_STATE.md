# Session State — mes-bots-finance

**Last updated**: Day 15 close, 2026-05-21 21:17

## Mode actuel
**High Standard / Solidification** — Path 5/6 strategic target.
TG canonical rollout active. NO new features.

## Bot state
- PID 2608 alive, polling, scheduler 27 crons
- Tests: 335 passed
- ruff + mypy clean on touched files
- 313 tickers universe (audit pending)

## Day 15 highlights (9 ships)
1. Phase B /portfolio
2. Phase D /thesis dispatcher (5-helper, 9 sub-actions)
3. 21-theses data fix
4. Substack 2 editorial passes
5. TG canonical spec doc
6. /brief canonical
7. KPI #2 timer fix
8. /recent_8k canonical
9. /asymmetry portfolio canonical + currency fix

## Day 16 priorities (empirical, surfaced by canonical)
1. COHR 🔴 STOP NEAR resolution
2. ALAB ratio 0.40 + 25.6% P&L anomaly
3. NVDA 4 officer departures 105d + 2 unresolved decisions
4. 4 orphans c1 J+30 (AMD/GOOGL/SAF.PA/TSLA)
5. Concentration policy AI_compute 67%

## Entry point Day 16
1. cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate
2. ps auxww | grep "bot.main" | grep -v grep   # L39: NOT pgrep -f python.*
3. Read HANDOFF.md Day 15 final close
4. Action Tier S priority order above

## Documents canoniques (entry order)
1. HANDOFF.md (Day 15 final close section = primary entry)
2. CONVENTIONS.md L37+L38+L39
3. TODO.md Day 15 closure
4. PHILOSOPHY.md High Standard
5. docs/conventions/telegram_output_canonical.md (TG spec)

## Carry-forward (not urgent)
- TG canonical P1: /portfolio, /positions, /digest
- shared/display.py canonical refactor (~5-10h)
- Universe pruning audit (313 vs 178)
- Substack SK hynix fact-check
- Canonical spec doc amendment ("color = external signal only")


## 2026-05-23 — Brier root-cause fix + dashboard hardening (tag day15-brier-dashboard, commit bbe74e4)

### Shipped (live, gates verts, committe + tagge)
- Resolution blindee: dropna `.T` dans shared/prices.py::get_current_price (tickers Tokyo renvoyaient nan) + garde nan sans import (px != px) dans intelligence/learning.py::resolve_due_predictions. Empeche nan final_price / faux "neutral" dans le batch. Bot redemarre propre, live sur cron resolve 9h.
- BRIER CAUSE-RACINE: probability_at_creation n'etait qu'un snapshot de la credibilite source (143/152 = 0.5) -> erreur de categorie (confiance source != P(cet appel correct)) -> Brier vide-mais-vert. Remplace par shared/math_helpers.py::estimate_probability(score, cred, signal_type, impact_magnitude) dans [0.50, 0.72], cable dans shared/storage.py::insert_prediction (SELECT elargi a score/type/impact). 4 tests Hypothesis. Cadre honnete: PRIOR APPRENABLE, pas verite calibree -- son job est de rendre le Brier informatif/iterable. Effet sur predictions FUTURES uniquement (id >= 158).
- Premier test du dashboard: tests/test_render_smoke.py -- render() end-to-end (couvre les 8 sections, marqueurs nav + payloads HEIMDALL). ~30 patches sans test -> filet pose.
- Re-tag narratives: AMD/ALAB/COHR -> AI_COMPUTE_2026, SAF.PA -> EU_DEFENSE_2026, GOOGL/TSLA -> MAG7_2026 (nouvelle categorie). 2 bacs admin morts. Reversible (edit notes). Effet de bord exact: AI Compute grossit -> Concentration EXCESSIVE 80%.

### Etat track record (HONNETE)
- ~0 exploitable. Les 151 ouvertes (dont cluster de 40 du 10 juin) gardent prob = 0.5 -> Brier vide-mais-VERT. NE PAS PUBLIER.
- Vraie courbe a partir des id >= 158, exploitable ~fin juin.

### Git / hygiene
- Backlog non committe rattrape (serve.py + snapshot.py jamais committes, render.py patche multi-sessions, 33 .bak en guise de VCS). Checkpoint unique, reprendre l'atomique ensuite.
- Secrets HORS historique: git ls-files credentials.json token.json vide -> safe pour push GitHub.
- 0 .bak restant, arbre propre.

### Watch / next
- Verif prob prod: predictions id >= 158 avec prob != 0.5 = integration confirmee.
- ~27 mai: 1eres resolutions, verifier final_price sains.
- Vue calibration (surface produit Path 6): batir quand >= 10 predictions prob-differenciee resolues (~fin juin). Reliability diagram + Brier-over-time + ledger. Trancher la: neutral exclu vs binaire-0.5.
- Concentration EXCESSIVE 80% AI Compute (> 30% cap, 6 lignes > 5%): decision politique en attente.
- Logo: parke candidat A (heaume-onde), a integrer dans render.py .logo svg quand choisi.
- Classifieur 8-K met tout Item 5.02 = HIGH (bruit signal->prediction): gele observation.
