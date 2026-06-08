# PRESAGE — Operational Readiness (la base, rendue mesurable)

> « Rendre la base opérationnelle au niveau qu'on veut » = faire passer au **vert** un check exécutable, pas atteindre un ressenti. Ce doc définit `scripts/base_health.py` : l'instrument qui note l'opérabilité de la base elle-même. **La base est opérationnelle quand ce run est vert.** Ni avant (auto-illusion), ni « jamais assez » (perfectionnisme). Falsifiable, donc fini-able.

## Principe

QUALITY_BAR a posé 3 mécanismes (M1 fraîcheur, M2 claims pré-enregistrées, M3 sizing-sur-edge) + fail-closed. « Opérationnel » signifie que ces invariants sont **enforced + running + observable**, automatiquement, le système refusant de les violer. `base_health.py` évalue chaque dimension → `GREEN / AMBER / RED` + raison une ligne, exit non-zéro si un `RED`. Lancé : (a) quotidien dans le spine, (b) en tête de `morning_brief`, (c) partiellement en CI. Le `RED` est l'événement — pas le contenu marché.

## Définition-de-fait — les checks (= le spec de `base_health.py`)

| Dim | Check concret (source) | Vert quand | Statut HONNÊTE aujourd'hui |
|---|---|---|---|
| **Positions vérité** (axe 3) | aucune position avec `eur_value` dans `notes` ; toute ligne ouverte a `last_price_native`+`price_asof` typés ; PEA valorisé comme CTO | état présent exact dérivé live | 🔴 `eur_value`-dans-`notes`, snapshots 15j, PEA sans valeur |
| **Fraîcheur data** (M1) | as-of le plus vieux du book < SLA (15min/1h) ; chaque prix = triple `(val, asof, source)` ; 0 import `yfinance` hors `prices.py` | « live » honnête, jamais nu | 🔴 19 bypass yfinance, snapshots figés |
| **Intégrité chaîne** (M2) | `verify_chain(get_prediction_integrity_chain())` OK ; dernier ancrage OTS < 25h ; chaîne non-vide | tamper-evident + ancré trustless | 🟠 code livré, bootstrap non lancé, OTS pas wire opér. |
| **Couverture claims** (M2) | `count(predictions) == count(prediction_integrity_log)` | toute prédiction est pré-enregistrée | 🔴 hook non mergé, 219 non chaînées |
| **Edge & sizing** (M3) | régime sizing = `construction` tant que N_résolu<100 ; `run_stress_test("AI capex -30%")` drawdown < seuil NAV ; ligne ballast ≥ cible | risque sizé pour survivre à la ruine | 🔴 conviction-weighted, 95% single-factor, 0 ballast |
| **Santé boucle** | resolver last-run < 25h ; 0 prédiction past-due non-résolue ; chaque step du spine a un last-run/latence | boucle fermée tourne unattended | 🟠 resolver OK (0 past-due ✅), spine fragmenté crons/+jobs/ |
| **Marqueurs dégradés** (fail-closed) | aucun score en mode dégradé non-marqué ; aucun nombre rendu sans as-of | le système n'imite jamais le sain | 🟠 honest-marker existe (ADR-014), pas partout |
| **Progression N** (temps) | N_résolu vs 100 ; affiché « warm-up » si < 100 | honnêtement en warm-up, **pas un échec** | 🟢-honnête 35/100, gaté par le temps |

> Lecture : la base est aujourd'hui majoritairement 🔴. C'est ça, la réponse honnête à « est-elle opérationnelle » — tu as la doctrine et les pièces, presque aucun check ne passerait. Le travail = virer chaque rouge, dans l'ordre de dépendance.

## Les 4 organes de l'opérabilité (ce que « enforced/running/observable » veut dire concrètement)

1. **Un spine unique** (running). Consolider `crons/` + `bot/jobs/` en UNE séquence quotidienne ordonnée : ingest → score → pré-enregistre+ancre → résout les dues → attribue → snapshot → `base_health`. Chaque step écrit une ligne télémétrie (last-run, ok/fail, latence) dans une table append-only (étendre `bot_events`/`handler_calls`). Un step qui échoue marque **dégradé**, ne saute jamais en silence.
2. **Enforcement runtime, pas que CI** (enforced). M1 : `prices.get()` retourne le triple + garde de staleness qui fail-close le scoring sur prix périmé. M2 : funnel unique `insert_prediction` + hook intégrité (déjà écrit) → auto-pré-enregistrement. M3 : le sizing **lit** le régime depuis `config/target_allocation.yaml` ; le stress-test **gate** quotidiennement.
3. **Une surface santé-base** (observable). `base_health` rend un cockpit unique répondant « la base est-elle saine maintenant ? » — fraîcheur, intégrité+âge ancrage, santé boucle, N, risque book. Tout porte son as-of. C'est la première chose que tu vois le matin.
4. **Le rituel** (le prouve). `morning_brief` mène avec santé-base avant tout contenu marché : base 🔴 = titre du jour. Pas de lecture marché sur une base cassée — elle propagerait l'erreur avec élégance.

## Chemin critique (ordre de dépendance, pas d'envie)

0. **`base_health.py` D'ABORD** — le tableau de score. Te donne la baseline rouge et rend chaque progrès visible (tu regardes les checks virer au vert). Construire l'instrument de mesure de la base *avant* de réparer la base = cohérent avec « auditable par un adversaire » appliqué à soi.
1. **Positions vérité (axe 3)** → débloque Fraîcheur. Deux dimensions au vert. *Le plus fondamental, tout lit cet état.*
2. **Bootstrap intégrité + hook + cron OTS** → Intégrité + Couverture claims au vert. (Code déjà livré, reste à lancer/wire.)
3. **Sizing construction + stress-gate + ballast** → Edge au vert. *Le risque qui ruine avant que la calibration arrive.*
4. **Consolider le spine + télémétrie** → Santé boucle au vert.
5. **Marqueurs dégradés partout** → fail-closed généralisé au vert.

## La règle d'arrêt (anti-perfectionnisme, gravée)

Quand `base_health` est **tout-vert sauf N** (qui ne devient vert qu'avec le temps + les sondes 7j), **la base EST opérationnelle**. On arrête de construire la base. On l'utilise. Ne jamais laisser un N-pas-encore-vert (parce que jeune, pas parce que cassé) prolonger indéfiniment le « je peaufine la base ». La base opérationnelle n'est pas parfaite — elle est *verte sur ce qui est atteignable maintenant, et honnête sur le reste*.

---

### Geste immédiat
`scripts/base_health.py` : 8 checks ci-dessus, chacun `GREEN/AMBER/RED` + raison, exit non-zéro si RED. C'est l'instrument qui transforme « opérationnelle au niveau qu'on veut » en un run vert/rouge. Une fois écrit, l'ordre de réparation est mécanique : on suit les rouges.
