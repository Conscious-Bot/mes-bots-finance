# Spec SOCLE — la racine porteuse (masterpiece)

> Le socle n'est pas « la donnée réparée » — c'est **la couche racine qui définit trois primitives dont tout l'étage au-dessus hérite**. Conçu correctement, il rend M1, le fail-closed et la confiance **automatiques partout au-dessus**, au lieu de re-disciplinés panel par panel. Petit, élégant, porteur. Exécution concrète : `HANDOFF_SOCLE.md`. Cette spec est le *contrat* + les *branchements*.

## 0. L'idée maîtresse (ce qui en fait une masterpiece)

Trois choses qu'on traitait comme des disciplines séparées — **M1** (valeur+as-of+source), **fail-closed** (honnête quand stale), **confiance calibrée** — sont en réalité **un seul primitif** : le `Datum`. Et une seule **règle de propagation** fait que toute grandeur calculée à partir de Datums hérite automatiquement de leur fraîcheur, leur dégradation et leur confiance.

> Définis `Datum` + la règle de propagation **une fois**, et M1-partout + fail-closed-partout + confiance-partout deviennent des **propriétés structurelles**, pas de la discipline répétée. Tout l'étage au-dessus est honnête *par construction* parce qu'il est bâti sur des Datums.

C'est ça, le « relié à l'étage » : chaque valeur de la cornerstone, de la position-card, des profils secteur **EST un Datum** → elles héritent gratuitement des primitives du socle.

## 1. Primitif #1 — le `Datum` (la tissu conjonctif)

```python
# shared/datum.py
class Datum(Generic[T], frozen=True):
    value: T
    asof: str            # M1 — quand
    source: str          # M1 — d'où
    confidence: float    # CALIBRATION_DOCTRINE — combien on y croit (0..1)
    @property
    def staleness(self) -> float: ...      # now − asof
    @property
    def degraded(self) -> bool: ...        # staleness > SLA  OU  source en échec  OU  confidence < seuil
```

**Tout nombre du système est un Datum.** Un prix = `Datum[float]`. Un verdict de thèse = `Datum[Verdict]`. Une lecture cornerstone = `Datum[float]`. Un KPI sectoriel = `Datum[float]`. Plus de float nu nulle part au-dessus du socle.

## 2. Primitif #2 — la règle de propagation (le fail-closed automatique)

```python
def derive(fn, *inputs: Datum, **kw) -> Datum:
    return Datum(
        value      = fn(*[d.value for d in inputs]),
        asof       = min(d.asof for d in inputs),          # M1 : as-of = le plus vieux contributeur
        source     = "derived",
        confidence = combine_confidence([d.confidence for d in inputs]),
        # degraded se calcule : True si UN input est degraded
    )
```

Conséquence : **toute grandeur dérivée hérite de la staleness/dégradation/confiance la plus faible de ses inputs.** Le `PositionView.degraded`, la bannière fail-closed de la card, le `p_outcome=None` de la cornerstone, le plafond « confiance(fragilité) ≤ confiance(cycle) » — **tout ça tombe gratuitement de cette règle**, plus besoin de le câbler à la main par feature.

## 3. Primitif #3 — les Gateways (une porte par ressource)

Le socle est où vit « one door per resource ». Chaque gateway produit des `Datum`, et le bypass est interdit par gate CI.

| Ressource | Porte unique | Produit | Gate CI |
|---|---|---|---|
| Prix | `shared/prices.get()` | `Datum[price]` | `yfinance` hors `prices.py` = rouge |
| FX | `shared/prices.fx()` | `Datum[rate]` | idem |
| DB | `shared/storage` | rows | `import sqlite3` hors `storage.py` = rouge |
| LLM | `shared/llm` | `Datum[output]` + coût | déjà single-gateway ✓ |

Ça referme les violations de l'audit d'origine (48 `sqlite3`, 19 `yfinance`) **structurellement**, pas par bonne volonté.

## 4. base_health — le socle rend compte de lui-même

`base_health` lit l'état des trois primitifs : Datums frais (fraîcheur), gateways non-bypassés (gate), chaîne intègre + ancrée (provabilité). Le vert sur « Positions-vérité » + « Fraîcheur » est la **condition de ship** de tout l'étage au-dessus.

## 5. Le substrat de provabilité (la racine du self-scoring)

La chaîne d'intégrité (commit-reveal + OTS) est dans le socle : c'est *là* qu'écrivent les `insert_prediction` du cornerstone, de l'érosion, du self-scoring. Toute claim falsifiable de l'étage s'ancre ici. Le socle garantit l'irréversibilité.

---

## 6. LA CARTE DES BRANCHEMENTS (relié à l'étage au-dessus)

Le cœur de ta demande : qui, en haut, consomme quoi du socle.

