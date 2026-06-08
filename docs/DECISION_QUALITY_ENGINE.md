# DECISION_QUALITY_ENGINE — spec d'ossature (draft 07/06/2026)

> Le jump : passer d'un *journal de P&L honnête* à un *moteur de qualité de décision*.
> On arrête de scorer les **outcomes** (dominés par la chance à petit n) pour scorer
> le **process** et l'**attribution causale**. Trois composants, un package neuf
> `track_record/`, `render.py` reste **consommateur read-only**.
>
> Doctrines respectées : L15 fail-closed (jamais de verdict fabriqué en mode dégradé),
> L16 splits temporels / point-in-time, L17 YAML déclaratif + journal DB append-only,
> `monitor_pattern` pour les transitions de résolution.

---

## A — Intégrité par pré-engagement (la fondation)

Sans verrou tamper-evident à l'entrée, toute métrique aval est corruptible
(révision de conviction post-hoc, date de résolution floue, benchmark cherry-pické).
Mode d'échec d'une machine à discipline = l'opérateur qui la triche en douce.

### Table `decision_journal` (append-only, hash-chaînée)

```sql
CREATE TABLE IF NOT EXISTS decision_journal (
    decision_id      TEXT PRIMARY KEY,           -- uuid4
    seq              INTEGER NOT NULL,            -- ordre append, monotone
    ticker           TEXT NOT NULL,
    entry_ts         TEXT NOT NULL,               -- ISO PIT, immuable
    conviction       INTEGER NOT NULL CHECK(conviction BETWEEN 1 AND 5),
    variant_perception TEXT NOT NULL,             -- où tu diffères du consensus
    epic_driver_json TEXT NOT NULL,               -- KPI mesurable + direction + magnitude + lien-prix
    falsifiable_claim TEXT NOT NULL,              -- prédiction testable unique
    kill_criteria_json TEXT NOT NULL,             -- [{condition, action}]
    horizon_date     TEXT NOT NULL,               -- résolution pré-commitée, immuable
    benchmark_id     TEXT NOT NULL,               -- fixé ex-ante
    entry_px         REAL NOT NULL,
    benchmark_entry_px REAL NOT NULL,
    payload_hash     TEXT NOT NULL,               -- sha256(canonical(champs immuables) + prev_hash)
    prev_hash        TEXT NOT NULL                -- chaînage → édition rétroactive = chaîne cassée
);
```

### Mécanisme

- `epic_driver_json` **doit** être un KPI mesurable, pas une narration. C'est ce qui rend
  l'attribution (composant B) mécanisable. Pydantic le force.
- Sérialisation canonique (clés triées, séparateurs fixes) → hash déterministe.
- Chaque ligne hash inclut `prev_hash` → ledger Merkle-like. `verify_chain()` recompute
  toute la chaîne ; **si elle casse, le moteur de calibration refuse de scorer (L15).**

```python
# track_record/decision_journal.py
import hashlib, json
from pydantic import BaseModel, Field, field_validator

class EpicDriver(BaseModel):
    kpi: str                       # ex: "gross_margin_bps"
    direction: str                 # "up" | "down"
    magnitude: float               # seuil prédit (ex: +150 bps)
    price_channel: str             # "fundamental" | "multiple" — par quel canal ça doit toucher le prix

class DecisionEntry(BaseModel):
    ticker: str
    conviction: int = Field(ge=1, le=5)
    variant_perception: str
    epic_driver: EpicDriver
    falsifiable_claim: str
    kill_criteria: list[dict]
    horizon_date: str
    benchmark_id: str
    entry_px: float
    benchmark_entry_px: float

_IMMUTABLE = ("ticker","conviction","variant_perception","epic_driver",
              "falsifiable_claim","kill_criteria","horizon_date","benchmark_id",
              "entry_px","benchmark_entry_px","entry_ts")

def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)

def compute_hash(payload: dict, prev_hash: str) -> str:
    body = {k: payload[k] for k in _IMMUTABLE}
    return hashlib.sha256((_canonical(body) + prev_hash).encode()).hexdigest()

def verify_chain(rows: list[dict]) -> bool:
    prev = "GENESIS"
    for r in sorted(rows, key=lambda x: x["seq"]):
        if compute_hash(r, prev) != r["payload_hash"]:
            return False                      # L15: chaîne cassée → no scoring
        prev = r["payload_hash"]
    return True
```

---

## B — Attribution causale 2×2 (le vrai jump)

Question supérieure : pas « la ligne a-t-elle surperformé ? » mais
**« a-t-elle surperformé pour la raison écrite à l'entrée ? »**

### Le 2×2 process × outcome

| | outcome bon | outcome mauvais |
|---|---|---|
| **raison juste** | skill répétable → *size ça* | process sain → ne pas désapprendre |
| **raison fausse** | **chance déguisée en talent → le quadrant qui ruine** | vrai apprentissage |

La calibration sur outcomes seule est **aveugle au quadrant haut-droite/bas-gauche** —
c'est précisément lui le danger.

### Mécanisation de « raison juste »

On ne prouve pas la causalité au sens dur ; on l'adjuge avec discipline :

