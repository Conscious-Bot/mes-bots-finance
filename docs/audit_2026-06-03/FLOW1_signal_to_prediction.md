# Flow 1 — Signal → Prediction

**Trace** : ingestion (Gmail / EDGAR / insider) → matérialité scoring → V2 directional scoring → register_prediction → predictions table.

## Entry points

Trois sources distinctes, trois pipelines :

| Source | Entry function | Storage cible |
|---|---|---|
| Gmail (newsletters) | `data_sources/gmail_.py:215` `ingest_new_emails()` | `signals` via `storage.insert_raw_signal` (storage.py:443) |
| EDGAR 8-K | `intelligence/edgar_signal_wire.py:45` `wire_8k_to_signal()` | `signals` via `storage.insert_primary_filing_signal` (storage.py:402) |
| Insider buy clusters | `intelligence/edgar_signal_wire.py:179` `wire_buy_cluster_to_signal()` | `signals` via same |

Gmail tire via cron `bot/jobs/intervals.py:19` `ingest_gmail_job()` (cron horaire) qui chaîne immédiatement materiality_v2 sur ce qui vient d'arriver (lignes 26-39).

EDGAR tire via cron dédié (à vérifier flow 4), avec wire intégré qui appelle `learning.auto_register_predictions` directement à l'insertion du signal (`wire_and_register_8k` ligne 271, `wire_and_register_buy_cluster` ligne 240).

**Discontinuité notée** : Gmail ingest → materiality_v2 → (cron séparé) → V2 directional. EDGAR ingest → wire → V2 directional **inline**. Deux pipelines différents pour la même cible (prédiction insérée). Le wiring EDGAR court-circuite materiality_v2 — délibérément, car le score=7 est hardcodé (cf commentaire `edgar_signal_wire.py:16` "score = 7 (passe filter auto_register_predictions score>=6)").

## Trace end-to-end

### Pipeline A (Gmail)

```
Gmail cron horaire (bot/jobs/intervals.py:19)
  → gmail_.ingest_new_emails (data_sources/gmail_.py:215)
    → gmail_.fetch_emails (line 100)
    → GmailSignal validation (line 159 Pydantic)
    → storage.insert_raw_signal (storage.py:443)
      → INSERT INTO signals (gmail_id UNIQUE → dedup) 
  → materiality_v2.score_pending_signals_v2 (materiality_v2.py:158)
    → score_materiality_structured (line 24, LLM call)
    → persist_breakdown (line 117) → UPDATE signals SET impact_magnitude, score
    → UPDATE signals SET scoring_status='scored'

[separately, via cron daily]
  → learning.auto_register_predictions (learning.py:163)
    → filter score>=6 + sentiment bullish/bearish (line 181)
    → for each ticker × signal :
       → signal_scorer_v2.score_directional_probability (line 215)
       → learning.register_prediction (line 260)
         → storage.insert_prediction (storage.py:839)
           → INSERT INTO predictions (methodology_version='v2' explicit)
```

### Pipeline B (EDGAR 8-K + insider clusters)

```
EDGAR cron (à vérifier dans Flow 4)
  → edgar_signal_wire.wire_and_register_8k (line 271)
    OR edgar_signal_wire.wire_and_register_buy_cluster (line 240)
  → wire_8k_to_signal (line 45) — insert signal
    → storage.insert_primary_filing_signal (storage.py:402)
    → score = 7 (hardcoded — bypass materiality_v2 LLM)
  → learning.auto_register_predictions ([sig_dict]) (line 263)
    → same downstream as Pipeline A
```

## Plugs solidity

| Plug | Status | Notes |
|---|---|---|
| Gmail credentials | live (`get_service()` OAuth), nécessite `.env` ✓ | non-fatal si manquant (catch global ligne 226) |
| storage.insert_raw_signal dedup | **solide** : UNIQUE constraint sur `gmail_id` + check explicite via `signal_exists_by_gmail_id` (storage.py:353) | double layer = pas de double insert même si check race |
| materiality_v2 → signals UPDATE | **solide** : transaction explicite (`conn.commit()` line 214) | path d'erreur LLMUnavailableError → `_mark_pending_llm` (line 196) puis abort batch (line 206) ✓ |
| signal_scorer_v2 → register_prediction | **solide** : V2 path passé `methodology_version='v2'` explicitement (learning.py:264 commit `d4a9481`) | abort batch sur LLMUnavailableError (line 224-239), marque restants pending_llm |
| storage.insert_prediction (methodology_version required) | **solide** : validation explicite (ADR 014 hazard B fix, alembic 0028) | toute tentative d'INSERT sans methodology_version → ValueError loud OU IntegrityError NOT NULL |
| EDGAR wire score=7 hardcoded | **fragile** : pas d'évaluation matérialité par le LLM | délibéré (8-K + cluster sont haut-signal a priori) mais bypass = on rate les 8-K boilerplate. Cf. `test_edgar_exhibits.py::test_v2_on_extracted_boilerplate_8k_stays_watch` (env-flaky, à valider) |

## Failure modes

