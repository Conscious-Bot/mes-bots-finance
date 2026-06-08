# Spec — Taxonomie d'instruments canonique + profils de réponse par secteur

> Rend le système **agnostique au book** : tout ticker entrant s'auto-classe → hérite d'un profil → la machinerie (cornerstone, factor_exposures, position_type, alertes) répond. Y compris les secteurs **hors-PF**. Hérite de `SPEC_ALERT_VOCABULARY`, `CALIBRATION_DOCTRINE`, `SPEC_CORNERSTONE`. Étend `config/sectors.yaml` + `ticker_classifier` + `ticker_axes` existants.

## 0. La version honnête de « répondre à any stock parfaitement »

> « Parfaitement et précisément » = **aussi bien que l'évidence le permet**, jamais une précision fabriquée. Un secteur tenu (semis) se lit avec de l'évidence ; un secteur jamais tenu se lit avec un **prior calibré et MARQUÉ comme tel** ; un instrument non-classable déclenche **fail-closed** (UNCLASSIFIED + flag), pas un profil inventé. La complétude de la *structure* ≠ la précision du *profil*.

## 1. Deux axes de classification orthogonaux (canoniques)

Tu l'as déjà découvert (MHI : secteur=Industrials, thème=Defense). Il faut les **deux** :

- **Axe SECTEUR** (*ce que c'est*) : structure complète type GICS, hiérarchique — `secteur → sous-secteur → sous-industrie`. Couvre **tout le marché**, pas seulement le PF.
- **Axe THÈME/FACTEUR** (*ce que ça parie*) : le `macro_factor` (AI-capex, memory-cycle, reshoring, rates-sensitive…) — déjà dans `ticker_axes`. C'est ce que `factor_exposures` consomme.

Un instrument porte **toujours les deux** : sa nature (secteur) et son pari (facteur). La divergence entre les deux est elle-même un signal (cf la cross-classification que `factor_exposures` affiche déjà).

## 2. Le profil de réponse par sous-secteur (ce dont le moteur a besoin)

C'est le cœur : chaque sous-secteur porte un **profil canonique** qui dit au moteur *comment lire* tout instrument qui en relève.

```yaml
semiconductors.equipment:
  cyclicality: deep_cyclical          # cycle-beta MESURÉ (pas asserté)
  criticality: chokepoint             # commodity ↔ moat ↔ chokepoint
  macro_factor: ai_capex
  deliverable_kpis:                   # la "réalité livrable" SPÉCIFIQUE au secteur
    - bookings_yoy
    - utilization
    - asp_trend
  crowding_proxies: [SMH, SOXX]       # ETFs qui le crowdent → consensus
  invalidation_template:              # kill-criteria type du secteur
    - "capex foundry révisé >15%"
    - "ASP down >10%"
  cycle_role: late_cyclical           # rotation sectorielle (early/mid/late/defensive)
  evidence_tier: S                    # cf §3
```

**Pourquoi c'est non-négociable** : la « réalité livrable » de la divergence micro est **sectorielle** — pour les semis c'est bookings/ASP, pour les banques NIM/credit-loss, pour l'énergie production/crack-spread, pour la pharma pipeline/patent-cliff. Sans profil par secteur, le moteur ne sait pas *quoi* mesurer pour un nouveau stock. Le profil est la clé qui rend le cornerstone agnostique au book.

## 3. Tiers d'évidence du profil (complétude ≠ fausse précision)

| Tier | Sens | Confiance |
|---|---|---|
| **S** | validé sur holdings (semis — ton expertise) | haute, evidence-backed |
| **A** | prior littérature (secteur connu, pas tenu) | moyenne, marqué « prior » |
| **B** | défaut générique (sous-industrie obscure) | basse, marqué « générique » |

Un ticker hérite du **meilleur tier disponible, MARQUÉ**. Shrinkage (cf doctrine) : le prior d'un secteur non-tenu se **raffine quand une position y accumule de la donnée** — il migre B→A→S au mérite, jamais affirmé S d'emblée.

## 4. Auto-classification (onboarding zéro-friction)

```
nouveau ticker → ticker_classifier / ticker_meta_classifier
   → (secteur, sous-secteur, sous-industrie) + (macro_factor/thème)
   → hérite le profil du sous-secteur (au tier dispo)
   → la machinerie répond (cornerstone, sizing, alertes) sans config manuelle
```

**Fail-closed** : non-classable avec confiance suffisante → `UNCLASSIFIED` + flag + le système **dit qu'il ne sait pas lire ce stock**, jamais un profil fabriqué. Ne prétends pas répondre « précisément » à un instrument que tu ne classes pas.

## 5. Criticité & cyclicité = mots-signaux canoniques (lien `SPEC_ALERT_VOCABULARY`)

Ils entrent dans le vocabulaire d'alerte, classe **STATE** (descriptif, calme — n'attirent pas l'œil par eux-mêmes) :

- `CYCLICALITY_{DEFENSIVE|MODERATE|CYCLICAL|DEEP_CYCLICAL}` — **calibré** (cycle-beta mesuré sur l'historique du secteur, pas un label tapé).
- `CRITICALITY_{COMMODITY|MOAT|CHOKEPOINT}` — evidence-backed (le `CHOKEPOINT` informe le **prior `position_type`** structural, mais ne l'assigne pas seul — l'assignation reste justifiée + pré-enregistrée, cf Catch 1).

Ils héritent de la règle d'attention : un STATE de cyclicité ne crie pas ; c'est un EVENT (`REGIME_SHIFT`, `CYCLE_ROTATION`) qui alarme quand le *delta* le mérite.

## 6. Architecture / grounding

- Étend `config/sectors.yaml` → `config/taxonomy.yaml` (structure complète) + `config/sector_profiles.yaml` (profils tiers, déclaratif L17).
- Réutilise `ticker_classifier.py` / `ticker_meta_classifier.py` / `ticker_axes` (macro_factor) — **ne pas réécrire**, étendre vers la taxonomie canonique.
- Le profil alimente : `divergence_engine` (deliverable_kpis), `factor_exposures` (macro_factor), `position_steer` (prior position_type via criticality), `consensus` (crowding_proxies).

## 7. Gouvernance & tests verrouillants

1. **Structure complète** (couvre tout le marché) MAIS chaque profil porte son `evidence_tier` obligatoire (pas de profil sans tier = build rouge).
2. **Aucun profil fabriqué** : un secteur non-tenu sort un prior A/B *marqué*, jamais présenté comme validé S.
3. **Fail-closed** : ticker non-classable → `UNCLASSIFIED`, pas de lecture confiante (assert).
4. **`deliverable_kpis` présents** pour tout sous-secteur qu'une position touche (sinon le moteur micro ne peut pas lire ce nom → flag).
5. **`cyclicality` calibrée** : cycle-beta mesuré, pas un label littéral (gate, comme « pas de `weight=<float>` »).
6. **Shrinkage actif** : le tier d'un secteur migre B→A→S **uniquement** quand `n_holdings_resolved >= N_min` et `audit_validated=true` (assert).
7. **Tier S exclusif** : un profil `tier=S` nécessite un `audit_metadata.holdings_validated` avec liste de tickers tenus + dates (anti-affirmation).

## 8. Build sequence

1. **`config/sector_profiles.yaml`** : poser le profil **semis** tier-S (validé sur tes holdings actuels ASML/AMAT/LRCX/etc.) + squelette priors tier-A pour secteurs adjacents (banks, energy, healthcare, industrials, consumer-staples). Tier-B générique pour le reste.
2. **`config/taxonomy.yaml`** : structure GICS-like complète (peut être largement vide en profil mais classifiée).
3. **Tests verrouillants** : 7 invariants §7.
4. **Extension `ticker_classifier`** : retourner `(secteur, sous-secteur, macro_factor, tier_dispo, degraded_if_unclassified)`. Wire fail-closed sur `UNCLASSIFIED`.
5. **Migration `divergence_engine.micro`** : consomme `deliverable_kpis` du profil au lieu de hardcoder bookings/ASP. Le moteur reste **projection-agnostic** (cf L24 walking skeleton) ; le profil est l'input.
6. **Tracer-bullet** : un ticker non-semis (ex. JPM banks) onboarded → vérifier que la machinerie répond avec `tier=A prior`, marqué, fail-closed sur les KPIs absents. Pas un profil inventé.

## 9. Seams à vérifier (verify-before-patch)

- `intelligence/ticker_classifier.py` : entrée/sortie actuelle, comment plug le nouveau profil sans casser l'existant.
- `intelligence/ticker_meta_classifier.py` : axe `macro_factor` déjà capturé.
- `intelligence/factor_exposures.py` : où il consomme `macro_factor` aujourd'hui.
- `config/sectors.yaml` : ce qu'il contient déjà, ce qu'il faut migrer.

## 10. Implementation Status

- **Gravé** : 2026-06-XX (commit `__TBD__`)
- **Enrichi** : 2026-06-08 (sections build + seams + tests shrinkage/tier-S exclusif)
- **Implémentation** : NON COMMENCÉE
- **Fichiers cibles** : `config/sector_profiles.yaml`, `config/taxonomy.yaml` (à créer) ; `intelligence/ticker_classifier.py` (à étendre) ; `tests/test_sector_profiles.py` (à créer)
- **Audit drift** : `scripts/audit_canonical_drift.py` (à wirer)
- **Prochain step** : C7a-2 (cf TODO #101)

## 11. Le fil

> Prêt à recevoir n'importe quel stock = il se **classe** (deux axes), **hérite** d'un profil calibré et tiers, et la machinerie répond **aussi bien que l'évidence le permet** — evidence sur le tenu, prior marqué sur le connu-non-tenu, fail-closed sur l'inconnu. La précision n'est jamais fabriquée : le système répond *prêt et honnête*, et se raffine au mérite quand une position lui donne de l'évidence. C'est l'agnosticité au book sans la prétention de tout savoir d'avance.
