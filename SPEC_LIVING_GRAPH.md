# Spec LIVING GRAPH — le DAG des Datums devient une boucle vivante

> Le socle a posé `Datum.parents` à V0 : **le graphe de lignage existe déjà**, latent dans chaque nombre du système. Le living graph est ce qu'on en fait quand on le **matérialise** + on l'**interroge**. Trois capacités self-* tombent gratuitement : auto-auditant (provenance forward), auto-correcteur (feedback arrière via parents), auto-cohérent (forks détectés live). Pas un nouvel étage — l'exploitation du substrat déjà présent.

## 0. L'idée maîtresse

Le `Datum` ([[SPEC_SOCLE]] §1) a déjà la structure d'un nœud Merkle-DAG : `id = hash(value, asof, source, parents, op)`. Quand `derive()` propage, chaque dérivation pointe vers ses parents via leur content-hash. **Le lignage complet de chaque fait du système existe donc déjà** — il flotte juste, non-matérialisé, jamais interrogé.

Le living graph se construit en couches **ordonnées par valeur livrée**, pas par complétude du tableau. La **V0 est lean** : juste ce qu'il faut pour mécaniser L29. Le reste vient quand le besoin se manifeste.

**V0 (le strict minimum qui mécanise L29) — indexer par concept + détecter les forks** :

Un Datum peut représenter "le PMP roulant de SK Hynix au 09/06 17h22" — mais plusieurs chemins de calcul (BookLine, VUE SQL, helper Python) peuvent prétendre calculer **le même fait sémantique**. La table `concept_index` mappe `(concept_key, ticker, asof_bucket) → [{value, source, op}, ...]` avec **les valeurs inline** (pas de FK vers un log généraliste). Quand ≥ 2 valeurs **divergent au-delà de la tolérance ε du concept** dans la même bucket → **fork détecté en live**. C'est tout ce qu'il faut pour tuer la classe de bug L29.

**V1+ (vision permise par le substrat, à construire quand le besoin se manifeste)** :

- **Matérialiser** le DAG complet (`datum_log` append-only) pour permettre `trace_parents` (debug provenance bidirectionnelle). Différé car (a) `shared/integrity.py` couvre déjà la tamper-evidence des chaînes critiques (predictions+theses) et (b) logger ~500 Datums/regen exige profil/batch (cf §7) — pas de bénéfice V0.
- **Auto-auditant** (provenance forward via `trace_parents`) — utile quand un consumer veut expliquer un chiffre.
- **Auto-correcteur** (feedback arrière) — utile quand quelqu'un signale "ce nombre ne fait pas sens".

**La conséquence vivante V0** : L29 ("corriger calcul ≠ vérifier diffusion") devient mécanisé **immédiatement**. Le fork PMP roulant BookLine vs VUE SQL aurait été **détecté automatiquement** dès la divergence apparue, sans que quelqu'un re-grep tous les consumers à la main. La discipline humaine "vérifier la diffusion à chaque chemin" devient une propriété structurelle — **avant qu'on construise quoi que ce soit d'autre**.

> Le socle pose les briques (Datum + parents). Le living graph les fait parler. Auto-auditant, auto-correcteur, auto-cohérent — pas par convention, par construction.

## 1. Pré-conditions (rappel discipline)

- **base_health vert** : positions-vérité + fraîcheur + chaîne intègre + OTS. Acquis 09/06 soir tard ([[SPEC_SOCLE]] §4).
- **`Datum.parents` capturés à la naissance** : si les gateways oublient de chaîner, le graphe a des trous. Vérifié via test serrure (cf §8).
- **`derive()` est la seule porte de propagation** : pas de Datum dérivé sans passer par `derive()` (sinon parents=()). Gate existant.

Sans ces 3 conditions, le living graph travaille sur un substrat troué — il ment par omission. C'est pourquoi le SPEC n'est gravé qu'après base_health vert (cf [[L25]] anti-pattern "graver sur fondation cassée").

## 2. Architecture V0 (tables + helpers strictement minimaux)

V0 = une table, deux helpers. Pas plus. Le `datum_log` (substrat de `trace_parents`) est explicitement V1+ — pas en V0.

```
concept_index (append-only, valeurs INLINE — pas de FK vers un log généraliste)
├── concept_key      TEXT     -- 'pmp_eur', 'value_eur', 'fragility', ... (registre)
├── ticker           TEXT     -- scope (NULL si concept global)
├── asof_bucket      TEXT     -- bucket temporel (per-concept override possible)
├── value            REAL     -- la valeur inline (le fait que les chemins prétendent calculer)
├── source           TEXT     -- 'BookLine', 'sql_view', 'helper:ledger_pmp', ...
├── op               TEXT NULL -- nom op (audit)
├── degraded         INT      -- 0|1 (propagé du Datum d'origine)
├── confidence       REAL     -- 0..1
├── logged_at        TEXT     -- now() à l'insert
└── PRIMARY KEY (concept_key, ticker, asof_bucket, source)
```

