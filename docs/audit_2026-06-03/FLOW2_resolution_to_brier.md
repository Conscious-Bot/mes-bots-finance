# Flow 2 — Prediction → Resolution → Brier

**Trace** : daily_resolve_job → get_due_predictions → get_close_on (prix exact target_date) → outcome computation → brier_for → resolve_prediction_row → predictions UPDATE + prediction_audit_log INSERT.

**Importance** : **c'est le flux du 10/06**. Les 35 V1 prédictions ciblées 2026-06-10 doivent résoudre par ce path. Audit prioritaire.

## Entry point

```
APScheduler cron daily (bot/jobs/daily.py:17 daily_resolve_job)
  scheduled in morning_chain (bot/jobs/sequences.py:106) at 09:00 UTC
  → learning.resolve_due_predictions(limit=50) (learning.py:287)
```

J-day specific :
```
APScheduler date trigger 2026-06-10 09:30
  → bot/jobs/j_day.py:109 j_day_batch_close_job (dépend de daily_resolve_job 09:00 ayant déjà tourné)
```

## Trace end-to-end

```
1. storage.get_due_predictions(limit=50) (storage.py:986)
   SQL : SELECT * FROM predictions
         WHERE target_date <= date('now') AND resolved_at IS NULL
         ORDER BY target_date ASC LIMIT 50

2. for each pred in due :
   a. target_close = prices.get_close_on(ticker, target_date) (prices.py:37)
      → yfinance .history() lookup pour target_date exact
      → returns float OR None (NaN handled)
   
   b. SKIP si target_close None ou NaN (learning.py:307 `continue`)
   
   c. return_pct = (target_close - baseline_price) / baseline_price
   
   d. outcome = correct/incorrect/neutral basé sur OUTCOME_THRESHOLD=0.05
      bullish + return >= +5% → correct
      bullish + return <= -5% → incorrect
      bullish + entre → neutral
      (bearish miroir)
   
   e. delta = OUTCOME_DELTA[outcome]
      (ADR 007 : delta calculé + stocké pour audit, mais NON appliqué
       à credibility — autorité unique = Brier recal mensuel)
   
   f. brier_score = math_helpers.brier_for(prob, outcome) (math_helpers.py:77)
      = (prob - target)² where target = 1 si correct, 0 si incorrect
      = None si prob is None OR outcome == 'neutral'
   
   g. storage.resolve_prediction_row (storage.py:999)
      → SELECT prev state (PIT)
      → if re-resolve : INSERT prediction_audit_log 're_resolve_pre' + 're_resolve'
      → if first : INSERT prediction_audit_log 'resolve'
      → UPDATE predictions SET resolved_at, final_price, return_pct, outcome,
                                 credibility_delta, brier_score
```

## Plugs solidity

| Plug | Status | Notes |
|---|---|---|
| `get_due_predictions` SQL | **solide** : LIMIT 50, idempotent, ORDER BY target_date ASC | re-run du cron = même résultat. Pas de double-resolve. |
| `get_close_on` (yfinance) | **fragile** : retour None si yfinance ban / network / ticker delisted / weekend | impact J-day : si 35 V1 ciblées 2026-06-10 et un partial fail yfinance, le subset résolu = silent partial. Pas d'alarme. |
| NaN handling | **solide** : `target_close != target_close` check (line 307) catch NaN explicit | python idiomatic NaN-self-inequality |
| outcome computation | **solide** : symétrique bullish/bearish, threshold explicit ±5% | bug potentiel = return_pct calcul si baseline_price = 0 → division par zero. Cf check ailleurs ? |
| `brier_for` | **solide** : None si non-scoreable, formule canonique | neutral correctly excluded (consistent avec OUTCOME_DELTA[neutral]=0) |
| `resolve_prediction_row` PIT log | **solide** : append-only log, transaction commit-or-rollback | premier flag bug 31/05 fixé via re-resolution audit ✓ |
| Re-resolve detection | **solide** : prev['resolved_at'] is not None → is_reresolve=True → log 2 lignes audit | source unique de re-resolve, déjà testé via audit 31/05 |

**Risk J-day** : `target_close = None` case (line 307 `continue` silent) → silent drop. Si 5/35 V1 ratent get_close_on, le J-day report dira "30 résolues" sans flag sur les 5 manqués. Audit log ne contient PAS d'entry pour les non-résolues. **Le watcher j_day_watcher.sh ne détecte que snapshot=missing, pas snapshot=partial.**

## Failure modes

