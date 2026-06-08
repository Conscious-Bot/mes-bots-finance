"""SOCLE extension : Monetary + pct_change + in_eur (cf SPEC_MONEY_INVARIANT.md).

Tout baseline monetaire (entry_price, avg_cost, stop, target_full, target_partial)
EST un `Datum[Monetary]` -- la devise voyage dans le `value`, asof/source/confidence/
degraded/derive viennent gratuitement du socle. Aucune logique de fraicheur dupliquee.

API publique :
  - `Monetary(amount, currency)` : la valeur portee par un Datum monetaire
  - `monetary(amount, currency, asof, source, ...)` : factory Datum[Monetary]
  - `pct_change(frm, to)` : UNE primitive de ratio monetaire qui asserte
    la commensurabilite (cross-devise -> erreur bruyante, pas nombre faux confiant)
  - `in_eur(m_datum, fx_datum)` : conversion devise -> EUR, retourne Datum[Monetary(EUR)]
    avec lignage propage via derive()

Lecture des invariants :
  - SPEC §1 : type unique Datum[Monetary], pas de hierarchie soeur Money
  - SPEC §2 : pct_change cross-devise = AssertionError (fail-closed structurel)
  - SPEC §5 : tests verrouillants — commensurabilite, baselines-distincts, byte-identite,
    fail-closed baseline, no-baseline-overwrite
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator

from shared.datum import Datum, derive


class Monetary(BaseModel):
    """La valeur portee par un Datum monetaire. Devise dans le triple.

    Frozen + extra='forbid' : anti-tampering downstream. L'etage compose, ne mute pas.
    `currency` : ISO 4217 ("USD", "EUR", "KRW", "JPY", "GBP", ...). Convention
    strict-upper -- comparaison directe sans normalisation a chaque site.

    Pydantic BaseModel (pas dataclass) pour compat directe avec Datum.value: Any
    qui transite par le serializer JSON Pydantic (content-hash + DB).
    """

    model_config = {"extra": "forbid", "frozen": True}

    amount: float
    currency: str

    @field_validator("currency")
    @classmethod
    def _currency_iso_upper(cls, v: str) -> str:
        if not v or v != v.upper():
            raise ValueError(
                f"Monetary.currency must be ISO 4217 upper-case, got {v!r}"
            )
        return v


def monetary(
    amount: float,
    currency: str,
    asof: str,
    source: str,
    confidence: float = 1.0,
    degraded: bool = False,
) -> Datum:
    """Factory : Datum[Monetary] leaf (pas de parents, pas d'op).

    Pour les baselines stockes en DB (entry_price, avg_cost, ...) qui sont
    des observations directes (pas derivees), c'est le constructeur canonique.
    """
    return Datum(
        value=Monetary(amount=amount, currency=currency),
        asof=asof,
        source=source,
        confidence=confidence,
        degraded=degraded,
    )


def pct_change(frm: Datum, to: Datum, op: str = "pct_change") -> Datum:
    """UNE SEULE primitive de ratio monetaire. Asserte la commensurabilite.

    `frm` et `to` doivent porter Monetary dans leur value, et MEME currency.
    Cross-devise (KRW vs EUR par ex) -> AssertionError immediate, pas un
    nombre faux confiant (+176056% etc.).

    Returns: Datum dont value = (to/from - 1)*100 (float pct). asof/confidence/
    degraded propages via derive() depuis frm + to.

    Pour comparer des devises differentes, l'appelant DOIT explicitement convertir
    via `in_eur(m, fx_at)` AVANT d'appeler pct_change -- traceable par lignage.
    """
    _assert_monetary(frm, "frm")
    _assert_monetary(to, "to")
    frm_ccy = frm.value.currency
    to_ccy = to.value.currency
    assert frm_ccy == to_ccy, (
        f"pct_change cross-devise interdit: {frm_ccy} vs {to_ccy} "
        "— convertis d'abord via in_eur() ou fx() (cf SPEC_MONEY_INVARIANT §2)"
    )
    # garde-fou divide-by-zero : retourne degraded si frm.amount = 0
    if frm.value.amount == 0:
        return Datum(
            value=None,
            asof=min(frm.asof, to.asof),
            source="derived",
            confidence=0.0,
            parents=(frm.id, to.id),
            op=op,
            degraded=True,
        )
    return derive(
        lambda a, b: (b.amount / a.amount - 1.0) * 100.0,
        frm, to,
        op=op,
    )


def in_eur(m_datum: Datum, fx_datum: Datum) -> Datum:
    """Convertit Datum[Monetary(X)] -> Datum[Monetary(EUR)] via fx Datum.

    fx_datum.value est le taux float (e.g. 0.000556 pour KRW->EUR). Le lignage
    est capture via derive() : le Datum resultat porte parents=(m.id, fx.id),
    asof=min, confidence=min, degraded=any.

    Asserte que fx_datum n'est pas None et qu'il convertit BIEN la currency
    de m_datum (sinon mismatch silencieux). On suppose fx.source porte le pair
    ("yfinance:fx" est trop vague mais coherent avec shared/prices.fx() actuel).

    Note : on n'asserte pas fx_datum.value.base parce que `shared.prices.fx()`
    retourne un Datum[float] (pas Monetary), donc on lui fait confiance pour
    fournir le bon taux. L'appelant garantit la coherence (sinon assert lev a
    plus tard quand pct_change croise les devises).
    """
    _assert_monetary(m_datum, "m_datum")
    if fx_datum is None or fx_datum.value is None:
        # fail-closed : pas de fx -> Datum degraded en EUR avec value None
        return Datum(
            value=None,
            asof=m_datum.asof,
            source="derived",
            confidence=0.0,
            parents=(m_datum.id,),
            op="in_eur_fx_missing",
            degraded=True,
        )
    return derive(
        lambda m, fx: Monetary(amount=m.amount * float(fx), currency="EUR"),
        m_datum, fx_datum,
        op="in_eur",
    )


def _assert_monetary(d: Datum, label: str) -> None:
    """Asserte qu'un Datum porte un Monetary dans son value."""
    if d is None:
        raise AssertionError(f"{label} is None — expected Datum[Monetary]")
    if not isinstance(d.value, Monetary):
        raise AssertionError(
            f"{label}.value must be Monetary, got {type(d.value).__name__} "
            "(cf SPEC_MONEY_INVARIANT §1 : tout baseline monetaire = Datum[Monetary])"
        )


def now_iso() -> str:
    """Helper pour les Datums leaf construits 'maintenant' (rare en prod, util tests)."""
    return datetime.now(UTC).isoformat()
