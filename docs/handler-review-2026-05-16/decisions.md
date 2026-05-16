# Handler Review 2026-05-16 — Olivier decisions

**Context**: empirical UX audit. 73 handlers actuels. User feedback: "beaucoup affichent des textes incomprehensibles et rebarbatifs".

**Method**: bloc par bloc, decision K/K+/U/D, logged here append-only.

**Decision codes**:
- K = keep as-is (used or wanted, output OK)
- K+ = keep + expand priority
- U = unify with cousin handler(s)
- D = delete (never used or never understood)

**Output**: Sprint 1.2 input. Execution post-J+28 OR earlier if UX gap blocks daily ritual.

---

## Bloc 1 — anti_erosion

| Cmd | Decision | Notes |
|---|---|---|
| /log_value | U | Fusionner dans /remarks |
| /log_friction | U | Fusionner dans /remarks |

**Unification target** `/remarks`:
- Single mental flow "capturer un truc"
- Sub-commands or flag: `/remarks value <text>` + `/remarks friction <text>`
- OR single `/remarks <text>` with auto-classify (lower priority design)
- Empirical usage justifying merge: 1 value entry + 0 friction entries in 4 days. Two handlers for ~zero usage = consolidation candidate.

## Bloc 4 — thesis_analyze

| Cmd | Decision | Notes |
|---|---|---|
| /analyze | K+ | OLIVIER FAVORITE. Scope expand priority for Sprint 1.2 (TBD what expand means). |
| /analyze_debate | K | 0 calls audit but high-value differentiator (Opus multi-round = unique vs ChatGPT). Commit: test empirically 1x this week (Kioxia/MHI/STVN candidates available). |
| /debate_replay | D | Replay stored debate. Never used (zero debates run). Pure dead code candidate. |
| /risk_check | K | 0 calls but THE anti-FOMO gate per PHILOSOPHY. Habit-formation: must invoke before any /trade buy. |
| /thesis_premortem | K | 0 calls + 0 theses with pre_mortem populated. KEPT because PHILOSOPHY core: "le bot force discipline pré-commit". Suppression = contradiction doc vs runtime. Habit-formation needed. |

**Sprint 1.2 follow-ups**:
- /analyze scope expand: define what "expand" means (length? structure? mid-thesis revisit option?)
- /risk_check + /thesis_premortem: track usage post-cleanup. If still 0 calls at J+30 (post-J+28), reopen delete decision.
- /analyze_debate: empirical test 1x cette semaine sur candidat thesis-queue (Kioxia/MHI/STVN).

## Bloc 5 — Features Day 4-5 (K provisoire, UX-review P0 avant Sprint 1.2)

| Cmd | Decision | Notes |
|---|---|---|
| /find | K | Cross-domain ticker dump. UX-review P0. |
| /journal_audit | K | KPI #5 silent tickers visibility. UX-review P0. |
| /signal_drilldown | K | Per-ticker signals. UX-review P0. |
| /thesis_health | K | Active theses health. UX-review P0. |
| /bias_pattern | K | Aggregate biases. UX-review P0. |

**Flag**: K provisoire jusqu'à test empirique Telegram. Si crash/illisible -> friction.md entry + revue après J+30 (post-J+28).

## Bloc 6 — Signaux + EDGAR + Macro + Journal + Biais + Sources/Tiers

### E. SIGNAUX
| Cmd | Decision | Notes |
|---|---|---|
| /digest | (TBD) | non décidé ce bloc |
| /signals_by_type | D | Filter par type peu utile vs /digest synthèse. Catalyst/data/narrative/opinion accessible via SQL si besoin. |
| /signal_drilldown | K (Bloc 5) | déjà acté |
| /echo_recent | (TBD) | non décidé ce bloc |
| /materiality | (TBD) | non décidé ce bloc |

### F. EDGAR / 8-K / INSIDER
| Cmd | Decision | Notes |
|---|---|---|
| /insiders | (TBD - target U) | unification target pour la famille |
| /insider_cluster | U | -> /insiders cluster TICKER |
| /insider_buy_cluster | (TBD - target U) | -> /insiders buy_cluster (probable) |
| /insider_buy_cluster_stats | D | empirical alpha calcul peu utilisé. Si valeur, requêtable SQL direct. |
| /insider_digest | (TBD - target U) | -> /insiders digest probable |
| /recent_8k | (TBD - rename /8k) | base de la famille 8K, renommer /8k |
| /eight_k_history | U | -> /8k history TICKER |

### G. MACRO / RÉGIME
| Cmd | Decision | Notes |
|---|---|---|
| /regime | (TBD) | non décidé |
| /macro | (TBD) | non décidé |
| /credit | (TBD) | non décidé |
| /calendar | (TBD) | non décidé |
| /calendar_refresh | D | Si /calendar marche bien, refresh = cron only (job déjà actif 5h). |

