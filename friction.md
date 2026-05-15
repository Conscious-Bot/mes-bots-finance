# FRICTION LOG — mes-bots-finance

Track every moment where the bot frustrated, missed, or felt clunky.
One line per entry. Don't fix on the spot — accumulate, prioritize later.

Format suggestion: `YYYY-MM-DD | context | what was missing/annoying`

Captures the wedge-feature signal for Phase 2 decision (Decision Journal vs Behavioral Graph).

---

## 2026-05

2026-05-13 15:56 | l'assistant a trop souvent insisté sur son envie que j'arrete ou fasse une pause, cela me deplait bcp, ensuite je pense que l'on a encore trop de handlers , je pense que jai besoin de le familiariser avec les outils, renommer et mieux comprendre les features, jaimerais enregistrer mes propres positions actuelles au bot pour voir en reel ce que son utilisation me fournirait.

## 2026-05-14 — Day 3 close friction batch (6 items, post-CI green)

### /brief specific
- `/brief` feels less interesting than `/digest`. Relative preference signal — when both available, user gravitates to digest.
- `/brief` truncates newsletter summaries mid-sentence. Concrete UX flaw, breaks readability.
- Unclear if `/brief` captures real value. Fundamental purpose question, not just polish.

### /brief vs /digest relationship
- `/brief` and `/digest` should probably be reviewed and possibly consolidated together. Two morning rituals competing for same attention slot.

### Handler metrics proliferation
- Too many handlers expose metrics/numbers in isolation. Could be unified into 1 handler + explanations. User does not understand all of them himself — they are dumped without context.

### Pipeline-wide signal
- Whole pipeline (ingestion → sources → interpretation → summary) could be improved. Not a single bug, a coherence question.

### Best features (expansion candidates)
- `/analyze` and `/orphan_ticker` are the most achieved features. Want to expand reach and catalog on these specifically.

### Disposition (deferred per observation window + Sprint 1.1 baseline + fatigue)
- Items 1-4: input for future `/brief` and `/digest` redesign sprint, post Sprint 1.1 close.
- Item 5: handler metrics consolidation sprint, separate scope.
- Item 6: pipeline-wide review, Phase 3 scope (~juillet 2026 earliest).
- Item 7: expansion candidates for `/analyze` and `/orphan_ticker`, post-J+28 batch resolution.
2026-05-15 04:31 | it seems that i did the digest feature and nothing came when i actually belive my mail is loaded on new newsletters with interesting content
2026-05-15 05:34 | comment est ce possible qu'il n y est aucun signal pertinent sur les dernières 24h

## 2026-05-15 — empirical validation of items 4, 5, 6

User reported /digest "bizarre — aucun signal pertinent ces dernieres 24h" despite 16 signals ingested in window.

Investigation revealed pipeline coherence gap: `signals.score` column deprecated since 2026-05-13 (materiality_v2 introduction Day 2 marathon), but /digest still filters on it. 31 of 92 signals have NULL score, all from May 13 onward. /digest filter `COALESCE(s.score, 0) >= 3` excludes all NULL scores → empty digest.

This empirically validates friction items 4 (/brief + /digest review together), 5 (metrics handlers without explanation), and 6 (whole pipeline coherence). User's intuition was correct: the friction was a real architecture gap, not just UX preference.

Full analysis: `docs/pipeline-coherence-audit.md`. Disposition: Sprint 1.2 critical input, no fix during observation window.
