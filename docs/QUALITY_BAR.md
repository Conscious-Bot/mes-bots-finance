# PRESAGE — QUALITY BAR (la base non-violable)

**Figé** : 07/06/2026 nuit (red-team meta-doctrine).
**Source de vérité unique** sur le contrat d'acceptation. Pas de re-formulation ailleurs.

## La base en une phrase

> Un hedge fund n'a pas raison plus souvent — il ne se ment jamais sur son edge, sa data, ou son risque. On copie ça, pas la perfection.

« Le meilleur possible » = le maximum atteignable sans jamais surévaluer ce qu'on a. La qualité institutionnelle n'est pas une data parfaite (inatteignable, solo, 26 jours, N=35, data gratuite) — c'est le **refus du système de présenter un nombre plus confiant que son évidence**. Tout le reste (intégrité, calibration, sizing) sert ça.

## Les 3 mécanismes d'exécution (le « comment », valables sur TOUS les axes)

### M1 · Tout datum est un triple, jamais un scalaire
`(valeur, as_of, provenance)`. Un prix nu est interdit. `prices.get()` retourne `(price, asof, source)`. Toute query positions retourne son `price_asof`. Toute surface UI affiche la fraîcheur.
**Opérationnalise** : data fidèle (axe 2), live honnête (axe 5), métriques bien jugées (axe 5).

### M2 · Toute claim est pré-enregistrée, falsifiable, bornée par un horizon
Pas d'opinion sans `(direction, proba, horizon, baseline)` figé tamper-evident (ledger d'intégrité + predictions).
**Opérationnalise** : positions/futurs propres (axe 3), timing honnête (axe 1).

### M3 · Toute taille respecte l'edge prouvé, pas la conviction affirmée
À `N_résolu < 100`, l'edge est inconnu → sizing **sous-Kelly** (compresser le spread de conviction), ballast obligatoire, stress-test comme gate dure.
**Opérationnalise** : gestion pro concentration/sizing/cluster/ballast (axe 4).

### Méta · Fail-closed (L15 généralisé)
Quand M1/M2/M3 ne peuvent être satisfaits (data stale, edge non-prouvé, chaîne cassée) → le système affiche **dégradé** ou **refuse**, jamais ne **fabrique**. C'est le cœur de la base.

## Les 5 axes — état / cible / « fait quand » / garde-fou / 1er geste

