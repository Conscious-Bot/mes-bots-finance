# Spec LIVING GRAPH — le DAG des Datums devient une boucle vivante

> Le socle a posé `Datum.parents` à V0 : **le graphe de lignage existe déjà**, latent dans chaque nombre du système. Le living graph est ce qu'on en fait quand on le **matérialise** + on l'**interroge**. Trois capacités self-* tombent gratuitement : auto-auditant (provenance forward), auto-correcteur (feedback arrière via parents), auto-cohérent (forks détectés live). Pas un nouvel étage — l'exploitation du substrat déjà présent.

## 0. L'idée maîtresse

Le `Datum` ([[SPEC_SOCLE]] §1) a déjà la structure d'un nœud Merkle-DAG : `id = hash(value, asof, source, parents, op)`. Quand `derive()` propage, chaque dérivation pointe vers ses parents via leur content-hash. **Le lignage complet de chaque fait du système existe donc déjà** — il flotte juste, non-matérialisé, jamais interrogé.

Le living graph est trois gestes pour le rendre vivant :

1. **Matérialiser** : table `datum_log` append-only qui persiste `(id, value_repr, asof, source, parents, op, degraded, created_at)` à chaque Datum publié. Le DAG existe **par écrit**, pas que dans la mémoire d'un run Python.

2. **Indexer par concept** : un Datum peut représenter "le PMP roulant de SK Hynix au 09/06 17h22" — mais plusieurs chemins de calcul (BookLine, VUE SQL, helper Python) peuvent prétendre calculer **le même fait sémantique**. La table `concept_index` mappe `(concept_key, ticker, asof_window) → liste de datum_ids prétendants`. Quand `len(values_distincts) > 1` dans la fenêtre → **fork détecté en live**.

3. **Interroger arrière** : un consumer qui reçoit une valeur "qui ne fait pas sens" peut remonter `parents` jusqu'à trouver un Datum dégradé/stale/source-fail. Le DAG est exploité **dans les deux sens** — forward pour provenance, backward pour bisect.

**La conséquence vivante** : L29 ("corriger calcul ≠ vérifier diffusion") devient mécanisé. Le fork PMP roulant BookLine vs VUE SQL aurait été **détecté automatiquement** dès la divergence apparue, sans que quelqu'un re-grep tous les consumers à la main. La discipline humaine "vérifier la diffusion à chaque chemin" devient une propriété structurelle.

> Le socle pose les briques (Datum + parents). Le living graph les fait parler. Auto-auditant, auto-correcteur, auto-cohérent — pas par convention, par construction.

## 1. Pré-conditions (rappel discipline)

- **base_health vert** : positions-vérité + fraîcheur + chaîne intègre + OTS. Acquis 09/06 soir tard ([[SPEC_SOCLE]] §4).
- **`Datum.parents` capturés à la naissance** : si les gateways oublient de chaîner, le graphe a des trous. Vérifié via test serrure (cf §8).
- **`derive()` est la seule porte de propagation** : pas de Datum dérivé sans passer par `derive()` (sinon parents=()). Gate existant.

Sans ces 3 conditions, le living graph travaille sur un substrat troué — il ment par omission. C'est pourquoi le SPEC n'est gravé qu'après base_health vert (cf [[L25]] anti-pattern "graver sur fondation cassée").

## 2. Architecture (tables + helpers minimaux)

```
datum_log (append-only)
├── id               TEXT PRIMARY KEY  -- content-hash du Datum
├── value_repr       TEXT              -- _stable_repr(value), pour audit human-readable
├── asof             TEXT              -- M1 quand
├── source           TEXT              -- M1 d'où (gateway:resource ou "derived")
├── parents          TEXT              -- JSON list[id] (FK soft vers self)
├── op              TEXT NULL          -- nom op si dérivé
├── degraded         INT  (0|1)        -- fail-closed flag propagé
├── confidence       REAL              -- 0..1
└── logged_at        TEXT              -- now() à l'insert (pas asof)

concept_index
├── concept_key      TEXT              -- 'pmp_eur', 'value_eur', 'fragility', ...
├── ticker           TEXT NULL         -- scope optionnel
├── asof_bucket      TEXT              -- bucket temporel (jour/heure selon concept)
├── datum_id         TEXT              -- FK datum_log.id
└── PRIMARY KEY (concept_key, ticker, asof_bucket, datum_id)
```

