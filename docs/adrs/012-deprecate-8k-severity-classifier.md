# ADR 012 — 8-K severity classifier SOFT-DEPRECATED comme mesure d'evidence_strength

**Status**: Accepted (30/05/2026)
**Related**: ADR 011 (probability stale-read), decision_logs/01_calibration_unanchored.md iter 6-7

## Context

`intelligence/filings_8k.classify_severity(item_codes)` classifie chaque 8-K en
`catastrophic / high / medium / low` selon le mapping `SEC Item Code -> severity`.
Exemple : Item 4.02 (restatement) -> catastrophic ; Item 5.02 (officer change)
-> high ; Item 2.02 (results of operations) -> medium ; Item 8.01 (other) -> low.

Le classifieur est utilise pour :
1. Filter quels 8-K alerter immediatement via Telegram (`bot/jobs/daily.scheduled_8k_scan_job` : `severity in ("catastrophic", "high")`)
2. Filter quels 8-K apparaissent dans le morning brief (`intelligence/morning_brief.py:108`)

## Probleme decouvert (audit 30/05 iter 6-7)

Le classifieur **ne lit que le code item**, pas le contenu du filing. Trois 8-K
testees recemment :

| Filing | Item codes | Contenu reel | Classifieur | V2 sur contenu |
|---|---|---|---|---|
| NVDA Q1 FY27 | 2.02 | Earnings beat $35.1B + $80B buyback + 25x dividend | **medium** | **strong, prob=0.750 bullish** |
| GOOGL 2026-05-21 | 8.01 | Debt notes issuance boilerplate | **medium** | none, prob=0.500 watch |
| MSTR 2026-05-26 | 7.01, 8.01 | $1.5B convertible repurchase + 24K BTC acquisition | **medium** | **moderate, prob=0.620 bullish** |

Le classifieur Item-codes seul classe les 3 en `medium` indifferemment. V2 sur
contenu reel discrimine entierement : strong / none / moderate. Le mapping
Item -> severity est trop grossier comme mesure de force d'evidence.

## Decision

**Soft-deprecation** : conserver `classify_severity()` pour son usage operationnel
(filter alertes Telegram tier-1), mais marquer dans le code et la doc que
**evidence_strength canonique est V2 sur contenu reel**, pas severity.

Concretement :
1. `intelligence/filings_8k.py` : annoter `classify_severity()` avec note
   d'obsolescence comme mesure d'evidence (conservation pour alerting heuristique).
2. `intelligence/morning_brief.py` + `bot/jobs/daily.py` : commentaires inline
   pour signaler que severity = filter rapide (heuristique), pas force d'evidence.
3. Cet ADR : trace de la decision.

**Pas supprime** parce que :
- 3 callers actifs, supprimer = casser sans ajouter (V2 n'a pas de remplacant
  one-line pour "alerter immediatement" -- il appellerait Sonnet sur chaque
  filing = overkill pour un Item 4.01 evident catastrophique).
- Le classifieur reste un filter rapide acceptable. Sa limite est revelee, pas
  ses derniers callers.

## Consequence

Future-self : ne **PAS** se baser sur `filings_8k_log.severity` pour decider de
la force d'un signal dans les analyses calibration / Brier. Source de verite :
V2 (`signal_scorer_v2.score_directional_probability().evidence_strength`).

Si une feature future veut filtrer 8-K par force d'evidence reelle, le bon
mecanisme :
1. Wire le 8-K via `edgar_signal_wire.wire_8k_to_signal()` (sync, ~5-10s)
2. Lire `signals.evidence_strength` (a stocker -- pas encore le cas) OU
   recourir a V2 directement sur le contenu

## Pourquoi pas dur deprecate maintenant

V2 sur contenu = 1 call Sonnet par filing (~3-5s + cout). Le pipeline d'alerting
Telegram veut une decision en <100ms. Le classifieur Item-codes est imparfait
mais constant et rapide. Tant qu'on n'a pas d'alternative low-latency, on garde.

Re-evaluation si :
- On detecte qu'une 8-K importante a ete miss-alertee parce que severity!='high'
- On modelise V2 cache pour filings (pre-compute apres wire) -> permettrait
  alerte basee sur evidence reelle sans relance LLM