| Étape | Failure | Détection | Récupération | Severity |
|---|---|---|---|---|
| `get_due_predictions` | DB lock (concurrent write) | sqlite3.OperationalError | pas géré explicitement → crash → APScheduler relance ? | **P2** — vérifier WAL mode actif |
| `get_close_on` | yfinance None / NaN | check explicit ligne 307 → `continue` | **silent skip, jamais retry** | **P1** — gap critique J-day : les 5 manqués ne sont jamais re-tentés sauf si target_date <= date('now') reste vrai (oui car target_date <= today). MAIS le cron tournera demain, et retentera. À J-day-only fenêtre, c'est OK. Mais le rapport j_day_batch_close_job (09:30) ne réalise pas que le daily_resolve (09:00) n'a pas tout résolu. |
| outcome=neutral | brier_score = None | excluded correctement de Brier average via `WHERE brier_score IS NOT NULL` | **P3** acceptable |
| baseline_price = 0 | div by zero ZeroDivisionError | non vérifié dans `resolve_due_predictions` | **P2** mineur — register_prediction protège déjà contre baseline None mais pas 0. Improbable mais possible si fixture corrompue |
| resolve_prediction_row PIT log INSERT fail | sqlite3 exception | non géré explicitement, propage → crash le `for` loop → predictions suivantes pas résolues | **P2** — un seul corrupt insert tue le batch. Devrait être try/except per-pred avec log |
| 2 daily_resolve_job concurrents | double-resolve risk | PIT log + UPDATE non-atomique vis-à-vis du concurrent | **P2** — single-instance guard (fcntl.flock) prévient déjà 2 bot.main, donc 2 cron ne se croisent pas. Mais : si APScheduler relance un job qui a crashé mid-batch, on peut re-resolve. La logique re_resolve_pre + re_resolve catch ça → audit-grade ✓ |

## Coupling assessment (3 patterns)

| Pattern | Évaluation |
|---|---|
| **Pattern 1 (liveness ≠ functionality)** | daily_resolve_job runs in bot process. Process alive + scheduler thread dead = silent fail. Couvert par #100 (post-J-day). À J-day spécifique : healthchecks.io ping in j_day.py catch ça car le ping vient du job lui-même ✓ |
| **Pattern 2 (snapshot drift)** | predictions table = source unique. `brier_by_methodology` aggregator computes from predictions live. Pas de snapshot intermédiaire. **N/A** sauf si le public site exporte la valeur (post-J-day = #101). |
| **Pattern 3 (multi-path)** | brier_score est calculé une seule fois ici (`math_helpers.brier_for`) + lu partout via `predictions.brier_score`. ✓ Mais le **calcul d'agrégat** (brier moyen, dedup, etc.) est dispersé : `j_day.py` recalcule cluster dedup à la main au lieu d'appeler `storage.brier_by_methodology`. **Pattern 3 violation locale**. Couvert par #102. |

## Résilience layer integration

| Item | Status |
|---|---|
| LLMUnavailableError | N/A — pas d'appel LLM dans la résolution. ✓ |
| ScoringOrchestrator | N/A |
| Restitution markers | N/A direct, mais le J-day report Telegram surface le résultat via texte structuré (`bot/jobs/j_day.py:88-104`) sans prose fake ✓ |
| Healthchecks ping post-resolve | ✓ wired ce matin (commit `3d442d9`) dans `j_day_batch_close_job` après snapshot. Pas dans daily_resolve_job lui-même (ne tire qu'une fois le 10/06). Adequate pour J-day. |

## Duplicates dans ce flux

- **Cluster dedup logic** : implémenté dans `math_helpers.aggregate_brier_dedup` (canonical) ET dans `bot/jobs/j_day.py:55-67` (recalcul local). Le J-day code n'utilise pas le helper. **Pattern 3 mineur**, #102.
- **OUTCOME_THRESHOLD=0.05** : constante définie dans `learning.py:37`. Recherche ailleurs ne montre pas de duplicate hardcoded ✓.
- **OUTCOME_DELTA dict** : single source ✓.

## Dead code dans ce flux

- `credibility_delta` est calculé + stocké mais **non appliqué** (ADR 007 dit autorité=Brier recal mensuel). Commentaire explicite ligne 326-327. Le champ est conservé pour audit. **Conscient, documenté.** Pas dead, mais à archiver dans la doc d'ADR au cas où.
- Aucun autre dead code détecté dans la résolution.

## Action items Flow 2

| Item | Priority | Disposition |
|---|---|---|
| **Partial-resolve detection J-day** : si daily_resolve laisse N predictions ciblées 2026-06-10 non résolues (yfinance fail), le j_day_batch_close_job ne le voit pas | **P1** | À cabler **avant J-day** : `_build_brier_telegram_msg` doit aussi vérifier `COUNT(*) FROM predictions WHERE target_date='2026-06-10' AND resolved_at IS NULL` et inclure le residual dans le report. Marker honnête. ~15 min |
| `baseline_price=0` ZeroDivision guard | **P2** | trivial — add `if baseline_price <= 0: continue` |
| Per-pred try/except dans resolve loop | **P2** | un crash mid-batch perd les suivants. Wrap chaque pred dans try/except, log + continue |
| Cluster dedup recompute local dans j_day.py | **P2** | #102 (aggregator) couvrira ce point |
| baseline_price=0 / corrupted prediction inserted | P3 | invariants test au insert (déjà passe via methodology check, étendre à baseline >0 ?) |

**P1 unique** : partial-resolve detection in J-day report. Action **avant le 10/06**.
