"""Pre-trade context check (friction décision #1).

Doctrine 06/06 : transformer dashboard passif en système qui INTERVIENT
au moment de la décision. Avant /trade buy/sell, surface obligatoire :
  1. Régime macro + chip warnings du ticker
  2. Composition cluster avant -> après
  3. Bias détecté (lock_in pour sell winner, fomo pour buy après run)
  4. Signaux 30j ticker

Pattern 2-step confirm : /trade buy ... → renvoie context + token TTL 60s.
/trade confirm <token> exécute. /trade cancel <token> annule.

Discipline mecanisee, pas blocking : on montre, on ne bloque pas.
"""

from __future__ import annotations

import logging
import secrets
import time as _t
from typing import Any, TypedDict

from shared import storage

log = logging.getLogger(__name__)


class PendingTrade(TypedDict):
    token: str
    action: str  # 'buy' | 'sell'
    ticker: str
    qty: float
    price: float
    reasoning: str
    expires_at: float
    chat_id: int


_PENDING: dict[str, PendingTrade] = {}
_TTL = 60.0  # 60 sec TTL pour confirm


def _gc_expired() -> None:
    now = _t.time()
    expired = [t for t, p in _PENDING.items() if p["expires_at"] < now]
    for t in expired:
        del _PENDING[t]


def store_pending(action: str, ticker: str, qty: float, price: float,
                  reasoning: str, chat_id: int) -> str:
    """Genere token court + stocke. Returns token."""
    _gc_expired()
    token = secrets.token_hex(3)  # 6 hex chars, e.g. "a3f7b2"
    _PENDING[token] = PendingTrade(
        token=token,
        action=action,
        ticker=ticker.upper(),
        qty=qty,
        price=price,
        reasoning=reasoning,
        expires_at=_t.time() + _TTL,
        chat_id=chat_id,
    )
    return token


def pop_pending(token: str) -> PendingTrade | None:
    """Retire et retourne le pending si non-expire, sinon None."""
    _gc_expired()
    return _PENDING.pop(token, None)


def get_pending(token: str) -> PendingTrade | None:
    """Lit sans retirer (pour preview)."""
    _gc_expired()
    return _PENDING.get(token)