### Axe 1 — Analyses & timing : calibré et asymétrique (PAS « parfait »)
- **Cible** : connaître son hit-rate honnêtement + jouer l'asymétrie (payé plus si raison que perdu si tort). Le timing parfait est l'erreur retail que l'instrument corrige (lock_in).
- **Fait quand** : chaque thèse a `target_partial/full` + invalidation chiffrés ; ratio gain-si-raison / perte-si-tort calculé et affiché ; hit-rate sort du ledger, pas d'une impression.
- **Garde-fou** : aucun nombre de proba présenté sans son N et son IC. À N<100, marqué « warm-up ».
- **1er geste** : déjà en cours (ledger d'intégrité + sondes 7j). Ne rien ajouter de calibration (invariant N<100).

### Axe 2 — Lecture du marché : inputs fidèles, lecture explicitement incertaine
- **Cible** : data fidèle (prix/fondamentaux/filings) + lecture taggée incertaine. On ne confond jamais « j'ai de la data exacte » et « je sais ce que le marché fera ».
- **Fait quand** : chaque signal porte sa source + as-of ; lecture sort comme distribution, pas point.
- **Garde-fou** : la monoculture newsletter (76 sources = cohorte macro corrélée) est nommée comme telle ; deux sources qui s'accordent toujours ne comptent pas pour deux. Ce n'est pas une lecture du marché, c'est une lecture d'une cohorte narrative.
- **1er geste** : pondérer down par corrélation inter-sources ; privilégier l'orthogonal déjà là (EDGAR, insider) sur le narratif.

### Axe 3 — Positions, historique, futurs : présent propre maintenant, futur = attente pré-enregistrée
- **Cible** : état présent exact et daté ; le « futur » n'est pas une connaissance mais une attente falsifiable (M2).
- **Fait quand** : `eur_value`-dans-`notes` est mort → colonnes typées `last_price_native, fx_asof, price_asof` ; la valeur est dérivée live (`qty × prix × fx`), jamais stockée figée ; lignes PEA ont leur prix comme les CTO ; chaque ligne expose son as-of ; 17 backups DB → 1 politique de rétention.
- **Garde-fou** : toute valeur de position > X min affichée en grisé/stale. Jamais un total agrégé sur des as-of hétérogènes sans le dire.
- **1er geste — LE FONDATIONNEL, à faire en premier** : tuer la dénormalisation `eur_value/notes`, colonnes typées + 1 job de réconciliation unique via `prices.get()`. Tout lit cet état ; il est cassé aujourd'hui.

### Axe 4 — Concentration / sizing / cluster / ballast : sous-Kelly + vrai ballast (le risque de ruine)
- **Cible** : sizing qui respecte l'edge non-prouvé ; concentration intentionnelle sizée pour survivre à la ruine.
- **Fait quand** : (a) sizing-régime construction dans `config/target_allocation.yaml` — spread de conviction compressé (vers quasi-équipondéré intra-cluster) tant que N<100, ré-élargi quand la calibration le mérite ; (b) ligne ballast définie (cash / décorrélé / hedge de queue) + `factor_exposures` exige le ballast et flag quand < cible ; (c) stress-test = gate dure : si `run_stress_test("AI capex -30%")` → drawdown > seuil NAV, le book est sur-concentré → alerte (pattern monitor).
- **Garde-fou** : le book est 95% single-factor AI-capex, zéro ballast. C'est la config qui a tué Archegos/Tiger 2022. Ne pas sizer sur conviction avant d'avoir prouvé l'edge = surconfiance mécanisée.
- **1er geste** : câbler le stress-test existant à un seuil + une alerte (la machinerie existe, l'alerte non) ; puis définir la cible ballast.

### Axe 5 — Métriques & data : near-live + fraîcheur en métrique de 1re classe (PAS « constamment live »)
- **Cible** : « live » honnête. Sur data gratuite tu es throttled/single-source/ban-prone — le « live » hedge-fund est un feed payant redondant SLA'd. On ne prétend pas live, on mesure la fraîcheur.
- **Fait quand** : gate CI `yfinance` uniquement dans `prices.py` (tue le SPOF des 19 call-sites) ; `prices.get()` retourne le triple M1 ; panneau « data health » = as-of le plus vieux du book + source + # stale ; SLA staleness (vert <15min / ambre <1h / rouge+flag au-delà).
- **Garde-fou** : aucun nombre rendu sans son as-of. Un nombre stale est marqué stale, jamais présenté comme frais.
- **1er geste** : la gate CI + le triple dans `prices.get()`. Décision à trancher : payer un feed (Polygon/Tiingo) pour un vrai live, ou assumer near-live+staleness. Recommandation : assumer near-live tant que single-user ; payer quand pro/multi-tenant.

## Séquence (par atteignabilité, pas par envie)

1. **Axe 3 présent** — positions propres + as-of (fondationnel, cassé, tout en dépend).
2. **Axe 5** — fraîcheur-métrique + gate CI (rend M1 réel partout).
3. **Axe 4** — stress-gate + ballast + sizing construction (le risque qui ruine avant la calibration).
4. **Axe 2** — orthogonalité des sources (améliore la lecture, mais gatée par la calibration).
5. **Axe 1** — calibration/timing (gatée par le temps ; ne PAS forcer, invariant N<100).

## Invariant transverse (à graver)

> Le système a le droit de dire « je ne sais pas / c'est stale / mon edge n'est pas prouvé ». Il n'a jamais le droit de présenter un nombre plus confiant que son évidence. La volonté de montrer sa propre ignorance est la qualité hedge-fund-worth — et c'est la seule qui convainc un adversaire.

## Référencer

Source unique : `docs/QUALITY_BAR.md`. Pas de re-formulation ailleurs. Pointage depuis `CLAUDE.md` « Catches récurrents » + L21 LESSONS pour les 3 mécanismes. Toute décision PRESAGE qui contredit cette base = revue à zéro.