PK composite `(concept, ticker, bucket, source)` : un même source enregistré 2× dans la même bucket = UPSERT (idempotent). Deux sources distinctes = deux rows = candidat fork.

**Helpers V0** (`shared/living_graph.py`) :

```python
def register_concept(
    concept_key: str,
    value: float,
    source: str,
    ticker: str | None = None,
    asof_bucket: str | None = None,
    op: str | None = None,
    degraded: bool = False,
    confidence: float = 1.0,
) -> None:
    """Lie une valeur+source à un concept sémantique. asof_bucket default = jour ISO.
    Idempotent via UPSERT (concept, ticker, bucket, source)."""

def detect_forks(asof_bucket: str | None = None) -> list[dict]:
    """Scan concept_index pour la bucket donnée (default aujourd'hui).
    Retourne [{concept_key, ticker, bucket, candidates: [{value, source, op}, ...]}]
    pour chaque tuple où len(values_distincts) ≥ 2 ET divergence > ε du concept.
    Vide = aucun fork. Appelé au regen-end (cf §4), pas en cron séparé."""
```

**Helpers V1+** (vision, à NE PAS construire en V0) :

```python
# V1+ uniquement quand le besoin se manifeste (debug provenance bidirectionnelle)
def log_datum(d: Datum) -> None: ...
def trace_parents(datum_id: str, max_depth: int = 5) -> list[dict]: ...
```

**Tolérance ε par concept** (`config/concept_keys.yaml`, gravé W1 mais le schéma figé V0) :

```yaml
concepts:
  pmp_eur:
    description: "PMP roulant fiscal FR en EUR"
    asof_bucket: day        # granularité bucket
    epsilon_rel: 0.001      # 0.1% — PMP doit être exact, micro-diff = fork
  value_eur:
    asof_bucket: day
    epsilon_rel: 0.005      # 0.5% — peut tolérer micro-jitter FX intra-regen
  pnl_position:
    asof_bucket: day
    epsilon_rel: 0.005
  fragility:
    asof_bucket: day
    epsilon_rel: 0.05       # signal qualitatif, tolère 5%
```

ε par concept = **anti-cry-wolf appliqué au checker lui-même**. Deux producteurs qui calculent `pmp_eur` à 1s d'écart dans le même regen peuvent diverger d'un epsilon de timing — pas un vrai fork. Le checker qui crie au loup sur du jitter float viole la doctrine d'alarme qu'il est censé incarner. **Les vrais forks sont GROS** (PMP Tesla +2%, le cas L29 09/06) ; **le bruit est minuscule** (<0.01%). La tolérance ε filtre l'un sans masquer l'autre.

## 3. Trois capacités self-* (V0 livre la 3e seulement)

Le substrat **permettra** les trois, mais V0 livre **uniquement l'auto-cohérence** — c'est celle qui mécanise L29. Les deux autres sont la vision V1/V2.

### 3.1 Auto-auditant (provenance forward) — V1+

Tout consumer peut demander "d'où vient ce nombre" via `trace_parents(d.id)`. Le DAG donne la chaîne complète : gateway origine → derivations intermédiaires → résultat affiché. Transparence du calcul, accessible à la demande.

**Statut V0** : NON livré. Requiert `datum_log` matérialisé (V1+). Le DAG existe déjà dans `Datum.parents` (en mémoire), mais V0 ne le persiste pas — pas de bénéfice immédiat justifiant le coût ~500 INSERT/regen + un 2e substrat à côté de `shared/integrity.py`.

### 3.2 Auto-correcteur (feedback arrière) — V2+

Quand un panneau affiche une valeur suspecte, `trace_parents` remonte le DAG et flag les nœuds `degraded=True` ou `confidence < seuil`. Le coupable est trouvé sans grep.

**Statut V0** : NON livré. Requiert `datum_log` + helper `trace_parents` (V2+). Vision claire, pattern défini, exécution différée jusqu'au moment où le besoin se manifeste concrètement.

### 3.3 Auto-cohérent (forks détectés live) — **V0 LIVRE CECI**

C'est le geste qui matérialise L29. `register_concept` est appelé par les producteurs canoniques (BookLine, VUE SQL, helpers Python) avec le même `concept_key` ("pmp_eur" par ex.). **`detect_forks` est appelé au regen-end** (cf §4 W0) — pas un cron séparé. Le regen EST le battement : si les producteurs viennent de tourner et publié leurs valeurs, c'est **immédiatement** que la cohérence doit être vérifiée, pas 5 minutes plus tard par un scan désynchronisé. Comme `base_health`.