| Étape | Failure | Détection | Récupération | Severity |
|---|---|---|---|---|
| Gmail fetch | OAuth expired / quota | log warning, retour vide | nouveau cycle dans 1h | **P2** — silencieux pour user, surface via uptime alarm si chronique |
| insert_raw_signal | gmail_id duplicate | dedup explicit returns None | OK silencieux | **P3** — comportement attendu |
| score_materiality_structured | LLMUnavailableError | scoring_status='pending_llm', abort batch | drain job futur (#93 A2 wired) | **P1** géré ✓ |
| score_materiality_structured | JSON parse fail | catch dans `materiality_v2.py:` retourne None, signal reste `impact_magnitude IS NULL` | retry au prochain cron | **P2** — peut accumuler "stragglers" silencieux. Pas de timeout / abandon explicite après N retries |
| signal_scorer_v2 | LLMUnavailableError | log + mark all remaining pending_llm + return registered | drain reprend | **P1** géré ✓ |
| signal_scorer_v2 | None return (watch enforcement OR JSON fail) | log info "V2 returned None ... skip" | aucune (pas de V1 fallback — délibéré, anti-mono-bucket) | **P2** — silencieux. Le signal reste sans prédiction enregistrée, jamais re-tenté |
| register_prediction | baseline_price IS None (yfinance retry fail) | print "no baseline price" → return None | aucune | **P2** — silent drop. Memory `[[parallel_projects_tennis_bot]]` mentionne ce bug 31/05 sur SK Hynix / SAMSUNG. Task #30 marquée [completed] mais le print est toujours là (line 133) — fix peut-être partiel |
| insert_prediction | methodology_version manquant | ValueError ou IntegrityError | loud crash | **P1** géré ✓ (ce matin) |

**P2 récurrent** : signaux qui passent le filtre score≥6 mais scorent watch ou échouent en JSON → invisibles. Pas un bug mais pas tracé non plus. Si 50% des Gmail signals deviennent watch silencieusement, on rate la mesure de "qualité de l'ingestion".

## Coupling assessment (3 patterns)

| Pattern | Évaluation |
|---|---|
| **Pattern 1 (liveness ≠ functionality)** | Gmail OAuth peut renvoyer 401 → token expiré, le bot continue, l'ingestion silencieusement à zéro. **Pas de detection-link** — process alive, fonctionnalité morte. Couvert par #100 (post-J-day). |
| **Pattern 2 (snapshot drift)** | Pas applicable directement à ce flux (pas de snapshot exporté, c'est de l'ingest en continu). N/A. |
| **Pattern 3 (multi-path)** | Pipeline A et Pipeline B chacun calculent leur propre route signal→prediction. Le calcul de la proba final passe par le **même** `signal_scorer_v2.score_directional_probability` ✓. Mais les **filtres en amont** (score≥6 dans A, score=7 hardcoded dans B) sont **deux chemins distincts** — un signal Gmail qui aurait scoré 5 serait filtré, un EDGAR 8-K équivalent ne le serait jamais (score forcé à 7). Asymétrie consciente, documentée. Pas une violation Pattern 3 stricte. |

## Résilience layer integration

| Item | Status |
|---|---|
| LLMUnavailableError detection (#93 A1) | ✓ raise dans `signal_scorer_v2.py:208` + `materiality_v2.py:` propagation |
| scoring_status='pending_llm' marker (#93 A2) | ✓ wiré dans `materiality_v2.py:196` et `learning.py:232` |
| ScoringOrchestrator wiring (#94 phase 3) | **OFF** — `learning.py:215` appelle `signal_scorer_v2` directement, pas l'orchestrator. Comme prévu, c'est #104 post-J-day. |
| Restitution markers | N/A à ce flux (pas de surface UI ici) |
| Cost cap soft (Haiku auto) | indirect : si cap soft franchi, `signal_scorer_v2.score_directional_probability` invoque `llm.call_*` qui resolve Haiku via `_resolve_model`. Le prompt V2 est sensible au modèle — Haiku peut produire moins de structure JSON cohérente. **Pas de test pour ce path en mode Haiku.** P2 à vérifier post-flag-flip. |

## Duplicates dans ce flux

- `from intelligence import signal_scorer_v2` apparaît 3× dans `learning.py` (175, 215, 260 indirect via register_prediction). **Acceptable** — lazy imports pour éviter cycle.
- Le filtre score≥6 + sentiment bullish/bearish est dupliqué entre Pipeline A (`learning.py:181`) et Pipeline B (score=7 hardcoded). **Conscient, documenté.**
- Pas d'autre duplication de logique détectée dans le flux.

## Dead code dans ce flux

- `intelligence/materiality.py` (sans `_v2`) — orphan candidat ? Vérifier vs `materiality_v2.py`. Probable code V1 archivé.
- Aucun autre dead code identifié dans le flux ingestion → prediction.

## Action items Flow 1

| Item | Priority | Disposition |
|---|---|---|
| Tests d'intégration mode Haiku (cost cap soft) sur V2 prompt | **P2** | À shipper avec #105 (validation calibration) |
| Silent drops post-V2-watch tracking | **P2** | Compteur `n_watch_returned` par cron, surface en KPI. Petit task. |
| `materiality.py` V1 archivé : vérifier orphan, supprimer si oui | P3 | Sweep ponctuel |
| Pipeline A vs B asymétrie score=7 hardcoded EDGAR vs ≥6 Gmail | P3 | Documenté, consciente. Si on veut une politique unique : task. Sinon laisser. |
| `register_prediction` silent "no baseline price" (line 133) | **P2** | Re-vérifier que c'est vraiment fixé post-#30. Si l'erreur arrive encore en prod (logs récents montrent "register_prediction: no baseline price for AVGO @ 2026-06-01" plusieurs fois), c'est un faux completed |
