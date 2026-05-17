"""Canonical display formatting helpers for Telegram output.

CANONISATION CENTRALE ET DEFINITIVE: un seul point de verite pour le choix
de la canonical currency. Migration future (e.g. EUR -> USD) = flip
CANONICAL_FINANCE constant + storage migration accompagnante.

ARCHITECTURE:
- Currency enum: symbols centralized (no more inconsistent \\u20ac / \\u20AC mix)
- CANONICAL_FINANCE: enum value used for ALL finance display (positions,
  prices, MV, pnl, aggregates). Currently EUR.
- CANONICAL_BILLING: enum value for Anthropic/LLM billing. Structurally
  USD (Anthropic invoices USD). Independent of CANONICAL_FINANCE.
- format_money(value, currency): low-level primitive
- format_finance(value): uses CANONICAL_FINANCE — handlers call this
- format_billing(value): uses CANONICAL_BILLING — LLM cost callers use this

INVARIANT: format_finance(value) assumes `value` is already expressed
in CANONICAL_FINANCE. Caller responsible for ensuring storage-currency
matches display-currency at call time. Future USD migration requires
BOTH storage migration AND CANONICAL_FINANCE flip together.

Phase A: library creation + tests (no callers migration).
Phase B: per-handler migration in separate bounded scopes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Currency(StrEnum):
    """Currency identifiers with display symbols.

    Values are the symbols used in Telegram output. Extensible if more
    currencies are needed (GBP, JPY, etc.) but core canonical pair is
    EUR/USD per current finance + billing domains.
    """

    EUR = "\u20ac"
    USD = "$"


CANONICAL_FINANCE: Final[Currency] = Currency.EUR
"""Canonical currency for finance display (positions, prices, MV, pnl, aggregates).

Migration to USD-canonical = change this to Currency.USD + accompanying
storage migration (theses.entry_price, positions.avg_cost, fx layer).
Display layer auto-updates with no handler edits."""


CANONICAL_BILLING: Final[Currency] = Currency.USD
"""Canonical currency for Anthropic/LLM billing display.