Sur fork détecté (au-delà de ε du concept) :

- **Telegram alert OPS** (analogue L29 fail-loud OTS) : "fork pmp_eur SK Hynix 09-06 : BookLine=45.21 vs VUE=44.83 (Δ=0.85%)"
- **Surface `base_health`** : 4e dimension "cohérence" passe RED tant que fork ouvert (W3, cf §4)
- **Décision humaine** : qui est juste, suppression du chemin faux (ou fail-closed NULL du chemin faux)

**Ce n'est pas une auto-résolution magique** — c'est la **détection automatique** + **alerte loud** d'un fait qui aurait sinon dormi. La décision reste humaine, mais le silent-drift est tué. **Anti-pattern à bannir** : auto-résolution machine (cf §5).

## 4. Build sequence (walking-skeleton, fixture réelle d'abord — L24)

**Geste fondateur (W0, tracer-bullet PMP — lean, no datum_log)** :
- Migration alembic : crée table `concept_index` SEULE (avec value inline). PAS `datum_log` (différé V1+).
- `shared/living_graph.py` minimal : `register_concept` + `detect_forks` SEULS. Pas de `log_datum`, pas de `trace_parents`.
- **Registre concepts** : `config/concept_keys.yaml` gravé avec `pmp_eur` minimum (epsilon_rel=0.001, asof_bucket=day).
- **Tracer-bullet PMP** : modifie `shared/ledger_pmp.py` pour `register_concept("pmp_eur", value, source="ledger_pmp", ticker=tk)` sur chaque calcul. Si VUE SQL helper PMP existe encore, idem `source="sql_view"`.
- **Regen-end hook** : `dashboard/render.py` (ou `serve.py` post-regen) appelle `detect_forks()` après que tous les producteurs aient tourné. Si forks > 0 → log + Telegram alert OPS. **Pas un cron 5min séparé** — le regen EST le battement.
- Test serrure : INSERT manuel de 2 rows divergents même concept_key au-delà de ε → `detect_forks` retourne 1 fork. INSERT de 2 rows divergents en-deçà de ε → 0 fork (anti-cry-wolf vérifié).
- **Si W0 marche** : on a la preuve par construction que le pattern fonctionne sur le cas exact qui a saigné (L29 09/06).

**W1** : étend aux concepts critiques restants — `value_eur`, `weight_pct`, `pnl_position`, `current_price_eur`. Producteurs canoniques (BookLine, helpers, panneaux) `register_concept` à leur point de naissance. Pas de nouveau substrat — c'est juste plus de concepts dans le registre.

**W2 (vision, à NE PAS faire avant besoin)** : `datum_log` + `log_datum` + `trace_parents`. Profil perf préalable (cf §7) pour décider batch ou async. Helper `/datum_trace <id>` Telegram pour debug live.

**W3** : `base_health` gagne une 4e dimension "cohérence live". RED si forks ouverts > 0 sur les concepts critiques. Gate de ship. (Indépendant de W2 — exploitable directement post-W1.)

**W4 (FUTURE post-cornerstone-macro)** : feedback arrière automatique sur signaux de l'utilisateur ("ce P&L ne fait pas sens") → `trace_parents` → recommandation de fix à la source. Requiert W2.

## 5. Anti-patterns à bannir

- **Living graph avant base_health vert** : substrat troué = mensonge structuré (cf §1).
- **Multiples gateways qui ne `log_datum` pas** : silent-miss inadmissible — un Datum qui sort d'un gateway sans entrer dans `datum_log` = trou de provenance définitif (le content-hash existe pas dans le log = parents future ne pourront pas le tracer). Gate CI sur tous les retours de `shared/prices.py`, `shared/storage`, `shared/llm`.
- **Concept_key inventés ad-hoc** : si le registre des concepts est ouvert (chacun crée sa clé), on perd l'invariant "même fait = même clé". Doit être un enum versionné (`config/concept_keys.yaml` à graver post-W1).
- **Auto-résolution magique des forks** : la machine **détecte**, l'humain **décide**. Sinon on rejoue le piège "le système se corrige tout seul" qui est exactement ce que [[L29]] interdit.

## 6. Tests verrouillants

- **fork_detection** : 2 Datums (concept_key="pmp_eur", ticker="000660.KS", asof_bucket="2026-06-09", value=45.21 vs 44.83) → `detect_forks` retourne ce fork.
- **no_fork_when_identical** : 2 Datums même concept + même value → 0 fork (idempotence).
- **provenance_capture** : `derive(fn, d1, d2)` puis `log_datum(result)` → `trace_parents(result.id)` retourne `[d1.id, d2.id, result.id]`.
- **degraded_propagation** : un Datum stale dans une chaîne → `trace_parents` montre `degraded=1` sur le nœud coupable.
- **gateway_log_invariant** : test grep que chaque `return Datum(...)` dans `shared/prices.py` est suivi de `log_datum(...)` (gate CI).
- **concept_keys_registry** : tout `concept_key` utilisé hors test doit exister dans `config/concept_keys.yaml` (gate CI W1+).

