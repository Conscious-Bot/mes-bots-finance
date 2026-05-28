# VALUE_LOG — mes-bots-finance

Track concrete moments where the bot actually helped your decisions or thinking.
One line per entry. No structure required. Be honest — if a week is empty, that's data.

Format suggestion: `YYYY-MM-DD | command/event | what helped`

Anti-erosion mechanism for solo 12-month build. If this file is empty at J+30, that's a signal.

---

## 2026-05

2026-05-13 12:54 | premiere tentative le bot tourne bien jaime la lecture des tickers et leurs descriptions, aussi jaime beaucoup la feature orphan_ticker
2026-05-13 13:27 | le brief est trop succint les resumes ne sont pas clairs du tout
2026-05-14 02:47 | le slash digest est bien meilleur et fais un meilleur resume que le / brief il faut revoir ca pour peut etre revoir le nombre de ligne, le style d'ecriture et peut etre reunir les 2 en 1

2026-05-14 21:45 | Day 3 close — Tier 2 ship validation empirique
Tier 2 bot_health_check.sh (commit 26678e9, déployé Day 3 evening) a détecté
l incident APScheduler hang dans les 24h de son déploiement. Sans cette feature
l incident serait resté invisible jusqu au prochain check manuel (probablement
demain matin). Detector value validée empiriquement.

Postmortem propre + CONVENTIONS §19 + failure_modes #6 documentés (commit
a34f705). 40+ commits Day 3, CI triple GREEN, Sprint 1.1 pre-flight validé
8/9 gates (mypy cosmetic à fixer Friday).

Friction batch (6 items: /brief, /digest, metrics proliferation, pipeline
coherence, /analyze + /orphan_ticker comme north stars) capturée raw dans
friction.md (commit 3a3ae2f) au lieu d être supprimée par fix immédiat —
preserves wedge signal pour /brief redesign post-Sprint-1.1.

Sprint 1.1 baseline verify: 98/98 function bodies unchanged, structural
counts unchanged, zéro commit a touché bot/main.py depuis le baseline 2158adf.
Ready Monday.

2026-05-16 ~13:00 | /journal_audit empirical KPI #5 | 26 silent tickers révélés (AMD 10, AVGO 10, QCOM 8) — data invisible avant aujourd'hui, now measurable runtime. Only NVDA tracked sur 27 tickers high-impact 30d. Insight brut: signaux narrative-level n'attendent pas tous une decision, mais 7+ tickers core position avec material signals + 0 decision = blind spots vs portfolio.

2026-05-16 ~late evening | Day 5 marathon close | 32 commits, empirical tetrahedron complete:
  /journal_audit revealed 26 silent tickers (high signal, zero decisions)
  /signal_drilldown drills per ticker (e.g. AMD 14 signals, Short Squeez 6)
  /thesis_health shows 21 active theses, 5 narratives, no inflation
  /bias_pattern aggregates BIASES taxonomy (sparse data confirmed
    bias_tagger gap on no_action_flag decisions)
  Refactor: bot/main.py 3324 -> 1115 LOC (-66%), 14 handler modules,
  Sprint 1.1 9/10 chunks closed, mypy strict 29 modules, 189 tests.
2026-05-21 05:05 | test phase L shipped
2026-05-21 05:06 | old alias still works

2026-05-28 19:10 | dashboard A/B | le dashboard lit enfin honnete : zero favorabilite tautologique, couleur = fait de marche. J'ai meme rattrape une tautologie que je m'appretais a reintroduire — l'outil ne me flatte plus mes propres hypotheses (coeur du recit Path 6).
