# ADR 010 — Decision Accountability Layer

**Statut** : Proposed (12 juin 2026), Q1/Q2/Q3 tranchées 13 juin 2026
**Date pose** : 13 juin 2026
**Chantier complet** : [`docs/CHANTIER_REDEVABILITY_LAYER.md`](../CHANTIER_REDEVABILITY_LAYER.md)

---

## Décision

Ajouter une **couche de redevabilité décisionnelle** au-dessus du ledger de prédictions existant :

1. **Registre de thèses hash-committé append-only** (`thesis_registry`) — record canonique unifié des thèses engagées ET vétoées.
2. **Nulle paresseuse** (`null_benchmark`) — shadow-portfolio SOXX/SPY/QQQ tracké en parallèle du book réel.
3. **Détecteur de dérive narrative** (`narrative_drift`) — classifieur 6 axes mécanisme-vs-mission sur la prose porteuse de thèse.
4. **P&L des biais** (`bias_pnl`) — chiffrage en euros du coût contrefactuel des biais flagués.

Architecture en 3 couches dépendantes : Couche 0 (nulle) gate Couche 1 (registre) qui gate Couche 2 (analytics). Cf chantier §2.

---

## Contexte

- Le ledger de prédictions actuel mesure les **prévisions** (Brier, calibration), pas le **processus**.
- Les vétos (biais #3 — la décision de **ne pas** investir) sont structurellement non-falsifiables : aucune trace, aucune résolution. Cette session 13/06 en est la preuve (SpaceX×6 itérations, Marvell, Lumentum, Aurubis tous rejetés sans trace).
- La valeur de l'appareil de discipline (kill_criteria, over_cap, stale_target, group_cap monitors) est non-mesurée vs l'alternative paresseuse (indexer).
- L'auto-référentialité (l'opérateur note l'opérateur) est l'un des 3 plafonds structurels identifiés dans VISION_PRO — non-percé par la calibration sur outcomes.

---

## Conséquences

**Positives** :
- Étend la doctrine append-only **aux thèses elles-mêmes** (ferme le gap L25/L26 : append-only acquis côté données et prédictions, pas côté affirmations).
- Introduit un **kill-switch honnête** : le système peut conclure « indexe et arrête » de lui-même, sans intervention humaine pour le saboter.
- Convertit le biais #3 (dérive narrative) d'un constat manuel à un signal mesurable.
- Convertit les flags biais existants (label) en montants (€).

**Négatives / coûts** :
- ~10-12h de build gatées derrière (a) la dette en cours (résolution 10 juin → migration 0055 → bug `add_sell`) et (b) une période d'observation post-Couche 0 avant Couche 1.
- Coût LLM Unité C (Haiku par scoring × volume thèses) à modéliser avant pose.
- Croissance accélérée de `thesis_registry` à chaque repose target/stop (cf Q1 ci-dessous).

**Acceptation explicite du verdict possible** : l'output ultime de ce chantier peut être « le book ne bat pas SOXX, indexe ». Un système assez honnête pour produire ce verdict vaut mieux qu'un qui ne le produit jamais. Ne jamais vendre ce chantier comme générateur d'alpha — il améliore **honnêteté + calibration**, pas les rendements.

---

## Alternatives rejetées

1. **Ajouter des features de signal supplémentaires** (5e/6e monitor narratif, scorer alternatif). N'adresse pas la question processus — empile de l'instrumentation sur un edge dont l'existence n'est pas prouvée.
2. **Ne rien faire**. Laisse la discipline non-mesurée et les vétos non-falsifiables. Status quo épistémiquement faible : on continue à investir du temps dans la discipline sans savoir si elle vaut son coût.
3. **Construire les 4 unités en parallèle** (5→4→1 chantier monolithique). Rejeté : Couche 0 doit gate les autres économiquement. Investir dans Couches 1-2 sans verdict de Couche 0 = construire l'instrumentation d'un edge potentiellement inexistant.

---

## Pré-requis bloquants (G1–G5)

Définis dans le chantier §0. Aucune unité ne démarre avant les 5 gates vertes :
- G1 batch Brier 10 juin résolu (≥40)
- G2 10 sentinelles event-type loggées (déc-2026→déc-2027)
- G3 migration 0055 triggers append-only mergée (≥7 triggers `_no_delete`)
- G4 bug `add_sell.realized_pnl_event` corrigé (pattern #133bis)
- G5 suite verte baseline (pytest exit 0)

**État 13 juin 2026** :
- G1 ✅ 84 résolus
- G3 ✅ 18 triggers `_no_delete` (alembic head 0059)
- G4 ✅ cure pattern #133bis BookLine appliquée
- **G2 🔴 ROUGE** : `SELECT count(*) FROM predictions WHERE target_date >= '2026-12-01' AND target_date <= '2027-12-31' = 0` ; `source_metadata_json LIKE '%sentinel%' = 0`. **Hypothèse 1 confirmée** : sentinelles spécifiées, jamais loggées. C'est le pattern L25 (gravé, jamais appliqué) — le chantier anti-L25 démarrerait par-dessus un L25 actif. **Action préalable** : `/predict ×10` (15 min) pour passer la barrière honnêtement.
- G5 ❓ à confirmer baseline pytest avant déclenchement Unité A.

---

## Décisions tranchées avant Unité B

Soulevées à la pose, **tranchées par Olivier 13/06**. Définissent ce qui entre dans le `content_hash` et la nature des comparateurs.

### Q1 — Périmètre du hash : DEUX chaînes, pas une

**Décision** : séparer `thesis_hash` et `levels_hash`, deux chaînes `prior_hash` distinctes dans la **même table**.

- **`thesis_hash`** = SHA-256 canonique sur `{claim, mechanism, invalidation, horizon}` — **pourquoi** tu détiens.
- **`levels_hash`** = SHA-256 canonique sur `{target, stop, sizing}` — **comment** tu gères.

**Conséquence opérationnelle** : un repose de niveaux (Hynix Régime A → `target=NULL` ; AVGO repose $492 + S10-S13) appende sur la chaîne `levels_hash`, **laisse `thesis_hash` intacte**. La table grossit, oui — c'est le coût de l'auditabilité. `direction` + type-de-chaîne rendent les sweeps filtrables.

**Bénéfice épistémique** : à la résolution, distinction propre entre « j'avais raison sur la thèse, j'ai mal géré les niveaux » et « la thèse était fausse ». C'est précisément la distinction prix ≠ preuve-de-thèse appliquée au schéma. Un seul hash mélangé efface cette distinction.

**Schéma table impacté** (vs chantier §B) :
- Ajouter `thesis_hash TEXT NOT NULL` + `levels_hash TEXT NOT NULL`
- Renommer `prior_hash` en `thesis_prior_hash` + ajouter `levels_prior_hash`
- Le champ `content_hash` du chantier §B disparaît au profit de cette paire.

---

### Q2 — Nulle 100% SOXX, jamais-rebalance, métriques duales

**Décision** : nulle = **100% SOXX, buy-and-hold littéral, jamais-rebalance**. Logger **brut (TWR) ET risk-adjusted (return/vol)**.

**Pourquoi pas 80/20 fixé** : SOXX 80% + cash 20% fige une exposition equity à 80%, alors que le book réel tourne ~96% investi. On comparerait des **bêtas différents** — la nulle gagnerait en risk-off pour de mauvaises raisons (moins exposée, moins de drawdown). Faussement flatteur.

**Pourquoi pas trimestriel** : rebalance vend les gagnants — donne à la nulle ton propre biais #1 en avantage cosmétique gratuit. Tu compares ta discipline à une nulle qui n'est plus paresseuse.

**Pourquoi 100% SOXX drift pur** : miroir le plus dur possible. Plus volatile que toi, oui — c'est précisément le point. Si tu ne bats pas 100% SOXX net de ton temps, le verdict doit pouvoir le dire crûment.

**Pourquoi métriques duales (brut + risk-adjusted)** : le brut répond « bat-on l'indexation ? ». Le risk-adjusted répond « bat-on l'indexation pour le risque qu'on prend ? ». Les deux comptent. Logger les deux dans `null_benchmark_nav` ou dériver à la lecture.

**Conséquence schéma** : table `null_benchmark_nav` stocke NAV brute ; le risk-adjusted se dérive à la lecture (`return / rolling_vol`). Pas besoin de colonne supplémentaire.

---

### Q3 — Deux labels orthogonaux par entrée, plus le détecteur a SA nulle

**Décision** : chaque entrée du seed Unité C porte **deux labels orthogonaux** :
- `narrative_profile` ∈ {`mécanisme`, `dérive`} — label du **contenu de la prose**, posé à la pose.
- `decision_outcome` — résolu plus tard (à 30/60/90j ou via résolution thèse Unité B).

**Le classifieur s'entraîne sur `narrative_profile`. Sa valeur se mesure en corrélant `narrative_profile` à `decision_outcome` sur le corpus accumulé.**

**Conséquence épistémique forte** : si « dérive narrative » ne corrèle à rien dans les outcomes, **le détecteur est du théâtre et on le coupe**. C'est sa propre nulle paresseuse. Le détecteur naît avec un kill-switch intégré, comme la Couche 0 a un kill-switch sur tout le chantier.

**Pourquoi c'est plus profond que de la clarté ADR** : les SpaceX×6 d'Olivier sont la donnée parfaite précisément parce que **la prose est dérive ET la décision est saine** (Olivier les a interceptées). Ce cas apprend au classifieur que dérive narrative ≠ mauvaise décision automatique — c'est un **signal précoce** que la décision risquerait de déraper si rien ne l'interceptait. Le détecteur ne prédit pas « cette décision est mauvaise » ; il prédit « cette prose a le profil qui, historiquement, précède une mauvaise décision **si rien ne l'intercepte** ». Sur SpaceX, ce qui a intercepté, c'est Claude.

**Schéma impacté** : Unité C produit des entrées avec `narrative_profile` figé à la pose + `decision_outcome` rempli à terme depuis le registre thèses (Unité B). Métrique de validation = corrélation `narrative_profile × decision_outcome` sur N≥20 entrées résolues.

---

## Lien avec doctrines existantes

- **L4 état découplé** : `thesis_registry` doit avoir son propre cycle d'état (`status` enum), pas réutiliser celui de `bias_events`.
- **L15 fail-closed scoring** : Unité C (narrative drift LLM) doit retourner `None` si LLM down, jamais score arbitraire.
- **L16 splits temporels** : si Unité C entraîne ses poids sur les thèses gagnantes/perdantes (cf §C ancrage empirique), splits train/val/oos pré-enregistrés dans `audit_metadata`.
- **L17 declarative YAML / live state DB** : config nulle (`SOXX 0.80, CASH 0.20`, rebalance) en YAML versionné ; NAV en DB append-only.
- **L21 QUALITY_BAR** : tout datum du registre = triple (valeur, asof, source). Hash = preuve tamper-evident.
- **L24 walking skeleton** : Unité B doit poser un tracer-bullet (1 thèse réelle backfillée) AVANT tests purs supplémentaires.
- **L25/L26 append-only doctrine** : extension explicite aux thèses, pas seulement données.