### I. JOURNAL DÉCISIONS
| Cmd | Decision | Notes |
|---|---|---|
| /journal | K (action) | /journal TICKER type conviction reasoning -> log décision |
| /journal_review | U | -> /journal review |
| /journal_unresolved | U | -> /journal unresolved |
| /journal_tag | U | -> /journal tag DECISION_ID newtag |
| /journal_audit | K (Bloc 5) | reste séparé (autre dimension: silent tickers vs decisions logguées) |
| /history | (TBD) | non décidé - probable redondant avec /signal_drilldown |

**Unification target** `/journal`:
- `/journal TICKER type conviction reasoning` -> log new decision (action verb implicit)
- `/journal review` -> stats + recent decisions
- `/journal unresolved` -> pending J+30/J+90
- `/journal tag DECISION_ID tag` -> override mistake_tag

### J. BIAIS COGNITIFS
| Cmd | Decision | Notes |
|---|---|---|
| /bias_review | D | Absorbé par /bias_pattern strictement plus riche (taxonomy + by-ticker + windows). |
| /bias_pattern | K (Bloc 5) | déjà acté |

### L. SOURCES / TIERS
| Cmd | Decision | Notes |
|---|---|---|
| /sources_health | (TBD - target U) | unification target /sources |
| /sources_brier | (TBD - target U) | -> /sources brier |
| /sources_half_life | D | Half-life concept peu utilisé en pratique. Backend reste si besoin. |
| /tiers | D handler | Backend reste actif (table sources.tier). Accès via /sources brier (input du tier). |
| /tiers_watch | D | Liste niche, accessible SQL direct si besoin. |
| /promote | D | Admin manual override. Système empirique auto-promote suffit. |

## Bloc 7 — THESES (catégorie C, 9 handlers)

Unification totale famille /thesis avec sous-commandes.

| Cmd actuel | Decision | Cmd cible |
|---|---|---|
| /thesis_add | U | /thesis add [template] |
| /thesis_list | U | /thesis list |
| /thesis_set | U | /thesis set TICKER field value |
| /thesis_note | U | /thesis note ID texte |
| /thesis_revisit | U | /thesis revisit |
| /thesis_health | U (override Bloc 5 K) | /thesis health |
| /thesis_premortem | U (override Bloc 4 K) | /thesis premortem ID |
| /exit | U | /thesis exit TICKER [price] |
| /exit_force | U | /thesis exit TICKER --force raison |

**Surface reduction**: 9 -> 1 command (-8 handlers).

## Confirmation rename /signal_drilldown
| Cmd actuel | Decision | Cmd cible |
|---|---|---|
| /signal_drilldown | K + rename | /signal_30j |

Question latente: pluriel /signaux_30j vs singulier /signal_30j ? User a écrit /signal_30j (singulier). Logged tel quel.

## Bloc 8 — Prédictions / Calibration (catégorie K, 5 handlers)

| Cmd actuel | Decision | Cmd cible |
|---|---|---|
| /predictions | K + sous-commande | /predictions (TL;DR list) |
| /resolve_now | U | /predictions resolve (manual trigger) |
| /credibility | U dans /sources | /sources credibility |
| /feedback | U dans /sources | /sources feedback ID up\|down |
| /asymmetry | U dans /thesis | /thesis asymmetry TICKER |

**Surface reduction**: 5 -> 1 (les autres absorbés dans /sources et /thesis).

**/sources famille consolidée Bloc 6 + 8**:
- /sources health     (was /sources_health)
- /sources brier      (was /sources_brier)
- /sources credibility (was /credibility) ← absorbé Bloc 8
- /sources feedback ID up|down (was /feedback) ← absorbé Bloc 8

## Bloc 9 — Status / Santé (catégorie A, 2 handlers)

| Cmd actuel | Decision | Cmd cible |
|---|---|---|
| /ping | K standalone | /ping (5 lignes ultra-rapide: capital, drawdown, theses, paper_only) |
| /health | U dans /bot_data (Bloc 2) | /bot_data health |

Rationale: 2 niveaux différents — /ping = pulse rapide, /bot_data = full status.

## Bloc 10 — Crypto (catégorie H, 2 handlers)

| Cmd actuel | Decision | Cmd cible |
|---|---|---|
| /crypto | K standalone | /crypto (anti-FOMO discipline, unique fonction PHILOSOPHY) |
| /price_check | U dans /thesis | /thesis check_triggers (cohérent famille /thesis Bloc 7) |

## Bloc 11 — Admin / Utils (catégorie N, 4 restants)

| Cmd actuel | Decision | Cmd cible |
|---|---|---|
| /help | K | /help (à reformer post-renaming global, reflète la nouvelle structure) |
| /find | K + rename TBD | suggestion /dump TICKER ou /tout TICKER (user décide) |
| /orphan_tickers | K+ FAVORI (expand scope) + rename TBD | suggestion /orphelins ou /non_suivis (user décide) |
| /override | U dans /thesis | /thesis override TICKER level reason |