1. **Driver-hit test** : le KPI nommé dans `epic_driver` a-t-il bougé dans la direction
   et la magnitude prédites ? Objectif car le KPI est mesurable (forcé par A).
   Source = daloopa / bigdata (KPI réalisé sur l'horizon).
2. **Décomposition du return** : excess return ≈ Δfondamental + Δmultiple + résidu.
   Le canal nommé (`price_channel`) domine-t-il la décompo ?
3. **Kill-criteria respectés** : booléen depuis le journal de monitoring existant.

```python
# track_record/attribution.py
from enum import Enum

class Quadrant(str, Enum):
    SKILL          = "right_reason_right_outcome"
    LUCK           = "wrong_reason_right_outcome"   # le quadrant dangereux
    SOUND_PROCESS  = "right_reason_wrong_outcome"
    LEARNING       = "wrong_reason_wrong_outcome"
    UNATTRIBUTABLE = "unattributable"               # L15: résidu domine → pas de story forcée

def attribute_decision(entry, realized) -> dict:
    driver_hit = (realized.kpi_move_dir == entry.epic_driver.direction
                  and abs(realized.kpi_move) >= entry.epic_driver.magnitude)
    decomp = realized.return_decomposition            # {fundamental, multiple, residual}
    dominant = max(decomp, key=decomp.get)
    # honnêteté : si on n'explique pas le mouvement, on ne fabrique pas de cause
    if decomp["residual"] >= 0.5 * sum(abs(v) for v in decomp.values()):
        return {"quadrant": Quadrant.UNATTRIBUTABLE, "decomp": decomp}
    reason_right = driver_hit and dominant == entry.epic_driver.price_channel \
                   and realized.kill_criteria_respected
    outcome_good = realized.excess_return >= realized.outperf_threshold
    q = {(True, True): Quadrant.SKILL, (True, False): Quadrant.SOUND_PROCESS,
         (False, True): Quadrant.LUCK, (False, False): Quadrant.LEARNING}[(reason_right, outcome_good)]
    return {"quadrant": q, "driver_hit": driver_hit, "decomp": decomp,
            "attributed_channel": dominant}
```

Sortie agrégée qui compte : **part de tes outcomes bons qui tombent en `LUCK`**.
C'est ton vrai taux d'illusion de skill.

---

## C — Hook base-rate (outside view, crève le plafond du petit n)

À n=40 tu ne calibres jamais avec puissance sur ton seul échantillon. Solution
structurelle : ancrer chaque thèse dans une **classe de référence** issue de l'univers
(Bigdata/daloopa désormais branchés).

### Fingerprint de thèse (extrait à l'entrée, pur)

```python
# track_record/reference_class.py
def fingerprint(entry, tearsheet) -> dict:
    return {
        "sector": tearsheet.sector,
        "catalyst_type": entry.epic_driver.kpi_family,      # "margin" | "growth" | "rerating" ...
        "setup": tearsheet.setup_bucket,                    # "post_beat" | "quality_momo" | "deep_value" ...
        "valuation_pct": tearsheet.valuation_percentile,    # décile EV/EBITDA vs secteur
    }

def base_rate(fp: dict, horizon_days: int) -> dict | None:
    dist = query_universe_excess_returns(fp, horizon_days)  # via bigdata_search/tearsheet, caché
    if dist.n < MIN_N:                                       # L15: pas de base rate bidon
        return None
    return {"p_outperform": dist.hit_rate, "dist": dist.summary, "n": dist.n}
```

Double usage :
- **Prior** de shrinkage bayésien dans la calibration (ton bucket conviction est tiré
  vers la base rate de sa classe quand n est faible).
- **Injection décision-time** : « ton fingerprint résout favorablement à X% ;
  ta conviction c4 implique Y% — l'écart est ta variant perception, est-elle justifiée ? »

### `config/decision_quality.yaml` (déclaratif, Pydantic)

```yaml
benchmark:
  default: "MSCI_WORLD_EUR"
  sector_overrides: { semis: "SOX_EUR", utilities: "SX6P_EUR" }
horizons_days: [126, 252]          # pré-commités
power_gates: { min_n_bucket: 20, min_n_base_rate: 40 }
shrinkage: { prior_strength: 15 }  # force du pull vers la base rate
attribution: { residual_dominance_threshold: 0.5 }
```

---

## Séquence de construction

Dépendance : **A → C → B** (A est la colonne ; C alimente le prior ; B a besoin du
driver structuré de A + des KPI externes). Mais ordre par **levier** :

1. **A** d'abord — intégrité, cheap, protège tout le reste. `decision_journal` + `verify_chain`
   + backfill PIT des positions ouvertes (fige le point-in-time **maintenant** : le look-ahead
   empoisonne toute reconstruction rétroactive).
2. **B** ensuite — l'adjudication 2×2 ; c'est *là* qu'est le saut qualitatif.
3. **C** enfin — dépend de la maturité connecteur (couverture KPI daloopa/bigdata à valider).

`render.py` n'ajoute qu'un panneau **read-only** : la grille 2×2 + part `LUCK` + base-rate gap.

## Garde-fous transverses
- **L15** : chaîne cassée, résidu dominant, ou n < gate → `None` / `UNATTRIBUTABLE`, jamais un chiffre inventé.
- **L16** : conviction et driver scorés *tels qu'enregistrés à l'entrée*, horizon pré-commité, zéro peeking.
- **L17** : `decision_journal` append-only ; toute config en `config/decision_quality.yaml` versionnée + Pydantic.
- **Anti-double-instrumentation** : `kill_criteria_respected` lit le journal de monitoring existant, ne le ré-implémente pas.
