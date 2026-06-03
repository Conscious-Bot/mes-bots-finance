# Synthèse — Audit deep tuyauterie 2026-06-03

**Méthode** : 5 flux vitaux + 1 cross-cutting. File:line refs verified. Discrimination P1 (load-bearing, blocking) / P2 (à fixer) / P3 (cosmétique).

## Verdict d'ensemble

Tuyauterie globalement **solide** :
- ADR-014 (canonical + substance filters) tient. Source unique respectée pour la méthodologie.
- Resilience layer (Phase 1-4) shippée et testée.
- J-day machinery in-band + out-of-band (healthchecks.io) prête.
- 28 alembic migrations, schema cohérent.
- 1000+ tests, peu de skip, pas de red ignoré.

Mais **un P1 critique en deployment gap** (bot tourne sur code d'hier) + **trois P1 ciblés** (un par flux) à fixer ou décider avant J-day.

## Action table consolidée

### P1 — load-bearing, à traiter immédiatement OU à décider explicitement de ne pas faire

| # | Item | Source | Effort | Recommandation |
|---|---|---|---|---|
| **1** | **Restart bot pour déployer code post-migration 0028** | Flow 5 | 30s | **MAINTENANT.** `pkill -f "python.*bot.main"` → launchd restart. Sans ça, dès que LLM revient, chaque insert prediction crashera IntegrityError. |
| 2 | **Partial-resolve detection J-day** (yfinance fail silencieux sur N/35 V1 predictions) | Flow 2 | 15min | Ajouter dans `_build_brier_telegram_msg` : `COUNT(*) FROM predictions WHERE target_date='2026-06-10' AND resolved_at IS NULL` + flag explicit dans le report Telegram. **Avant 10/06.** |
| 3 | **Verify scheduler dump au start** : `j_day_batch_close_job` registered avec next_run=2026-06-10 09:30 | Flow 4 | 5min | Post-restart (cf P1.1), tail `bot.log` for "Scheduler started with N jobs" line. **Avant 10/06.** |
| 4 | **Verify cron_tier* double registration** (`bot/main.py:255-257` ET `279-281`) | Flow 4 | 5min | Post-restart, count occurrences dans le dump scheduler. Si 2× → supprimer un set. |
| 5 | **Lock_in instrumentation** : `bot/handlers/positions.py:399` TODO Pile 2.1 v2 vs decision explicit "pas faire" | Cross-cutting | discussion | Cf memory `[[presage_biais_1_only]]` : biais #1 PRESAGE non-instrumented. Décision actée à reconfirmer. |

### P2 — à fixer post-J-day, déjà capturées sauf nouveaux items

| # | Item | Source | Capturé existant |
|---|---|---|---|
| 6 | Sweep handlers Telegram pour catch LLMUnavailableError (5 fichiers identifiés) | Flow 3 | Nouveau — log task |
| 7 | Silent drops post-V2-watch tracking (compteur visible) | Flow 1 | Nouveau — log task |
| 8 | Tests d'intégration mode Haiku (cost cap soft) sur V2 prompt | Flow 1 | À shipper avec #105 (validation calibration) |
| 9 | `register_prediction` re-vérifier baseline_price drop fix (#30 marquée completed mais log montre récurrence) | Flow 1 | Re-ouvrir #30 ? |
| 10 | `book.py:384` native vs eur prix séparation | Cross-cutting | TODO doc, lié à #91 |
| 11 | `prices.py:141` fx_rates SQLite migration | Cross-cutting | Standalone task à logger |
| 12 | dashboard/serve.py thread/process health monitoring | Flow 3 | Couvert par #100 (heartbeat tests link) |
| 13 | Telegram sendMessage retry on 429 | Flow 3 | Nouveau — log task |
| 14 | dashboard HTML well-formed validation post-write | Flow 3 | Nouveau — log task |
| 15 | Per-pred try/except dans resolve_due_predictions loop | Flow 2 | Nouveau — log task |
| 16 | baseline_price=0 ZeroDivision guard | Flow 2 | Trivial — fix au prochain touch |
| 17 | Healthchecks ping pour monthly_track_record + weekly_calibration | Flow 4 | Nouveau — log task |
| 18 | serve.py supervised by launchd (second plist) | Flow 4 | Optionnel |
| 19 | Logguer dans LESSONS.md la règle "migration schema-invariant → restart bot" | Flow 5 | Doc, 10 min |
| 20 | Vérifier WAL mode active en prod | Flow 5 | trivial sanity |
| 21 | task #28 re-verify daily_backup_job vivant | Flow 5 | grep mtime |

### P3 — cosmétique, sweep ponctuel

| # | Item | Source |
|---|---|---|
| 22 | `materiality_v2.py:169,211` use storage.db() au lieu sqlite3.connect direct | Flow 5 |
| 23 | `intelligence/cluster_threshold_sweep.py` orphan : décider supprimer vs wirer | Cross-cutting |
| 24 | `intelligence/reconcile.py` orphan : confirmer manual usage vs supprimer | Cross-cutting |
| 25 | `intelligence/materiality.py` V1 archivé : confirmer orphan + supprimer | Flow 1 |
| 26 | 6 TODOs/DEPRECATED tags dispersés | Cross-cutting |
| 27 | render.py 5522 LOC duplications internes | Flow 3, #66 |
| 28 | storage.py 3667 LOC split éventuel | Cross-cutting |
| 29 | 3 sites de query KPI (dashboard + /brief + morning_brief) | Flow 3, #102 |

## Pattern coupling assessment (3 patterns du framework)

| Pattern | Couverture audit |
|---|---|
| **Pattern 1** (liveness ≠ functionality) | Confirmé : Telegram polling thread, sendMessage, serve.py regen thread, scheduler thread. Tous **non couverts pré-J-day**. Mitigation J-day : healthchecks.io ping out-of-band. Post-J-day : #100. |
| **Pattern 2** (snapshot drift) | Confirmé : dashboard.html = snapshot 60s, backups quotidiens = snapshot daily, future site public = snapshot publish. Couvert par #101 (provenance stamps). |
| **Pattern 3** (multi-path) | Confirmé en plusieurs sites : 52 `FROM predictions` queries en 14 fichiers, 3 sites de KPI computation, j_day cluster dedup recompute local, double registration cron_tier* (P1). Centralisation partielle ADR-014 + #102 extension. |

## Resilience layer integration : où ça couvre, où ça ne couvre pas

| Flow | LLM error path | Cost cap soft | Restitution marker | ScoringOrchestrator | Shadow paired |
|---|---|---|---|---|---|
| Flow 1 (signal→pred) | ✓ pending_llm | indirect Haiku | N/A | OFF (#104) | OFF (#106) |
| Flow 2 (resolve→Brier) | N/A | N/A | N/A | N/A | N/A |
| Flow 3 (state→surface) | ✓ chat+analyze, **gap autres 5 handlers** | badge ✓ | ✓ source unique | N/A | N/A |
| Flow 4 (schedule) | per-job catch à auditer | global | N/A | N/A | N/A |
| Flow 5 (storage) | N/A | N/A | N/A | N/A | N/A |

## Synthèse en 5 lignes

1. **Restart bot immédiat** (P1.1) sinon insertions predictions crasheront silencieusement dès LLM up.
2. **Avant le 10/06** : 3 vérifications J-day (P1.2-4), toutes <30 min cumulées.
3. **Décision attendue** : P1.5 lock_in instrumentation (ship vs explicitly skip).
4. **Tuyauterie globalement solide** : ADR-014 tient, resilience shippée, schema cohérent, tests 1000+ passent.
5. **Post-J-day** : 15 items P2 à dispatcher dans les tasks #99-108 ou nouveaux. ~3 items vraiment nouveaux, le reste = recouvrement avec tâches déjà loggées.