## 7. Seams (verify-before-patch)

- **Coût V0 de `register_concept`** : ~6 concepts × ~26 noms = ~150 INSERT/regen sur `concept_index` (vs ~500 si on loggait chaque Datum). UPSERT idempotent via PK composite. `perf_watch` doit voir < 20ms ajoutés. Si dépassé, batch via `executemany`.
- **`asof_bucket` granularité** : trop grosse (jour) = forks ratés intra-jour ; trop fine (seconde) = fausses positives sur deux calculs presque synchrones. Default jour, override per concept dans `concept_keys.yaml`.
- **Tolérance ε par concept** : essentielle, cf §2. Sans ε, le checker crie au loup sur jitter — il viole sa propre doctrine. ε mis à `epsilon_rel=0.001` pour PMP (calcul exact attendu), `0.005` pour value_eur/pnl (peut tolérer micro-jitter FX), `0.05` pour signaux qualitatifs (fragility).
- **DB growth V0** : `concept_index` est UPSERT, ne croît PAS avec les regens (un seul row par tuple PK même si écrit 1000×). Pas de TTL nécessaire en V0. (Quand `datum_log` arrivera en V1+, TTL 90j gérera la croissance append-only de la log généraliste — distinct.)
- **Coût V1+ de `datum_log`** : différé jusqu'au besoin. Quand on l'attaquera, profil avant : ~500 INSERT/regen exige soit batch `executemany`, soit worker async. Décision V1+, pas V0.

## 8. Anti-pattern détecté à la rédaction (auto-audit L25)

En écrivant cette spec, j'observe que `shared/integrity.py` (chaîne predictions + theses) implémente déjà une variante du pattern (hash-chain append-only, anchored OTS). Le living graph ne le doublonne PAS : `integrity.py` = chaîne sur predictions/theses spécifiquement (commit-reveal hiding), `datum_log` = log généraliste de TOUS les Datums du système. Couches différentes. Mais la séparation doit être nommée pour ne pas re-réinventer demain (verify-before-write L25 appliqué).

## 9. Implementation Status

- **Gravé** : 2026-06-09 (cf TODO #110, condition base_health vert acquise commit `2d3a4e4` + fail-loud `f3289c5`)
- **Implémentation** : IN_PROGRESS — W0 LIVRÉ 09/06 soir tard : `concept_index` table (migration 0051) + `register_concept`/`detect_forks` minimal + wire `ledger_pmp.py` (9 tickers publient `pmp_eur`) + hook regen-end `dashboard/render.py` + 5 tests (fork>ε / no-fork<ε / UPSERT idempotent / default ε / silent-miss L7). Reste W1-W4 (extension concepts, datum_log V1+, base_health 4e dim, feedback arrière).
- **Fichiers cibles V0** : `shared/living_graph.py` (à créer — `register_concept` + `detect_forks` SEULS), `scripts/alembic/versions/0051_concept_index.py` (à créer — table `concept_index` valeurs inline, PAS `datum_log`), `config/concept_keys.yaml` (à créer — pmp_eur min + ε par concept), `tests/test_living_graph.py` (à créer — fork_detection + anti-cry-wolf vérifié)
- **Fichiers cibles V1+** (différé jusqu'au besoin) : `datum_log` table + `log_datum` + `trace_parents` helpers
- **Audit drift** : `scripts/audit_canonical_drift.py`
- **Prochain step** : W0 tracer-bullet PMP — implémenter `register_concept/detect_forks` minimal + wire sur `shared/ledger_pmp.py` + appel `detect_forks` au regen-end dans `dashboard/render.py` ou `serve.py` + test fork_detection sur le cas exact L29 09/06 (anti-cry-wolf : même test avec diff <ε retourne 0 fork).

## 10. Le fil

> Le socle a déjà fait le travail invisible : chaque `Datum.parents` est un pointeur Merkle vers son lignage. Le living graph n'invente rien — il **matérialise** ce DAG dans une table append-only, l'**indexe** par concept sémantique, et l'**interroge** dans les deux sens (forward pour provenance, backward pour bisect). Trois capacités self-* tombent gratuitement : auto-auditant, auto-correcteur, auto-cohérent. L29 ("corriger calcul ≠ vérifier diffusion") devient une **propriété de la machine**, pas une discipline humaine répétée. Le graphe latent dans le socle devient une **boucle vivante** dès qu'on l'écoute.
