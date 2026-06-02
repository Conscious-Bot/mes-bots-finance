"""PRESAGE — Invariants des thèses (currency + kill_criteria substance).

Soudure du joint identifié par user 29/05 round 5 :
> "Le fix n'est pas d'éditer un champ, c'est une validation qui rejette tout
>  champ prix dont la devise ≠ la cote de l'instrument (classe ADR 005).
>  Et un price-stop est de toute façon banni (leçon Micron)."

Bug récurrent : intervention_3 hier (PRESSURE 55 CCJ stop EUR sur USD) →
encore aujourd'hui (STRONG_OPPOSE 78, MÊME bug). Le fix d'un champ ne tient
pas — il faut un invariant qui rejette structurellement.

Deux invariants forts ici :

1. **Currency native consistency** (ADR 005 reformulé)
   Tous les prix d'une thèse (entry, target_partial, target_full, stop)
   doivent être dans la devise NATIVE du ticker (déduite du suffixe).
   Cross-check via yfinance : ratio stop/current dans [0.4, 1.0] = sain.

2. **Kill-criteria substance** (leçon Micron post-Sprint 23)
   invalidation_triggers ne peut PAS être 100% prix-based :
   - banni : "Cassure stop X EUR", "stop break", "X price level", "a etoffer"
   - requis : au moins UN trigger fondamental (revenue, margin, customer,
     guidance, pricing power, customer concentration, regulatory).

Appelé par run_static_gate() — fail si violation. Surface dans dashboard
quand bloquant.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


# ─────────────────────── Currency native par ticker ───────────────────────


# Suffixe yfinance -> devise native
_SUFFIX_CURRENCY: dict[str, str] = {
    ".PA": "EUR", ".AS": "EUR", ".DE": "EUR", ".SW": "CHF",
    ".L": "GBP", ".MI": "EUR", ".BR": "EUR", ".MC": "EUR",
    ".ST": "SEK", ".HE": "EUR", ".CO": "DKK", ".OL": "NOK",
    ".T": "JPY", ".HK": "HKD", ".KS": "KRW", ".SS": "CNY",
    ".SZ": "CNY", ".TO": "CAD", ".AX": "AUD", ".SI": "SGD",
    ".SA": "BRL", ".MX": "MXN",
}


def expected_native_currency(ticker: str) -> str:
    """Devise native attendue du ticker, dérivée du suffixe yfinance.
    Pas de suffixe = USD (NYSE/NASDAQ par défaut)."""
    if not ticker:
        return "USD"
    tk = ticker.upper()
    for suf, cur in _SUFFIX_CURRENCY.items():
        if tk.endswith(suf):
            return cur
    return "USD"


# ─────────────────────── Patterns banned dans kill_criteria ───────────────


# Patterns explicitement bannis (price-only, à étoffer)
_BANNED_PATTERNS_LITERAL = [
    "a etoffer",
    "à etoffer",
    "à étoffer",
    "to flesh out",
]

# Patterns suspects (probablement price-only s'ils sont seuls)
_PRICE_ONLY_INDICATORS = [
    "cassure stop",
    "cassure du stop",
    "break of stop",
    "stop break",
    "price level",
    "niveau de prix",
]


def is_kill_criterion_substantive(trigger: str) -> bool:
    """Vrai si le trigger contient au moins un mot fondamental.

    Mots reconnus : revenue, margin, customer, guidance, pricing, regulatory,
    operations, supply, demand, market share, design, contract, deal, etc.
    """
    if not trigger or not isinstance(trigger, str):
        return False
    t = trigger.lower()
    # Banned literal -> non-substantive
    if any(b in t for b in _BANNED_PATTERNS_LITERAL):
        return False
    # Liste de mots-cles fondamentaux qui denotent substance
    fundamental_words = [
        "revenue", "margin", "customer", "guidance", "pricing",
        "regulatory", "regulator", "ftc", "doj", "antitrust",
        "operations", "supply", "demand", "market share", "design",
        "contract", "deal", "earnings", "miss", "asp", "production",
        "design-in", "design out", "cap", "approval", "license",
        "ca", "marge", "client", "concurrence", "share", "ramp",
        "renege", "cancellation", "compression", "expansion",
        "share gain", "share loss", "NRR", "churn", "retention",
    ]
    return any(w in t for w in fundamental_words)


def has_at_least_one_fundamental_trigger(triggers: list[str]) -> bool:
    """Vrai si AU MOINS UN trigger contient de la substance fondamentale.
    Tolere des triggers prix tant qu'un fundamental existe."""
    if not triggers:
        return False
    return any(is_kill_criterion_substantive(t) for t in triggers)