```
SOCLE (racine)                          ÉTAGE (déjà bâti)
─────────────                           ──────────────────
Datum + propagation        ───────────► tout PositionView (chaque champ)
                           ───────────► drivers cornerstone (value+confidence+asof)
                           ───────────► KPI sectoriels (SPEC_SECTOR_TAXONOMY)
                           ───────────► STATE FRESH_LIVE|NEAR|STALE (SPEC_ALERT_VOCABULARY)

prices.get() / fx()        ───────────► value_eur() → PositionView.MV/P&L
                           ───────────► cornerstone micro (crowding, multiple, prix-vs-croyance)
                           ───────────► governor / fragilité

degraded (propagé)         ───────────► PositionView.degraded → card bannière + row dot gris
                           ───────────► cornerstone p_outcome=None (fail-closed)
                           ───────────► FLAG DEGRADED / FAIL_CLOSED (vocabulaire)

confidence (propagé)       ───────────► plafond confiance(fragilité) ≤ confiance(cycle)
                           ───────────► méta-calibration (bande N-dépendante)

base_health                ───────────► gate de ship de TOUTE partie book-facing

intégrité + OTS            ───────────► self-scoring cornerstone/érosion (insert_prediction)
```

**Invariant de liaison** : aucune couche de l'étage ne fabrique un nombre nu, ne bypass un gateway, ni ne décide son propre `degraded`. Elle **reçoit des Datums du socle et les compose**. La cohérence de tout l'édifice tient parce que la racine est un type + une règle, pas une convention.

## 7. Invariants porteurs (ce qui le rend load-bearing)

1. **Pas de float nu au-dessus du socle** : toute valeur affichée/calculée est un `Datum` (gate : grep des retours non-typés sur les fonctions de calcul).
2. **Pas de bypass de gateway** (gates CI prix/fx/db).
3. **`degraded` jamais décidé à la main en haut** : il se propage. Un panel qui set `degraded` localement = build rouge.
4. **base_health vert = pré-condition de ship** book-facing (les 4 DoD de `HANDOFF_SOCLE`).
5. **Datum frozen** (`extra='forbid'`) : anti-tampering downstream — l'étage compose, ne mute pas.

## 8. Exécution

Voir `HANDOFF_SOCLE.md` (ordonné par dépendance) : S0 OTS (irréversible, immédiat) → S1 `prices.get()` triple + gateways + `price_history` → S2 migration positions (tuer `eur_value`-dans-`notes`, `value_eur()` dérivée) → S3 base_health vert.

**Ajout masterpiece à cet ordre** : S1 *est* l'instanciation du `Datum` + des gateways. Donc S1 devient : poser `shared/datum.py` (le type + propagation) **d'abord**, puis `prices.get()` qui le retourne. Le `Datum` est la première brique — tout le reste du socle, et tout l'étage, en dépend.

## 9. Implementation Status

- **Gravé** : 2026-06-08 (date approximée — session SOCLE complet)
- **Implémentation** : IMPLEMENTED — les 5 primitifs sont en prod (S0 OTS anchor, S1a Datum, S1b gateways, S1c HARD mode yfinance, S2 positions VUE, S3 base_health vert)
- **Fichiers cibles** :
  - `shared/datum.py` (S1a primitif Datum + propagation derive) — TODO #109
  - `shared/prices.py` (S1b gateway canonique yfinance + helpers info/calendar/financials/balance_sheet/cashflow) — TODO #106 + #111
  - `scripts/base_health.py` (S3 scoreboard 3 dimensions positions+fraîcheur+chaîne) — TODO #107
  - `scripts/integrity_anchor.sh` + `bot/jobs/integrity_anchor.py` (S5 OTS substrat provabilité + L29 fail-loud Telegram) — TODO #108
  - `tests/test_doctrine_grep_gates.py` + `scripts/check_yfinance_gate.sh` (gate HARD mode AST-based) — TODO #112
- **Audit drift** : `scripts/audit_canonical_drift.py`
- **Prochain step** : `SPEC_LIVING_GRAPH` post-socle — graver DAG Datums boucle vivante (cf TODO #110 pending, condition base_health vert ACQUISE)

## 10. Le fil

> Une masterpiece de socle n'est pas grosse — elle est **petite et porteuse** : un type (`Datum`), une règle (propagation), quatre portes (gateways), un scoreboard (base_health), un ancrage (OTS). Cinq primitifs. Et parce que tout l'étage au-dessus *compose des Datums passés par des gateways*, il hérite de M1, du fail-closed et de la confiance **gratuitement, structurellement, partout**. Le socle ne soutient pas l'édifice par sa masse — il le soutient parce que **chaque pierre au-dessus est faite de sa matière.**