**Helpers** (`shared/living_graph.py`) :

```python
def log_datum(d: Datum) -> None:
    """Persist Datum dans datum_log. Idempotent via id PK. Silent-miss L7 si DB down."""

def register_concept(concept_key: str, d: Datum, ticker: str | None = None, asof_bucket: str | None = None) -> None:
    """Lie un Datum à un concept sémantique. asof_bucket default = jour ISO de asof."""

def detect_forks(concept_key: str, ticker: str | None = None, asof_bucket: str | None = None) -> list[dict]:
    """Retourne liste de forks live : [{concept, bucket, candidates: [{id, value, source, op}, ...]}, ...].
    Fork = ≥ 2 valeurs distinctes dans la même bucket. Vide = cohérent."""

def trace_parents(datum_id: str, max_depth: int = 5) -> list[dict]:
    """Remonte le DAG : retourne chaîne [(id, source, op, value, degraded), ...] jusqu'à
    leaf Datums (parents=()) ou max_depth. Utile pour bisect 'qui a menti'."""
```

## 3. Trois capacités self-*

### 3.1 Auto-auditant (provenance forward)

Tout consumer peut demander "d'où vient ce nombre" via `trace_parents(d.id)`. Le DAG donne la chaîne complète : gateway origine → derivations intermédiaires → résultat affiché. C'est la transparence du calcul, accessible à la demande.

Pas nouveau conceptuellement (le DAG est déjà là), mais devient **interrogeable** une fois matérialisé dans `datum_log`.

### 3.2 Auto-correcteur (feedback arrière)

Quand un panneau affiche une valeur suspecte (P&L absurde, asym ratio négatif, etc.), le helper `trace_parents` remonte le DAG et flag les nœuds `degraded=True` ou `confidence < seuil`. **Le coupable est trouvé sans grep.** Le développeur (ou un sub-agent automatique futur) attaque la source, pas le symptôme — cure for-good par construction.

### 3.3 Auto-cohérent (forks détectés live)

C'est le geste qui matérialise L29. `register_concept` est appelé par les producteurs canoniques (BookLine, VUE SQL, helpers Python) avec le même `concept_key` ("pmp_eur" par ex.). `detect_forks` est appelé par un cron 5min ou un test gate — il retourne tout fork live. Sur fork détecté :

- **Telegram alert OPS** (analogue L29 fail-loud OTS) : "fork pmp_eur SK Hynix 09-06 : BookLine=45.21 vs VUE=44.83"
- **Surface base_health** : 4e dimension "cohérence" passe RED tant que fork ouvert
- **Décision humaine** : qui est juste, suppression du chemin faux (ou fail-closed NULL du chemin faux)

**Ce n'est pas une auto-résolution magique** — c'est la **détection automatique** + **alerte loud** d'un fait qui aurait sinon dormi. La décision reste humaine, mais le silent-drift est tué.

## 4. Build sequence (walking-skeleton, fixture réelle d'abord — L24)

