"""SOCLE Phase 0 (Geste 1) : Datum + propagation. La brique-zero NON-RETROFITTABLE.

Cf SPEC_SOCLE.md S1-S2 : tout nombre du systeme est un Datum (value, asof,
source, confidence) avec lignage (parents, op) + content-hash (id).

L'idee maitresse : trois disciplines (M1 valeur+as-of+source, fail-closed
honnete-quand-stale, confiance calibree) sont en realite **un seul primitif**.
La regle derive() propage automatiquement la staleness/degradation/confiance
la plus faible des inputs -- M1+fail-closed+confiance deviennent des proprietes
STRUCTURELLES de l'etage au-dessus, pas de la discipline repetee.

Geste 1 cle : si chaque Datum est content-addresse (id = hash(value, parents, op)),
alors le graphe de lignage est un **Merkle-DAG = la chaine d'integrite**.
Provenance ET tamper-evidence dans la meme structure. Le lignage EST l'integrite.

Non-retrofittable : le graphe doit naitre AVEC le Datum, sinon l'info est perdue.
C'est pourquoi parents+op+id sont ici, des V0.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field


class Datum(BaseModel):
    """Le tissu conjonctif du socle. Tout nombre au-dessus du socle est un Datum.

    M1 : value + asof + source.
    Calibration : confidence (0..1).
    Lignage (Geste 1) : parents (ids des Datums d'ou il derive) + op (operation appliquee).
    Integrite : id content-hash = Merkle-DAG node.

    Frozen + extra='forbid' : anti-tampering downstream. L'etage compose, ne mute pas.
    """

    model_config = {"extra": "forbid", "frozen": True}

    value: Any = Field(description="La valeur (float, int, str, dict, enum...). Tout ce qui mesure quelque chose.")
    asof: str = Field(min_length=1, description="ISO timestamp de l'observation (M1 -- quand)")
    source: str = Field(min_length=1, description="Provenance (FRED:BAMLH0A0HYM2, yfinance:NVDA, derived, llm:haiku, ...) M1 -- d'ou")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="Confiance calibree 0..1. 1.0 = certitude (fixture), <0.5 = degraded structurel")
    parents: tuple[str, ...] = Field(default=(), description="Ids des Datums dont il derive (vide = leaf Datum issu d'un gateway). Lignage capture a la naissance.")
    op: str | None = Field(default=None, description="Nom human-readable de l'operation qui l'a produit (audit). 'fx_convert', 'qty_mul_price', 'sum_weighted_z'...")
    degraded: bool = Field(default=False, description="Fail-closed : True si stale OU source-fail OU confidence sous seuil. Propage automatiquement via derive().")

    @property
    def id(self) -> str:
        """Content-hash : sha256 deterministe sur (value, asof, source, parents, op).

        Stable byte-for-byte entre runs Python (json sort_keys + separators stricts).
        Merkle-DAG : un Datum + ses parents ids encode tout son lignage en hash chain.
        Le content-hash EST la preuve d'integrite dans la chaine OTS (Phase 2).
        """
        # value peut etre n'importe quoi : on le serialise via str() pour stable repr.
        # Pour float : on garde la precision native (pas de truncation 6-dec ici,
        # contrairement a canonical_payload integrity.py -- different cas d'usage).
        payload = {
            "value": _stable_repr(self.value),
            "asof": self.asof,
            "source": self.source,
            "parents": list(self.parents),
            "op": self.op,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_repr(v: Any) -> Any:
    """Serialisation stable pour le content-hash. Floats -> repr Python deterministe.

    Supporte Pydantic BaseModel (e.g. Monetary cf SPEC_MONEY_INVARIANT) via
    model_dump() recursif -- la devise voyage dans le value et reste hashable.
    """
    if isinstance(v, float):
        # repr Python est stable cross-platform pour les floats binary64 IEEE 754.
        return repr(v)
    if isinstance(v, BaseModel):
        # Datum[Monetary] et toute autre BaseModel imbriquee. Recurse sur le dump.
        return _stable_repr(v.model_dump())
    if isinstance(v, (list, tuple)):
        return [_stable_repr(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _stable_repr(val) for k, val in sorted(v.items())}
    return v


def derive(
    fn: Callable[..., Any],
    *inputs: Datum,
    op: str | None = None,
) -> Datum:
    """Propage M1+fail-closed+confiance+lignage en composant des Datums.

    Regle de propagation :
    - value     = fn(*[d.value for d in inputs])
    - asof      = min(d.asof for d in inputs)         # M1 honnete : le plus vieux dicte
    - source    = "derived"
    - confidence = min(d.confidence for d in inputs)  # le plus faible dicte
    - parents   = tuple(d.id for d in inputs)         # lignage capture
    - op        = nom human-readable (audit)
    - degraded  = any(d.degraded for d in inputs)     # fail-closed automatique

    Conditions :
    - inputs non-vide (ValueError sinon).

    Note : derive() ne sait rien des SLA staleness -- c'est aux gateways
    (prices.get, fx, llm) de set degraded=True quand stale. derive() ne fait
    QUE propager. Cette separation garantit que le socle reste agnostique
    aux SLA specifiques de chaque ressource.
    """
    if not inputs:
        raise ValueError("derive() requires at least 1 input Datum")

    return Datum(
        value=fn(*[d.value for d in inputs]),
        asof=min(d.asof for d in inputs),
        source="derived",
        confidence=min(d.confidence for d in inputs),
        parents=tuple(d.id for d in inputs),
        op=op,
        degraded=any(d.degraded for d in inputs),
    )