def compute_trade_context(action: str, ticker: str, qty: float, price: float) -> dict[str, Any]:
    """Compute les 4 contextes pour pre-trade surface.

    Returns dict :
        regime, score, regime_warnings (list de rule_id),
        cluster_id, cluster_share_pct_now, cluster_share_pct_after,
        bias_warnings (list de phrases FR),
        signals_30d_str (phrase FR),
        warnings_summary (list haut-niveau)
    """
    ctx: dict[str, Any] = {
        "ticker": ticker.upper(),
        "action": action,
        "qty": qty,
        "price": price,
    }

    # 1. Régime + warnings ticker
    try:
        from shared.calibration import get_concentration_caps
        from shared.macro_state import current_macro_state
        ms = current_macro_state()
        ctx["regime"] = ms["regime"]
        ctx["score"] = ms["score"]
        ctx["bucket_counts"] = ms["bucket_counts"]
    except Exception as e:
        log.warning(f"trade_context regime: {e}")
        ctx["regime"] = "?"
        ctx["score"] = 0
        ctx["bucket_counts"] = {}

    # 2. Composition cluster avant -> apres (simulate post-trade)
    positions: list[dict] = []
    try:
        from shared.sectors import book_composition_by_sector, sector_for_ticker
        with storage.db() as cx:
            positions = [
                {"ticker": r[0], "qty": float(r[1] or 0), "avg_cost": float(r[2] or 0)}
                for r in cx.execute(
                    "SELECT ticker, qty, avg_cost FROM positions WHERE qty > 0"
                ).fetchall()
            ]
        sector = sector_for_ticker(ticker.upper())
        cluster_id = sector["id"] if sector else "uncat"
        ctx["cluster_id"] = cluster_id
        # Composition courante
        comp_before = book_composition_by_sector(positions)
        ctx["cluster_share_pct_now"] = comp_before.get(cluster_id, {}).get("share_pct", 0.0)
        # Simulate post-trade
        positions_after: list[dict] = []
        found = False
        for p in positions:
            if p["ticker"] == ticker.upper():
                found = True
                new_qty = p["qty"] + qty if action == "buy" else p["qty"] - qty
                # Si vente totale ou plus, retirer
                if new_qty > 0:
                    # avg_cost recalculation simplifie : on garde avg_cost actuel pour cluster_share
                    # (l'estimate share post-trade est approx, suffisant pour friction)
                    positions_after.append({**p, "qty": new_qty})
            else:
                positions_after.append(p)
        if not found and action == "buy":
            positions_after.append({"ticker": ticker.upper(), "qty": qty, "avg_cost": price})
        comp_after = book_composition_by_sector(positions_after)
        ctx["cluster_share_pct_after"] = comp_after.get(cluster_id, {}).get("share_pct", 0.0)
        ctx["cluster_delta_pp"] = ctx["cluster_share_pct_after"] - ctx["cluster_share_pct_now"]
    except Exception as e:
        log.warning(f"trade_context cluster: {e}")
        ctx["cluster_id"] = "?"
        ctx["cluster_share_pct_now"] = 0.0
        ctx["cluster_share_pct_after"] = 0.0
        ctx["cluster_delta_pp"] = 0.0

    # 3. Warnings macro ticker (R1/R2/...)
    try:
        from intelligence.macro_book_warnings import compute_book_warnings
        ind_vals = {
            k: (v.get("value") if isinstance(v, dict) else None)
            for k, v in ms.get("readings_for_regime", {}).items()
        }
        all_warnings = compute_book_warnings(ms["regime"], positions, ind_vals)
        ticker_warnings = [
            w for w in all_warnings
            if ticker.upper() in [t.upper() for t in w.get("tickers", [])]
        ]
        ctx["regime_warnings"] = [
            {"rule_id": w["rule_id"], "severity": w["severity"], "action": w["action"]}
            for w in ticker_warnings
        ]
    except Exception as e:
        log.warning(f"trade_context warnings: {e}")
        ctx["regime_warnings"] = []

    # 4. Bias detection (lock_in pour sell winner, fomo pour buy après run)
    # + min_positions garde-fou (anti-overdilution) v5 audit
    # + Elder circuit breaker check pour BUY (gate si DD > 6%/mois)
    bias_warnings: list[str] = []
    # Circuit breaker Elder : si actif et action=buy, warning explicit
    try:
        from intelligence.circuit_breaker import check_circuit_breaker
        cb_state = check_circuit_breaker()
        if action == "buy" and cb_state.get("active"):
            bias_warnings.append(
                f"CIRCUIT BREAKER ACTIVE : portfolio DD "
                f"{cb_state.get('dd_pct', 0):+.1f}% sur 30j (seuil Elder rule "
                f"{-cb_state.get('threshold_pct', 6):.0f}%). Nouvelles positions "
                f"deconseilles jusqu'a recovery."
            )
    except Exception as _e:
        log.warning(f"trade_context circuit_breaker: {_e}")
    # Min positions check : si SELL ferait passer sous min, warning
    try:
        from shared.calibration import get_concentration_caps
        min_pos = int(get_concentration_caps().get("min_open_positions") or 8)
        if action == "sell" and positions:
            pos = storage.get_position_by_ticker(ticker.upper())
            current_n = len([p for p in positions if float(p.get("qty", 0)) > 0])
            qty_remaining = (float(pos.get("qty", 0)) - qty) if pos else 0
            future_n = current_n - (1 if qty_remaining <= 0 else 0)
            if future_n < min_pos:
                bias_warnings.append(
                    f"OVERDILUTION risk : sell complete amenerait book a "
                    f"{future_n} positions (< min {min_pos}). Reconsidere "
                    f"taille de la sortie (sweet spot 8-20 concentre)."
                )
    except Exception as _e:
        log.warning(f"trade_context min_positions: {_e}")
    try:
        # Get current position state
        pos = storage.get_position_by_ticker(ticker.upper())
        if pos:
            avg_cost = float(pos.get("avg_cost") or 0)
            if avg_cost > 0:
                pnl_pct = (price - avg_cost) / avg_cost * 100
                if action == "sell" and pnl_pct >= 15.0:
                    # Check conviction si thesis dispo
                    thesis = storage.get_thesis_by_ticker(ticker.upper())
                    if thesis and int(thesis.get("conviction") or 0) >= 3:
                        bias_warnings.append(
                            f"LOCK_IN risk : tu vends un winner (+{pnl_pct:.1f}%) "
                            f"avec conviction c{thesis['conviction']}. "
                            f"Sur-vente winner = biais #1 documente."
                        )
        # FOMO check pour buy : ticker en hausse +15% sur 7d ?
        if action == "buy":
            try:
                # SOCLE S1c (#111) : migré yf.Ticker → prices.ensure_price_history.
                from datetime import UTC, datetime, timedelta

                from shared.prices import ensure_price_history
                end_dt = datetime.now(UTC)
                start_dt = end_dt - timedelta(days=10)
                h_df = ensure_price_history(
                    ticker.upper(), start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"),
                )
                price_col = "price_native" if (h_df is not None and "price_native" in h_df.columns) else "Close"
                h = h_df[price_col].dropna() if (h_df is not None and not h_df.empty) else None
                if h is not None and len(h) >= 6:
                    perf_7d = (float(h.iloc[-1]) - float(h.iloc[-6])) / float(h.iloc[-6]) * 100
                    if perf_7d >= 15.0:
                        bias_warnings.append(
                            f"FOMO risk : ticker en hausse {perf_7d:+.1f}% sur 7j. "
                            f"Acheter apres un run = candidate FOMO."
                        )
            except Exception:
                pass
    except Exception as e:
        log.warning(f"trade_context bias: {e}")
    ctx["bias_warnings"] = bias_warnings

    # 5. Signaux 30j (recent_outlook)
    try:
        from shared.ticker_outlook import outlook_phrase, recent_outlook
        ctx["signals_30d_str"] = outlook_phrase(recent_outlook(ticker.upper()))
    except Exception as e:
        log.warning(f"trade_context outlook: {e}")
        ctx["signals_30d_str"] = "Signaux 30j indisponibles."

    return ctx