**Geste fondateur (W0, tracer-bullet)** :
- Migration alembic : crée tables `datum_log` + `concept_index`
- `shared/living_graph.py` minimal : `log_datum` + `register_concept` + `detect_forks` (pas encore `trace_parents`)
- **Tracer-bullet PMP** : modifie `shared/ledger_pmp.py` pour `log_datum` + `register_concept("pmp_eur", ticker)` sur chaque calcul ; modifie la VUE-equivalent SQL helper (s'il existe encore) pour faire pareil
- Test serrure : INSERT manuel de 2 Datums divergents même concept_key → `detect_forks` retourne 1 fork
- **Si W0 marche** : on a la preuve par construction que le pattern fonctionne sur le cas exact qui a saigné (L29 09/06)

**W1** : étend aux concepts critiques restants — `value_eur`, `weight_pct`, `pnl_position`, `current_price_eur`. Cron `detect_forks_job` (5min) qui appelle `detect_forks` sur tous les concepts enregistrés + Telegram alert OPS sur fork.

**W2** : `trace_parents` + helper `/datum_trace <id>` Telegram pour debug live. Surface dans la position-card via attribut `data-datum-id` sur les chiffres affichés (debug power-user).

**W3** : base_health gagne une 4e dimension "cohérence live". RED si forks ouverts > 0 sur les concepts critiques. Gate de ship.

**W4 (FUTURE post-cornerstone-macro)** : feedback arrière automatique sur signaux de l'utilisateur ("ce P&L ne fait pas sens") → trace_parents → recommandation de fix à la source.

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

- **Coût de `log_datum`** : à chaque Datum publié, un INSERT. Sur un dashboard regen avec ~500 Datums, c'est 500 INSERT/regen. Mesurer : `perf_watch` doit voir < 50ms ajoutés. Si dépassé, batch INSERT via `executemany` ou worker async.
- **Idempotence via content-hash PK** : `INSERT OR IGNORE` sur datum_log.id — si le même Datum est publié 2× (legit), la 2e insertion est no-op gratuite.
- **`asof_bucket` granularité** : trop grosse (jour) = forks ratés intra-jour ; trop fine (seconde) = fausses positives sur deux calculs presque synchrones. Default jour, override per concept dans `concept_keys.yaml`.
- **DB growth** : `datum_log` est append-only, croît avec chaque regen. TTL : truncate au-delà de 90j (les forks anciens non détectés sont des artefacts archéologiques, pas du fail-closed actif). Cron `purge_old_datums_job`.

## 8. Anti-pattern détecté à la rédaction (auto-audit L25)

En écrivant cette spec, j'observe que `shared/integrity.py` (chaîne predictions + theses) implémente déjà une variante du pattern (hash-chain append-only, anchored OTS). Le living graph ne le doublonne PAS : `integrity.py` = chaîne sur predictions/theses spécifiquement (commit-reveal hiding), `datum_log` = log généraliste de TOUS les Datums du système. Couches différentes. Mais la séparation doit être nommée pour ne pas re-réinventer demain (verify-before-write L25 appliqué).

## 9. Implementation Status

- **Gravé** : 2026-06-09 (cf TODO #110, condition base_health vert acquise commit `2d3a4e4` + fail-loud `f3289c5`)
- **Implémentation** : NOT_STARTED (SPEC posé, walking-skeleton W0 à venir)
- **Fichiers cibles** : `shared/living_graph.py` (à créer), `scripts/alembic/versions/0051_datum_log_concept_index.py` (à créer), `config/concept_keys.yaml` (à créer W1+), `tests/test_living_graph.py` (à créer)
- **Audit drift** : `scripts/audit_canonical_drift.py`
- **Prochain step** : W0 tracer-bullet PMP — implémenter `log_datum/register_concept/detect_forks` minimal + wire sur `shared/ledger_pmp.py` + test fork_detection sur le cas exact L29 09/06.

## 10. Le fil

> Le socle a déjà fait le travail invisible : chaque `Datum.parents` est un pointeur Merkle vers son lignage. Le living graph n'invente rien — il **matérialise** ce DAG dans une table append-only, l'**indexe** par concept sémantique, et l'**interroge** dans les deux sens (forward pour provenance, backward pour bisect). Trois capacités self-* tombent gratuitement : auto-auditant, auto-correcteur, auto-cohérent. L29 ("corriger calcul ≠ vérifier diffusion") devient une **propriété de la machine**, pas une discipline humaine répétée. Le graphe latent dans le socle devient une **boucle vivante** dès qu'on l'écoute.