Structurally USD (Anthropic invoices USD). Independent of CANONICAL_FINANCE.
If finance migrates to USD, billing remains USD — no special handling."""


NA_PCT = "  n/a "
"""Fixed-width placeholder for missing percentage values."""


def format_money(
    value: float,
    currency: Currency,
    decimals: int = 2,
    width: int | None = None,
    signed: bool = False,
) -> str:
    """Format money value with currency prefix. Low-level primitive.

    Most callers should use format_finance or format_billing to inherit
    canonical currency choices automatically.

    Args:
        value: numeric amount in `currency` units
        currency: Currency enum (EUR, USD, ...)
        decimals: digits after decimal point (default 2)
        width: pad numeric part to this width (None = no padding)
        signed: include explicit + sign for non-negative values (default False).
            Use for PnL display where direction matters (realized PnL, etc.).
    """
    sign_part = "+" if signed else ""
    if width is not None:
        return f"{currency.value}{value:>{sign_part}{width},.{decimals}f}"
    return f"{currency.value}{value:{sign_part},.{decimals}f}"


def format_finance(value: float, decimals: int = 2, width: int | None = None, signed: bool = False) -> str:
    """Format finance value (positions, MV, pnl, aggregates) in canonical currency.

    INVARIANT: `value` must already be expressed in CANONICAL_FINANCE.
    Caller is responsible for ensuring storage-currency matches at call site.

    Use signed=True for PnL displays where direction matters (realized PnL events).
    """
    return format_money(value, CANONICAL_FINANCE, decimals, width, signed=signed)


def format_billing(value: float, decimals: int = 2, width: int | None = None, signed: bool = False) -> str:
    """Format Anthropic/LLM billing value in CANONICAL_BILLING (USD).

    Use for LLM cost reporting, budget tracking, MTD spend, projections.
    signed=True for spend deltas if ever needed.
    """
    return format_money(value, CANONICAL_BILLING, decimals, width, signed=signed)


def format_pct(value: float, decimals: int = 1, signed: bool = True, width: int | None = None) -> str:
    """Format percentage. Input is RAW percentage (not ratio): 5 -> '5.0%'.

    Args:
        value: percentage value (e.g. 5.0 for 5%)
        decimals: digits after decimal (default 1)
        signed: include explicit + sign for non-negative (default True)
        width: pad to width (None = no padding)
    """
    # Normalize -0.0 + round-to-zero (UX: avoid "-0.0%" display artifact)
    rounded = round(value, decimals)
    if rounded == 0:
        value = 0.0
    sign = "+" if signed else ""
    formatted = f"{value:{sign}.{decimals}f}%"
    if width is not None:
        return f"{formatted:>{width}s}"
    return formatted


def format_pnl_pct(value: float | None, width: int = 7) -> str:
    """Format PnL percentage with sign. None -> fixed-width n/a placeholder."""
    if value is None:
        return f"{NA_PCT:>{width}s}"
    return format_pct(value, decimals=1, signed=True, width=width)


def format_position_line(
    ticker: str,
    name: str | None,
    conviction: int | None,
    avg_cost: float,
    current_price: float | None,
    market_value: float,
    pct_book: float,
    pnl_pct: float | None,
    *,
    ticker_width: int = 10,
    name_width: int = 24,
    conv_width: int = 4,
) -> str:
    """Canonical position line for /portfolio etc.

    All monetary inputs (avg_cost, current_price, market_value) must be in
    CANONICAL_FINANCE units.
    """
    name_safe = name if name else ticker
    name_trunc = name_safe[:name_width]
    conv_str = f"c{conviction}" if conviction else "c-"
    cur_str = format_finance(current_price, decimals=2, width=8) if current_price is not None else "  n/a  "
    pnl_str = format_pnl_pct(pnl_pct, width=7)

    return (
        f"  {ticker:<{ticker_width}s} {name_trunc:<{name_width}s} {conv_str:<{conv_width}s} "
        f"{format_finance(avg_cost, decimals=2, width=8)} "
        f"{cur_str:>9s} {format_finance(market_value, decimals=0, width=6)} "
        f"{pct_book:>4.1f}% {pnl_str:>7s}"
    )


def format_brief_position_line(
    ticker: str,
    name: str | None,
    conviction: int | None,
    value: float | None,
    pnl_pct: float | None,
    *,
    ticker_width: int = 9,
    name_width: int = 22,
    conv_width: int = 2,
) -> str:
    """Compact position line for /brief POSITIONS (Day 6 canonical 5-col layout).

    `value` in CANONICAL_FINANCE units.
    """
    name_safe = name if name else ticker
    name_trunc = name_safe[:name_width]
    conv_str = f"c{conviction}" if conviction else "c-"

    if value is None:
        return f"  {ticker:<{ticker_width}s} {name_trunc:<{name_width}s} {conv_str:<{conv_width}s}  (price n/a)"

    pnl_str = format_pct(pnl_pct, decimals=1, signed=True) if pnl_pct is not None else "n/a"
    return (
        f"  {ticker:<{ticker_width}s} {name_trunc:<{name_width}s} {conv_str:<{conv_width}s}  "
        f"{format_finance(value, decimals=0, width=6)}  {pnl_str}"
    )


def format_aggregate_line(
    label: str,
    market_value: float,
    pct_total: float,
    n_positions: int,
    pnl_pct: float,
    *,
    label_width: int = 28,
) -> str:
    """Canonical sector/narrative aggregate line.

    `market_value` in CANONICAL_FINANCE units.
    """
    return (
        f"  {label:<{label_width}s}  {format_finance(market_value, decimals=0, width=6)}  "
        f"[{pct_total:>4.1f}%]  ({n_positions} pos, PnL {format_pct(pnl_pct, decimals=1, signed=True)})"
    )