## Bloc 9 — Status / Santé (catégorie A, 2 handlers)

| Cmd actuel | Decision | Cmd cible |
|---|---|---|
| /ping | K standalone | /ping (5 lignes ultra-rapide: capital, drawdown, theses, paper_only) |
| /health | U dans /bot_data (Bloc 2) | /bot_data health |

Rationale: 2 niveaux différents — /ping = pulse rapide, /bot_data = full status.

## Bloc 10 — Crypto (catégorie H, 2 handlers)

| Cmd actuel | Decision | Cmd cible |
|---|---|---|
| /crypto | K standalone | /crypto (anti-FOMO discipline, unique fonction PHILOSOPHY) |
| /price_check | U dans /thesis | /thesis check_triggers (cohérent famille /thesis Bloc 7) |

## Bloc 11 — Admin / Utils (catégorie N, 4 restants)

| Cmd actuel | Decision | Cmd cible |
|---|---|---|
| /help | K | /help (à reformer post-renaming global, reflète la nouvelle structure) |
| /find | K + rename TBD | suggestion /dump TICKER ou /tout TICKER (user décide) |
| /orphan_tickers | K+ FAVORI (expand scope) + rename TBD | suggestion /orphelins ou /non_suivis (user décide) |
| /override | U dans /thesis | /thesis override TICKER level reason |

## Renames finaux (Bloc 12)

| Cible Bloc 6-11 | Renamed final |
|---|---|
| /find | /find (keep) |
| /orphan_tickers | /orphan_tickers (keep) |
| /signal_30j (was /signal_drilldown) | /signal |
| /echo_recent | /echo |
| /journal_audit | /journal audit (sub-command, cohérent famille) |
| /bias_pattern | /biases |
| /log_value + /log_friction | /remarks |
| /recent_8k + /eight_k_history | /8k |

## /journal family — final structure
/journal TICKER type conviction reasoning    → log new decision
/journal review                              → stats + recent decisions
/journal unresolved                          → pending J+30/J+90 resolution
/journal tag DECISION_ID newtag              → override mistake_tag
/journal audit                               → silent tickers (was /journal_audit)

5 sub-commands under single family.

## Final surface — 25 top-level commands

1.  /ping              status financier ultra-rapide
2.  /bot_data          [health|costs] (was 4 handlers)
3.  /handler_stats     Pareto usage
4.  /portfolio         [TICKER|sectors|narratives|drift|TICKER history] (was 8)
5.  /trade             buy|sell TICKER QTY (was 2)
6.  /thesis            add|list|set|note|revisit|health|premortem|exit|asymmetry|check_triggers|override (was 12)
7.  /analyze TICKER    fiche Opus (K+)
8.  /analyze_debate    multi-round Opus (séparé K)
9.  /digest [hours]    synthèse + materiality (was 2)
10. /signal TICKER     drill 1 ticker (was /signal_drilldown)
11. /echo              clusters multi-source (was /echo_recent)
12. /insiders          [TICKER|cluster|buy_cluster|digest] (was 5)
13. /8k                [TICKER|history TICKER] (was 2)
14. /macro             [regime|credit|calendar] (was 4)
15. /journal           [TICKER...|review|unresolved|tag|audit] (was 6)
16. /history TICKER    vue 360 cross-table
17. /biases            cognitive bias aggregate (was /bias_pattern)
18. /predictions       [resolve] (was 2)
19. /sources           [health|brier|credibility|feedback] (was 4)
20. /crypto            cycle indicators
21. /help              categorized list
22. /find TICKER       cross-domain dump
23. /orphan_tickers    hot external (favori ❤️)
24. /remarks           [value|friction] (was /log_value + /log_friction)
25. /debate_replay     ID (Bloc 4 D → check si encore voulu)

WAIT: /debate_replay was D in Bloc 4. Final surface should be 24 commands.

## Final count

- Before: 73 handlers
- After: 24 top-level commands (with sub-commands)
- Reduction: -49 handlers / 73 = **-67% surface**

## Audit done — Action items

1. **Sprint 1.2 execution plan**: implement renames + sub-command routing per family
2. **bot/handlers/ refactor**: groupe modules par famille final (currently 16 modules, target ~15 aligned with families)
3. **/help rewrite**: reflect new structure, group by category
4. **friction.md migration**: 5 items captured 14 mai still valid post-audit
5. **Pre-execution**: empirical test in Telegram of 5-7 daily ritual commands BEFORE Sprint 1.2 ship, per user feedback "textes incomprehensibles"

## Trigger Sprint 1.2

- Post-J+28 (2026-06-10) per observation mode discipline
- OR earlier if daily ritual UX blocks user (current state: handlers exist but illisibles)
