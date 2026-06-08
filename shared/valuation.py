"""Valorisation = fonction, jamais table (M1 doctrine premier-principe).

Spec red-team 07/06 nuit++ : "Ne stocke jamais une valeur qui est fonction
d'un prix." eur_value figé dans positions.notes = bug fondateur. La verite
de "combien vaut ma position" est un CALCUL a l'instant de lecture sur des
inputs qui portent chacun leur as-of.

position_valuation(position_id) ->
  PositionValuation dataclass avec :
  - qty (input mutable, latest-wins)
  - price_native + price_asof + price_source (cache live)
  - fx_rate + fx_asof + fx_source (cache live)
  - effective_asof = min(price_asof, fx_asof)
  - staleness_severity (green/amber/rouge via shared/freshness)
  - value_eur (DERIVE : qty * price_native * fx_rate, ou None si rouge L15)
  - value_eur_fail_reason : str si None (fail-closed visible)

Doctrine :
- L15 fail-closed : si price ou fx en rouge severity -> value_eur = None
  + raison explicite. Le caller dashboard/render affiche "STALE" badge,
  jamais un chiffre fabrique.
- M1 triple : chaque field porte son asof + source observable.
- L17 declarative : SLA seuils en config/freshness.yaml.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PositionValuation:
    """Snapshot derive au moment de la lecture. JAMAIS persiste."""
    position_id: int
    ticker: str
    qty: float
    # Inputs dates (M1 triple)
    price_native: float | None
    price_asof: str | None
    price_source: str | None
    price_severity: str  # green / amber / rouge / unknown
    fx_rate: float | None
    fx_from: str
    fx_to: str
    fx_asof: str | None
    fx_source: str | None
    fx_severity: str
    # Outputs derives (None si fail-closed L15)
    value_eur: float | None
    value_eur_fail_reason: str | None
    effective_asof: str | None  # min(price_asof, fx_asof)
    overall_severity: str       # max(price_severity, fx_severity)


_SEVERITY_RANK = {"green": 0, "amber": 1, "rouge": 2, "unknown": 3}


def _worst(a: str, b: str) -> str:
    return a if _SEVERITY_RANK.get(a, 99) >= _SEVERITY_RANK.get(b, 99) else b


def _min_asof(a: str | None, b: str | None) -> str | None:
    if a is None or b is None:
        return a or b
    return a if a < b else b


def position_valuation(position_id: int) -> PositionValuation | None:
    """Calcule valorisation d'une position a l'instant de lecture.

    Returns None si position introuvable ou qty <= 0.
    Returns PositionValuation avec value_eur=None si severity rouge (L15).

    Doctrine M1 : tous les inputs portent leur asof + source. Le derive
    value_eur est None sur rouge, jamais fabrique.
    """
    from shared import storage
    from shared.freshness import classify_asof
    from shared.prices import get_currency_for_ticker

    # Read position (input mutable, latest-wins)
    try:
        with storage.db() as cx:
            row = cx.execute(
                "SELECT id, ticker, qty FROM positions "
                "WHERE id = ? AND status = 'open'",
                (position_id,),
            ).fetchone()
            if not row or float(row[2]) <= 0:
                return None
            ticker = row[1]
            qty = float(row[2])
    except Exception as e:
        log.warning(f"position_valuation {position_id} DB read failed: {e}")
        return None

    # Read latest price (input date)
    latest_px = storage.get_latest_price(ticker)
    if latest_px is None:
        # Pas d'observation persistee -> unknown severity (L15 refuse value)
        return PositionValuation(
            position_id=position_id, ticker=ticker, qty=qty,
            price_native=None, price_asof=None, price_source=None,
            price_severity="unknown",
            fx_rate=None, fx_from=get_currency_for_ticker(ticker), fx_to="EUR",
            fx_asof=None, fx_source=None, fx_severity="unknown",
            value_eur=None,
            value_eur_fail_reason=f"no price_history observation for {ticker}",
            effective_asof=None, overall_severity="unknown",
        )
    price_native = latest_px["price_native"]
    price_asof = latest_px["asof"]
    price_source = latest_px["source"]
    price_severity, _ = classify_asof("price", price_asof)
    currency = latest_px["currency"]

    # Read latest FX (if needed)
    if currency == "EUR":
        fx_rate = 1.0
        fx_asof = price_asof  # synthetic identity
        fx_source = "identity"
        fx_severity = "green"
    else:
        latest_fx = storage.get_latest_fx_rate(currency, "EUR")
        if latest_fx is None:
            return PositionValuation(
                position_id=position_id, ticker=ticker, qty=qty,
                price_native=price_native, price_asof=price_asof,
                price_source=price_source, price_severity=price_severity,
                fx_rate=None, fx_from=currency, fx_to="EUR",
                fx_asof=None, fx_source=None, fx_severity="unknown",
                value_eur=None,
                value_eur_fail_reason=f"no fx_history observation for {currency}->EUR",
                effective_asof=price_asof, overall_severity="unknown",
            )
        fx_rate = latest_fx["rate"]
        fx_asof = latest_fx["asof"]
        fx_source = latest_fx["source"]
        fx_severity, _ = classify_asof("fx", fx_asof)

    # Compute derived value (L15 fail-closed si rouge)
    overall_severity = _worst(price_severity, fx_severity)
    effective_asof = _min_asof(price_asof, fx_asof)
    value_eur: float | None
    fail_reason: str | None
    if overall_severity == "rouge":
        value_eur = None
        fail_reason = (
            f"L15 fail-closed: severity=rouge (price={price_severity}, "
            f"fx={fx_severity}). Inputs stales au-dela SLA config/freshness.yaml."
        )
    else:
        value_eur = qty * price_native * fx_rate
        fail_reason = None

    return PositionValuation(
        position_id=position_id, ticker=ticker, qty=qty,
        price_native=price_native, price_asof=price_asof,
        price_source=price_source, price_severity=price_severity,
        fx_rate=fx_rate, fx_from=currency, fx_to="EUR",
        fx_asof=fx_asof, fx_source=fx_source, fx_severity=fx_severity,
        value_eur=value_eur, value_eur_fail_reason=fail_reason,
        effective_asof=effective_asof, overall_severity=overall_severity,
    )


# === SOCLE Phase 2 S2 : position_valuation_datum (compose via derive) =====
# Cf SPEC_SOCLE.md S1 ("tout nombre est un Datum") + HANDOFF_SOCLE.md S2.
#
# position_valuation() retourne une PositionValuation dataclass (legacy compatible).
# position_valuation_datum() retourne un Datum compose via derive() -- la version
# Datum capture le LIGNAGE (parents = qty_id, price_id, fx_id) qui amorce le
# graphe vivant (post-socle living_graph).
#
# Migration consumers : nouveaux callers (cornerstone, governor, PositionView)
# devraient consommer la version Datum pour beneficier de la propagation gratuite
# de degraded/confidence. Legacy callers gardent PositionValuation (status quo).


def position_valuation_datum(position_id: int):  # -> Datum | None
    """SOCLE compose : retourne value_eur en Datum avec lignage capture.

    Wrap chaque input (qty, price_native, fx_rate) en leaf Datum puis derive()
    compose la value_eur en propageant asof=min, confidence=min, degraded=any,
    parents=(qty.id, price.id, fx.id).

    Returns None si position introuvable ou fail-closed (severity rouge).

    Lien Phase 2 S0 : le content-hash du Datum produit (`.id`) est un noeud
    Merkle-DAG qui sera ancrable OTS (le lignage EST l'integrite).
    """
    from shared.datum import Datum, derive
    pv = position_valuation(position_id)
    if pv is None:
        return None
    if pv.value_eur is None:
        # L15 fail-closed propage : retourne Datum degraded sans value calculee.
        # Mais Datum exige value -- on retourne None ici (cohesion avec
        # legacy PositionValuation.value_eur=None pattern). Le caller checke None.
        return None

    # Severity -> confidence palier (green=1.0, amber=0.7, rouge handled above)
    _severity_to_confidence = {"green": 1.0, "amber": 0.7, "unknown": 0.5}

    # Leaf Datum : qty (latest-wins, source positions table)
    qty_datum = Datum(
        value=pv.qty,
        asof=pv.price_asof or "1970-01-01T00:00:00Z",  # qty n'a pas d'asof propre,
        # on prend price_asof comme baseline minimum (qty.asof <= price.asof toujours)
        source=f"positions:{pv.ticker}",
        confidence=1.0,  # qty est ground-truth user
        degraded=False,
    )

    # Leaf Datum : prix natif
    price_datum = Datum(
        value=pv.price_native,
        asof=pv.price_asof or "1970-01-01T00:00:00Z",
        source=f"price_history:{pv.ticker}:{pv.price_source}",
        confidence=_severity_to_confidence.get(pv.price_severity, 0.5),
        degraded=(pv.price_severity == "rouge"),
    )

    # Leaf Datum : FX rate (identity si EUR natif)
    fx_datum = Datum(
        value=pv.fx_rate,
        asof=pv.fx_asof or pv.price_asof or "1970-01-01T00:00:00Z",
        source=f"fx_history:{pv.fx_from}->{pv.fx_to}:{pv.fx_source}",
        confidence=_severity_to_confidence.get(pv.fx_severity, 0.5),
        degraded=(pv.fx_severity == "rouge"),
    )

    # Compose : value_eur = qty * price_native * fx_rate
    return derive(
        lambda q, p, f: q * p * f,
        qty_datum, price_datum, fx_datum,
        op="qty_mul_price_mul_fx",
    )
