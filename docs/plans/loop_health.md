# ============================================================
# Loop-Health Canaries — Spec & Plan d'implémentation
# ============================================================
# Statut : spec figée, build à froid. Date : 2026-05-25 (Day 15 suite).
# Triggers : Step 0 + Step 2 buildables maintenant ; Step 1 (C1) s'arme à
#            N>=20 résolues post-fix (~semaines) ; Step 3 (C4) ~été ; C5 jamais.

## 1. Pourquoi

Le système instrumente ses *opérations* (handler_stats, llm_costs, uptime) mais
pas la *santé du chemin de valeur* — la boucle signal -> prior -> résolution ->
Brier -> crédibilité. C'est précisément ce trou qui a laissé `estimate_probability`
émettre 0.5 sur ~95% des prédictions pendant des semaines (Brier plafonné à 0.25,
KPI#3 inatteignable par construction) sans qu'aucun voyant ne s'allume. Les canaris
sont l'observabilité de cette boucle.

## 2. Frontière honnête (à lire AVANT de coder)

`/loop_health` est un capteur de **vie, pas de correctness**. Il attrape les
pathologies de données (~la moitié de ce qu'on a trouvé au Day 15), **jamais les
misconceptions** (divergence des deux writers de crédibilité, tests creux — la
moitié de plus grande valeur, qui ne se trouve qu'à la trace sceptique).

Danger : un `/loop_health` vert qui fait croire que la tuyauterie est saine =
récursivement le piège tableau-de-bord-vert-au-dessus-d'une-fonction-morte. Donc
le handler doit être **étiqueté liveness**, et la trace manuelle périodique reste
le vrai audit. Aucun script ne remplace l'esprit qui demande "est-ce que ça fait
vraiment ce qu'on croit ?".

Méthode durable (capture le Day 15) : suivre la valeur pas le code ; vérifier ne
pas réciter (3 docstrings mentaient) ; tracer chaque saut write->transform->consume ;
signature de panne = "bonne forme, substance creuse" ; test discriminant = "une
version cassée passerait-elle quand même ?".

## 3. Architecture

Deux couches, pas un framework (un framework serait la prochaine forme creuse) :
- Pathologies de données -> handler `/loop_health` à la demande, états
  OK / WARN / NOT_MEASURABLE (le warmup ne crie jamais au loup).
- Invariants structurels -> tests CI (déterministes, pas de data live).

Décision de design centrale : **séparer FETCH de ASSESS.**
- `shared/storage.py` calcule les stats descriptives (data, déterministe).
- `intelligence/loop_health.py` applique les *seuils* (policy) et rend un verdict,
  en fonctions PURES.
Conséquence : les `assess_*` se testent par `assert assess_X(input_cassé).state == "WARN"`
— sans DB, triviaux, infalsifiables. Même pattern que estimate_probability + son
property test. La rigueur méta devient gratuite, donc non-esquivable.

Insight deux-capteurs : le test `test_dynamic_range_over_support` garde l'amplitude
de la *fonction* (régression code, CI). Le canari C1 garde la *distribution réalisée*
(qui peut s'effondrer même avec une fonction saine, si les intrants dérivent). Deux
origines de panne, deux capteurs — pas redondant.

Accès DB exclusivement via storage.py (CONVENTIONS rule 5).
`intelligence.loop_health` rejoint l'override mypy strict (logique pure).

## 4. Canaris — spec complète

### C1 — Différenciation du prior  [KEYSTONE, garde le fix du Day 15]
- Cible : régression dead-range de estimate_probability.
- Signal : sur predictions created_at >= now-30j ET probability_at_creation NOT NULL :
  stddev, fraction modale, spread [min,max].
- Seuil : WARN si stddev < 0.02 OU fraction_modale > 0.80. C'est un PLANCHER, pas
  une bande : quand la crédibilité s'activera (post-recal), le spread S'ÉLARGIRA —
  ne pas alarmer là-dessus. Justif empirique : état cassé = modale 0.95 / stddev
  ~0.006 ; état sain actuel = stddev ~0.04-0.06.
- États : NOT_MEASURABLE sous 20 prédictions post-fix.
- Faux positif : semaine calme tout-signaux-faibles peut resserrer -> mitigé N>=20
  + fenêtre 30j. Faux négatif assumé : détecte l'EFFONDREMENT, pas la mauvaise
  calibration (capteur de vie, pas de qualité).

### C2 — Intégrité de résolution  [cheap, toujours mesurable]
- Cible : un resolve qui résout sans calculer le Brier (track record silencieusement NULL).
- Signal : COUNT(resolved_at NOT NULL AND outcome IN ('correct','incorrect')
  AND probability_at_creation IS NOT NULL AND brier_score IS NULL). Doit être 0.
- Exclusions CRITIQUES (le spec du canari EST ces exclusions) : neutral a un Brier
  NULL légitime (brier_for non-binaire) ; la legataire id=1 NVDA a prob NULL ->
  Brier NULL légitime. Sans ces deux exclusions, le canari hurle sur du sain et
  devient le bruit qu'on ignore. État actuel : 0 = OK.

### C3 — Tables orphelines  [RAPPORT, pas alarme]
- Cible : table fantôme (calibration, rows=0 jamais câblée) + tables débranchées.
- Sous-checks : (a) empty après >30j d'opération -> candidat "jamais câblé" ;
  (b) stale (rows>0, max(ts) >30j) -> "table débranchée". Liste de REVUE (jugement
  humain — patterns vide est légitime, Phase 5), pas un WARN binaire.
- Read-orphan (alimentée mais jamais lue) : NON automatisable proprement (queries
  dynamiques, f-strings) -> reste un grep semi-manuel dans la méthode.

### C4 — Liveness crédibilité  [DIFFÉRÉ ~été]
- Cible : bras retour mort (recal qui ne tire pas malgré la data).
- Signal : WARN si une source a >=10 résolues-brier ET credibility == 0.5 EXACT
  (untouched ; le recal écrit un float computé, jamais 0.5 pile -> distinguable).
- NOT_MEASURABLE pendant des mois. Ne PAS construire maintenant (code qui dort).
  Trigger : première source approchant N=10 résolues-brier.

### C5 — Cohérence doc<->schéma  [NON CONSTRUIT]
- Le code est couvert (test_schema_drift, test_sql_observability). Le gap = queries
  documentées (KPI_DASHBOARD, colonne morte). Extraction depuis markdown = fiddly
  pour valeur marginale. Action : fixer KPI_DASHBOARD une fois, point.

## 5. Signatures

shared/storage.py (FETCH, typé) :
    def prior_distribution_stats(days: int = 30) -> dict[str, Any]
        # {"n","stddev","modal_fraction","min","max"}
    def resolution_integrity_count() -> int
    def credibility_liveness(min_n: int = 10) -> dict[str, Any]
        # {"measurable": bool, "stuck": list[str]}
    def table_population_report(stale_days: int = 30) -> list[dict[str, Any]]
        # par table: {"table","rows","max_ts","empty","stale"}

intelligence/loop_health.py (ASSESS, pur, typé) :
    PRIOR_STDDEV_FLOOR = 0.02
    PRIOR_MODAL_CEIL   = 0.80
    PRIOR_MIN_N        = 20
    CRED_LIVENESS_MIN_N = 10
    class CanaryResult(TypedDict): name: str; state: str; detail: str
        # state in {OK, WARN, NOT_MEASURABLE}
    def assess_prior_differentiation(stats: dict) -> CanaryResult   # C1, pur
    def assess_resolution_integrity(broken: int) -> CanaryResult    # C2, pur
    def assess_credibility_liveness(data: dict) -> CanaryResult     # C4, pur
    def run_all() -> list[CanaryResult]   # SEULE fn DB-touchante: fetch -> assess

bot/handlers/observability.py (folder dans l'existant, "moins de surface") :
    async def cmd_loop_health(update, ctx)  # run_all() + table report -> Telegram

## 6. Tableau des seuils (tunables, documentés dans le module)

| Canari | Métrique | WARN | NOT_MEASURABLE si | Panne captée |
|---|---|---|---|---|
| C1 | stddev / modal_fraction prior 30j | stddev<0.02 OU modal>0.80 | n<20 post-fix | estimateur mort / intrants effondrés |
| C2 | resolved non-neutres prob-set brier-NULL | >0 | jamais | resolve sans Brier |
| C3 | tables empty / stale | report | — | table fantôme / débranchée |
| C4 | sources >=10 résolues-brier à cred 0.5 pile | >=1 | aucune source à N>=10 | bras retour mort |

## 7. Séquence (3 patchs gatés + 1 différé)

STEP 0 — Scaffold + C2  [buildable maintenant ; prouve la chaîne end-to-end]
  - loop_health.py : CanaryResult, constants, run_all() (registre=[C2]),
    assess_resolution_integrity.
  - storage.py : resolution_integrity_count().
  - observability.py : cmd_loop_health + format.
  - main.py : register /loop_health.
  - test_loop_health.py : C2 broken (résolue prob-set/brier-NULL -> WARN) +
    healthy (0 -> OK) + exclusions (legataire/neutral ne trippent pas).
  - Gate : ruff + mypy intelligence/loop_health.py shared/storage.py
           + python -c "import bot.main" + pytest -q + commit.

STEP 1 — C1 différenciation  [keystone ; ship NOT_MEASURABLE, s'arme à N>=20]
  - storage.py : prior_distribution_stats(days).
  - loop_health.py : assess_prior_differentiation (seuils PRIOR_*) + registre.
  - test_loop_health.py : broken (stddev 0.005/modal 0.95 -> WARN) +
    healthy (stddev 0.05 -> OK) + insufficient (n<20 -> NOT_MEASURABLE).
  - Gate idem.

STEP 2 — C3 rapport tables  [buildable maintenant ; section revue]
  - storage.py : table_population_report(stale_days).
  - observability.py : section "tables à revoir" (empty/stale).
  - test_loop_health.py : report avec une empty + une stale -> présentes en sortie.
  - Gate idem.

STEP 3 — C4 liveness crédibilité  [DIFFÉRÉ — trigger: 1re source >=8 résolues-brier]
  - storage.credibility_liveness + assess_credibility_liveness + registre + test
    broken (source stuck -> WARN) + recal-vers-~0.5 ne trippe pas (float != 0.5).

## 8. Le non-négociable

Aucun assess_* ne ship sans son test broken-trips dans le MÊME patch : on lui
injecte l'état pathologique exact (il doit hurler), l'état sain (il doit se taire),
le warmup (NOT_MEASURABLE). Le découplage FETCH/ASSESS rend ces trois assertions
gratuites -> zéro excuse. Instrumenter l'instrument, ou c'est de la décoration —
le piège "monotone-mais-plat" du Day 15, appliqué récursivement.

## 9. Coût & surface

LLM : zéro (SQL + stats pures). Surface : +1 module logique, +4 fns storage,
+1 handler folder dans observability, +1 test file, +1 registration main.py.
À froid : Step 0+1+2 ≈ 2-3h, un patch gaté chacun, dans l'ordre.
Binding constraint = temps-jusqu'aux-résolutions, pas le code.