def format_context_message(ctx: dict[str, Any], token: str) -> str:
    """Format MarkdownV2-friendly pour Telegram."""
    action_upper = ctx["action"].upper()
    tk = ctx["ticker"]
    qty = ctx["qty"]
    price = ctx["price"]

    lines = [
        f"PRE-CHECK TRADE — {action_upper} {tk} {qty} @ {price}",
        "",
        f"Regime : {ctx.get('regime', '?')} (V3 score {ctx.get('score', 0):.0f})",
    ]

    buckets = ctx.get("bucket_counts", {})
    if buckets:
        lines.append(
            f"  ACT {buckets.get('act', 0)} / WATCH {buckets.get('watch', 0)} / "
            f"CALM {buckets.get('calm', 0)} / SILENT {buckets.get('silent', 0)}"
        )

    # Warnings ticker
    rws = ctx.get("regime_warnings") or []
    if rws:
        lines.append("")
        lines.append(f"Warnings {tk} :")
        for w in rws:
            sev = w["severity"].upper()
            rid = w["rule_id"].split("_")[0]
            lines.append(f"  [{sev}] {rid} — {w['action']}")
    else:
        lines.append("")
        lines.append(f"Aucune warning macro active sur {tk}.")

    # Cluster delta
    cid = ctx.get("cluster_id", "?")
    cnow = ctx.get("cluster_share_pct_now", 0)
    cafter = ctx.get("cluster_share_pct_after", 0)
    delta = ctx.get("cluster_delta_pp", 0)
    if cid != "uncat":
        lines.append("")
        sign = "+" if delta >= 0 else ""
        lines.append(f"Impact cluster {cid} : {cnow:.1f}% -> {cafter:.1f}% ({sign}{delta:.1f}pp)")

    # Bias
    bws = ctx.get("bias_warnings") or []
    if bws:
        lines.append("")
        lines.append("Bias check :")
        for b in bws:
            lines.append(f"  ⚠ {b}")
    else:
        lines.append("")
        lines.append("Bias check : aucun detecte.")

    # Signaux 30j
    sig = ctx.get("signals_30d_str", "")
    if sig:
        lines.append("")
        lines.append(sig)

    # Token + confirm
    lines.append("")
    lines.append(f"Token : {token} (TTL 60s)")
    lines.append(f"Confirme : /trade confirm {token}")
    lines.append(f"Annule : /trade cancel {token}")

    return "\n".join(lines)
