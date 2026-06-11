"""Helpers purs pour le track-record alpha (SPEC_THESIS_ALPHA_RESOLVER §2-3).

Couche pure-fonction : zero I/O, zero DB, zero fetch. Le caller fournit les
inputs (prix, fx, PT consensus) résolus. Ces helpers calculent la conversion
+ les métriques alpha + classify direction.

Décisions §0 SPEC :
- A : convert AT ASOF (fx_asof figé par caller, helper ne re-fetch pas)
- B : freeze PT (helper opère sur snapshot, jamais re-read consensus)
- D : frame NATIF fx-strippé (toute la formule en native_currency)
- E : couche isolée (jamais agrégée avec Brier signal ou P&L EUR)

Loader : N/A (pure functions, importées directement).
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Literal

log = logging.getLogger(__name__)

DirectionLabel = Literal["correct", "incorrect", "neutral", "no_bet"]


def convert_consensus_pt_to_native(
    consensus_ref: dict,
    native_currency: str,
    fx_at_asof: float,
) -> dict | None:
    """Convert PT consensus → devise native du ticker, FIGÉE à asof.

    Décisions A + D : asof = moment de la pose, native = devise de l'action.

    Args:
        consensus_ref : dict avec keys {pt, median, currency, asof}. Format
            issu de portfolio_rules.yaml validé par Pydantic.
        native_currency : devise du ticker (EUR, USD, JPY, KRW, ...).
        fx_at_asof : fx (consensus_ref.currency → native_currency) à asof.
            Si consensus_ref.currency == native_currency, override à 1.0
            (la valeur passée est ignorée — contrat clair).

    Returns:
        dict {pt_native, median_native, fx_at_asof_used, asof, source_currency,
              native_currency} si tout OK.
        None si fail-closed L15 : consensus_ref manquant / fx invalide / PT
        invalide. Le caller décide quoi faire (log skip §4 SPEC).

    Invariant : aucune conversion en EUR cachée — tout reste en native_currency.
    """
    # Fail-closed §4 : pas de PT consensus → pas de conversion possible
    if not consensus_ref:
        return None
    pt = consensus_ref.get("pt")
    median = consensus_ref.get("median")
    src_currency = consensus_ref.get("currency")
    asof = consensus_ref.get("asof")
    if pt is None or median is None or not src_currency or asof is None:
        return None
    # Validate numeric inputs (fail-closed contre NaN/Inf, cf bug 'NaN%' 10/06)
    if not (math.isfinite(pt) and math.isfinite(median) and pt > 0 and median > 0):
        return None

    # No-op si les devises matchent (décision A2 : fx forcé à 1.0)
    if src_currency == native_currency:
        return {
            "pt_native": float(pt),
            "median_native": float(median),
            "fx_at_asof_used": 1.0,
            "asof": asof,
            "source_currency": src_currency,
            "native_currency": native_currency,
        }

    # Conversion fx (décision A : fx figé à asof par le caller)
    if not math.isfinite(fx_at_asof) or fx_at_asof <= 0:
        return None
    return {
        "pt_native": float(pt) * fx_at_asof,
        "median_native": float(median) * fx_at_asof,
        "fx_at_asof_used": fx_at_asof,
        "asof": asof,
        "source_currency": src_currency,
        "native_currency": native_currency,
    }


def compute_your_delta_native_pct(
    your_target_native: float,
    pt_native_asof: float,
    asof_price_native: float,
) -> float | None:
    """ton pari = (your_target - pt_native_asof) / asof_price_native × 100.

    Décision D : tout en native_currency, fx-strippé.

    Si positive → tu price plus haut que le consensus (bull thesis vs foule).
    Si negative → tu price plus bas que le consensus (bear thesis vs foule).

    Returns None si inputs invalides (fail-closed L15).
    """
    if not all(math.isfinite(x) for x in (your_target_native, pt_native_asof, asof_price_native)):
        return None
    if asof_price_native <= 0:
        return None
    return (your_target_native - pt_native_asof) / asof_price_native * 100.0


def compute_alpha_realized_pct(
    resolve_price_native: float,
    pt_native_asof: float,
    asof_price_native: float,
) -> float | None:
    """alpha = (resolve_price - pt_native_asof) / asof_price_native × 100.

    Décision D : tout en native_currency, fx-strippé. asof_price_native est
    le dénominateur partagé avec your_delta → leur différence et leur sign
    sont comparables par construction.

    Si positive → l'action a battu le PT consensus (la foule était trop basse).
    Si negative → l'action n'a pas atteint le PT (la foule était trop haute).

    Returns None si inputs invalides (fail-closed L15).
    """
    if not all(math.isfinite(x) for x in (resolve_price_native, pt_native_asof, asof_price_native)):
        return None
    if asof_price_native <= 0:
        return None
    return (resolve_price_native - pt_native_asof) / asof_price_native * 100.0


def classify_direction(
    your_delta_native_pct: float | None,
    alpha_realized_pct: float | None,
    epsilon_neutral_pct: float = 1.0,
    epsilon_delta_pct: float = 1.0,
) -> DirectionLabel | None:
    """Direction correct / incorrect / neutral / no_bet selon SPEC §3.1.

    Deux seuils symétriques (anti-trou-classify) :
    - ε_delta : si |your_delta| < ε_delta → 'no_bet'. Pas de variant view posée.
      Pendant symétrique de §6.8 SPEC ("pas de PT = pas de variant perception").
      Sans ce seuil, une pose your_target ≈ consensus serait scorée sur le sign
      fragile d'un delta minuscule (+0.1% vs -0.1% = verdicts opposés sur le
      même alpha).
    - ε_neutre : si |alpha| < ε_neutre → 'neutral'. Pari posé mais alpha plat
      à 12m, indistinguable de bruit.

    Les deux exclusions ('no_bet' + 'neutral') sont exclues de l'agrégation
    mais distinctes pour le diagnostic (no_bet fréquent = poses molles ;
    neutral fréquent = actions plates).

    Args:
        your_delta_native_pct : ton pari (signed pct, native)
        alpha_realized_pct : l'alpha réalisé observé
        epsilon_neutral_pct : seuil neutre alpha, défaut 1.0 (1% native)
        epsilon_delta_pct : seuil no-bet your_delta, défaut 1.0 (1% native)

    Returns:
        'no_bet'    si |your_delta| < ε_delta (pas de pari à scorer)
        'neutral'   si |alpha| < ε_neutre (alpha plat, bruit)
        'correct'   si signs égaux ET |alpha| ≥ ε_neutre ET |your_delta| ≥ ε_delta
        'incorrect' si signs opposés (mêmes conditions de seuil)
        None        si inputs invalides

    Ordre de priorité : no_bet > neutral > correct/incorrect. Une pose sans
    bet ne devient pas correcte par chance, quel que soit l'alpha.
    """
    if your_delta_native_pct is None or alpha_realized_pct is None:
        return None
    if not (math.isfinite(your_delta_native_pct) and math.isfinite(alpha_realized_pct)):
        return None
    if abs(your_delta_native_pct) < epsilon_delta_pct:
        return "no_bet"
    if abs(alpha_realized_pct) < epsilon_neutral_pct:
        return "neutral"
    same_sign = (your_delta_native_pct > 0) == (alpha_realized_pct > 0)
    return "correct" if same_sign else "incorrect"