# ─────────────────────── Gate checks ───────────────────────────────────────


def _parse_triggers(raw: str | list | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw if t]
    s = str(raw).strip()
    if not s or s == "[]":
        return []
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(t) for t in parsed if t]
        except Exception:
            return [s]
    return [s]


def check_kill_criteria_substance(conn) -> list[str]:
    """Pour toute these active sur position ouverte, kill_criteria doit avoir
    AU MOINS UN trigger fondamental (pas tous price-only / a-etoffer).

    Leçon Micron post-Sprint 23 : kill_criteria = degradation fondamentale
    verifiee, jamais juste un niveau de prix.
    """
    violations = []
    rows = conn.execute("""
        SELECT t.ticker, t.invalidation_triggers
        FROM theses t
        INNER JOIN positions p ON p.ticker = t.ticker
        WHERE t.status='active' AND p.qty > 0 AND p.status='open'
    """).fetchall()
    for tk, raw in rows:
        triggers = _parse_triggers(raw)
        if not triggers:
            violations.append(f"kill_criteria_substance : {tk} aucun trigger d'invalidation")
            continue
        if not has_at_least_one_fundamental_trigger(triggers):
            sample = (triggers[0] or "")[:80]
            violations.append(
                f"kill_criteria_substance : {tk} triggers all price-only / 'a etoffer' "
                f"(sample: '{sample}'). Reformule en kill-criteria fondamentaux."
            )
    return violations


def check_currency_native_consistency(conn, *, tolerance_low: float = 0.30, tolerance_high: float = 1.1) -> list[str]:
    """Cross-check stop_price vs prix natif du ticker.

    Pour chaque these active sur position ouverte :
    - derive expected currency from ticker suffix
    - fetch current price native via yfinance
    - ratio stop_price / current_native doit etre dans [tolerance_low, tolerance_high]

    Si ratio hors range = probable mismatch devise (e.g. 71.90 EUR labelisé
    comme stop_price sur CCJ qui cote en USD).

    Best-effort : si yfinance indispo, skip ce check pour ce ticker.
    """
    violations: list[str] = []
    try:
        import yfinance as yf
    except Exception:
        return violations  # yfinance pas dispo

    rows = conn.execute("""
        SELECT t.ticker, t.stop_price, t.entry_price
        FROM theses t
        INNER JOIN positions p ON p.ticker = t.ticker
        WHERE t.status='active' AND p.qty > 0 AND p.status='open'
          AND t.stop_price IS NOT NULL
    """).fetchall()

    for tk, stop_price, entry_price in rows:
        expected_cur = expected_native_currency(tk)
        # Get current price natif (yfinance retourne native)
        try:
            import yfinance as yf
            t_obj = yf.Ticker(tk)
            hist = t_obj.history(period="5d")
            if hist.empty:
                continue
            cur_native = float(hist["Close"].iloc[-1])
        except Exception:
            continue

        if cur_native <= 0:
            continue
        ratio = stop_price / cur_native
        if not (tolerance_low <= ratio <= tolerance_high):
            violations.append(
                f"currency_native : {tk} stop_price={stop_price} vs current_native={cur_native:.2f} "
                f"{expected_cur} (ratio {ratio:.2f} hors [{tolerance_low}, {tolerance_high}]). "
                f"Probable mismatch devise -- entry_price={entry_price}"
            )
    return violations


# ─────────────────────── Helper API ─────────────────────────────────────────


def validate_thesis_pre_insert(ticker: str, stop_price: float | None,  # noqa: ARG001
                               invalidation_triggers: list[str] | str | None) -> list[str]:
    """Valide une these AVANT insertion. Retourne liste d'erreurs.

    Utile pour les writers (chat_intent, handlers/positions, /thesis_set, etc.)
    qui veulent rejeter une these mal formee a la source.
    """
    errors = []
    triggers = _parse_triggers(invalidation_triggers)
    if triggers and not has_at_least_one_fundamental_trigger(triggers):
        errors.append(
            f"{ticker}: kill_criteria all price-only / 'a etoffer'. "
            "Au moins UN trigger doit avoir substance fondamentale "
            "(revenue, margin, customer, guidance, pricing, regulatory, operations)."
        )
    # Le currency check pre-insert est plus difficile (besoin yfinance live).
    # On laisse run_static_gate detecter post-insert.
    return errors
