"""
Position tracking — actual portfolio holdings (qty + avg_cost per ticker).
Full buy/sell history in position_events. Integrates with Phase 5 + 6 alerts.
"""

import logging
from datetime import UTC, datetime

from shared import prices
from shared.storage import db

log = logging.getLogger(__name__)


def _ensure_tables(cx) -> None:
    """No-op depuis migration 0048.

    positions est une VUE (créée par alembic), positions_meta + transactions
    sont créés par migration 0046. Le legacy CREATE INDEX positions ne fonctionne
    plus (SQLite refuse d'indexer une VUE).
    """
    # Conserve uniquement position_events qui est encore une table (audit legacy)
    cx.execute("""
        CREATE TABLE IF NOT EXISTS position_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER, ticker TEXT NOT NULL, event_type TEXT NOT NULL,
            qty REAL NOT NULL, price REAL, pnl REAL,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP, notes TEXT
        )
    """)
    cx.execute("CREATE INDEX IF NOT EXISTS idx_position_events_ticker "
               "ON position_events(ticker, timestamp)")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def cost_in(avg_cost_eur: float | None, target_cur: str = "USD") -> float | None:
    """Convert EUR-stored avg_cost to target currency. Canonical per ADR 005 (Day 13).

    Single source of truth: positions.avg_cost is ALWAYS stored EUR (Day 7
    broker import convention). Replaces 4+ ad-hoc handlers that wrongly
    multiplied by fx_native_to_X (treating EUR-stored value as native),
    producing 1000x+ P&L errors on JPY/KRW tickers (Lesson 15 audit Day 13).
    """
    if avg_cost_eur is None:
        return None
    tc = target_cur.upper()
    if tc == "EUR":
        return avg_cost_eur
    from shared.prices import get_fx_rate

    fx = get_fx_rate("EUR", tc) or 1.0
    return avg_cost_eur * fx


def _get_currency_and_fx(ticker: str) -> tuple[str, float, int]:
    """Resolve (currency, fx_at_trade, fx_is_derived) pour l'ingestion ledger.

    Convention SPEC_LEDGER §1.5 : currency dérivée du ticker via prices.get,
    fx_at_trade depuis le gateway fx_history. Si EUR → 1.0 figé.

    Retourne (currency, fx, fx_is_derived) — fx_is_derived=1 si fallback
    fx_history (pas un EUR débité TR autoritatif).
    """
    currency = prices.get_currency_for_ticker(ticker)
    if currency == "EUR":
        return "EUR", 1.0, 0
    fx_datum = prices.fx(currency, "EUR")
    if fx_datum is None or fx_datum.value is None:
        # Fallback : impossible de calculer le fx → ne pas insérer un trade
        # avec fx fabriqué (fail-closed L15)
        raise ValueError(
            f"Cannot resolve fx_at_trade for {currency}→EUR. "
            f"fx_history indispo → ingestion refusée (fail-closed)."
        )
    return currency, float(fx_datum.value), 1  # fx_is_derived=1 (pas TR EUR débité)


def set_position(ticker: str, qty: float, avg_cost: float, notes: str | None = None) -> dict:
    """Bootstrap d'une position existante via INSERT transaction BUY synthétique.

    Cf SPEC_LEDGER §3.1 (anchor pattern). Utilise l'astuce fx pour reproduire
    avg_cost en EUR exactement. À utiliser pour ré-anchorer une position
    connue-bonne (pas pour ingérer un trade réel — préférer add_buy pour ça).
    """
    ticker = ticker.upper()
    currency, fx_at_trade, fx_is_derived = _get_currency_and_fx(ticker)
    # Convention bootstrap : si l'appelant fournit avg_cost en EUR (canonical), on
    # stocke price_native = avg_cost EUR avec fx=1, currency=EUR. Le bootstrap est
    # EUR-only par convention (cf SPEC_LEDGER §3.1 anchor pattern).
    if currency != "EUR" and avg_cost > 0:
        currency, fx_at_trade, fx_is_derived = "EUR", 1.0, 0

    with db() as cx:
        cx.execute(
            "INSERT OR IGNORE INTO positions_meta (ticker, status, account, wrapper) "
            "VALUES (?, 'open', 'TR', 'CTO')",
            (ticker,),
        )
        cx.execute(
            "INSERT INTO transactions (ticker, side, qty, price_native, fees_native, "
            "currency, fx_at_trade, fx_is_derived, trade_date, broker_trade_id, "
            "source, is_anchor, notes) "
            "VALUES (?, 'BUY', ?, ?, 0, ?, ?, ?, ?, NULL, ?, 1, ?)",
            (ticker, qty, avg_cost, currency, fx_at_trade, fx_is_derived,
             _now(), f"set_position_bootstrap_{_now()[:10]}",
             notes or "set_position bootstrap (is_anchor=1, SPEC_LEDGER §3.1)"),
        )
        cx.commit()
    result = get_position(ticker)
    assert result is not None, "position lookup after set_position failed"
    return result


def add_buy(
    ticker: str, qty: float, price: float, notes: str | None = None,
    *, fees: float = 0.0, currency: str | None = None,
    fx_at_trade: float | None = None, broker_trade_id: str | None = None,
    source: str = "manual_add_buy", trade_date: str | None = None,
) -> dict:
    """Ingest a BUY trade into the immutable ledger (transactions table).

    #126 refactor : ce wrapper INSERT dans `transactions` (side='BUY') au lieu de
    UPDATE positions (qui est maintenant une VUE, SPEC_LEDGER §1). La VUE
    recalcule qty/PRU/realized_pnl automatiquement à la lecture.

    Side effects préservés :
      - auto_classify_new_ticker si premier BUY pour ce ticker
      - positions_meta créée si nouveau ticker

    Args:
      ticker, qty, price : identifiants minimaux du trade.
      notes : libre.
      fees : frais broker en devise native (défaut 0).
      currency : devise du prix. Si None, dérivée du ticker via prices.get.
      fx_at_trade : fx native→EUR. Si None, dérivé via fx_history (fx_is_derived=1).
      broker_trade_id : TR ID si dispo. UNIQUE constraint → idempotence DB.
      source : trace audit (chat / TR_export / etc).
      trade_date : ISO timestamp. Défaut now.
    """
    ticker = ticker.upper()
    if qty <= 0 or price <= 0:
        raise ValueError(f"qty and price must be positive, got qty={qty} price={price}")

    if currency is None or fx_at_trade is None:
        cur, fx, fx_derived = _get_currency_and_fx(ticker)
        currency = currency or cur
        if fx_at_trade is None:
            fx_at_trade = fx
            fx_is_derived = fx_derived
        else:
            fx_is_derived = 0
    else:
        fx_is_derived = 0

    trade_date = trade_date or _now()
    with db() as cx:
        # Detect new entry for auto_classify hook (avant INSERT)
        was_new_entry = cx.execute(
            "SELECT 1 FROM transactions WHERE ticker = ? AND side = 'BUY' LIMIT 1",
            (ticker,),
        ).fetchone() is None

        cx.execute(
            "INSERT OR IGNORE INTO positions_meta (ticker, status, account, wrapper) "
            "VALUES (?, 'open', 'TR', 'CTO')",
            (ticker,),
        )
        cx.execute(
            "INSERT INTO transactions (ticker, side, qty, price_native, fees_native, "
            "currency, fx_at_trade, fx_is_derived, trade_date, broker_trade_id, "
            "source, is_anchor, notes) "
            "VALUES (?, 'BUY', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (ticker, qty, price, fees, currency, fx_at_trade, fx_is_derived,
             trade_date, broker_trade_id, source, notes),
        )
        cx.commit()

    if was_new_entry:
        _auto_classify_new_ticker(ticker)

    result = get_position(ticker)
    assert result is not None, "position lookup after add_buy failed"
    return result


def _auto_classify_new_ticker(ticker: str) -> None:
    """Best-effort auto-classification pour nouveaux tickers (axes + meta).

    Verifie si deja classifie ; sinon lance les 2 classifications. Non-bloquant.
    Cost : ~$0.025 (2 LLM calls Sonnet/Haiku, ~$0.012 + $0.012).
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        from shared.storage import get_all_latest_ticker_axes, get_all_latest_ticker_meta

        axes_tks = {a["ticker"] for a in get_all_latest_ticker_axes()}
        meta_tks = {m["ticker"] for m in get_all_latest_ticker_meta()}

        if ticker not in axes_tks:
            try:
                from intelligence import ticker_classifier
                ticker_classifier.classify_ticker(ticker)
                logger.info(f"auto-classified axes for new ticker {ticker}")
            except Exception as e:
                logger.warning(f"auto-classify axes {ticker} failed: {e}")

        if ticker not in meta_tks:
            try:
                from intelligence import ticker_meta_classifier
                ticker_meta_classifier.classify_one(ticker)
                logger.info(f"auto-classified meta for new ticker {ticker}")
            except Exception as e:
                logger.warning(f"auto-classify meta {ticker} failed: {e}")
    except Exception as e:
        logger.warning(f"_auto_classify_new_ticker {ticker} failed: {e}")


def add_sell(
    ticker: str, qty: float, price: float, notes: str | None = None,
    *, fees: float = 0.0, currency: str | None = None,
    fx_at_trade: float | None = None, broker_trade_id: str | None = None,
    source: str = "manual_add_sell", trade_date: str | None = None,
) -> dict:
    """Ingest a SELL trade into the immutable ledger (transactions table).

    #126 refactor : INSERT side='SELL' au lieu de UPDATE positions. La VUE
    recalcule qty/realized_pnl automatiquement via la sous-requête corrélée
    PRU-pré-vente (SPEC_LEDGER §2.2).

    Side effects préservés :
      - Validation : position ouverte, qty ≤ current qty (depuis VUE)
      - lock_in_detector.detect_winner_sell hook (L7 silent miss)

    Returns:
        dict avec realized_pnl_event (P&L event-level), remaining_qty (depuis VUE),
        closed (True si remaining_qty ≈ 0).
    """
    ticker = ticker.upper()
    if qty <= 0 or price <= 0:
        raise ValueError(f"qty and price must be positive, got qty={qty} price={price}")

    # Validation pré-vente depuis la VUE
    current = get_position(ticker)
    if not current or (current.get("qty") or 0) <= 0:
        raise ValueError(f"No open position for {ticker}")
    qty_before = float(current["qty"])
    if qty > qty_before + 1e-9:
        raise ValueError(f"Sell qty {qty} > position qty {qty_before}")
    # Cure 13/06 (#133bis pattern) : VUE.avg_cost_* est NULL par construction
    # depuis migration #105 (positions VUE derivee, PMP roulant computed live
    # via BookLine + ledger_pmp). Avant : fallback 0 => realized_pnl_event
    # falsifie a qty × price (revenue total au lieu du vrai PnL). Critique
    # avant file de sells (trim/exit) -> chaque vente polluait le ledger.
    # Cure : prefer BookLine.avg_cost_eur (canonique), fallback VUE puis 0.
    avg_cost_pre = 0.0
    try:
        from shared import book as _bk
        _bl = _bk.get_book_index().get(ticker)
        if _bl and _bl.avg_cost_eur:
            avg_cost_pre = float(_bl.avg_cost_eur)
    except Exception:
        pass
    if avg_cost_pre <= 0:
        # Fallback legacy (VUE / static columns) si BookLine indispo
        avg_cost_pre = float(current.get("avg_cost_eur") or current.get("avg_cost") or 0)

    if currency is None or fx_at_trade is None:
        cur, fx, fx_derived = _get_currency_and_fx(ticker)
        currency = currency or cur
        if fx_at_trade is None:
            fx_at_trade = fx
            fx_is_derived = fx_derived
        else:
            fx_is_derived = 0
    else:
        fx_is_derived = 0

    trade_date = trade_date or _now()
    with db() as cx:
        cx.execute(
            "INSERT INTO transactions (ticker, side, qty, price_native, fees_native, "
            "currency, fx_at_trade, fx_is_derived, trade_date, broker_trade_id, "
            "source, is_anchor, notes) "
            "VALUES (?, 'SELL', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (ticker, qty, price, fees, currency, fx_at_trade, fx_is_derived,
             trade_date, broker_trade_id, source, notes),
        )
        cx.commit()

    # P&L event-level (en EUR via fx_at_trade) pour le hook + return
    # PRU pre-sell est en EUR (current["avg_cost_eur"]). price * fx = sell EUR per share.
    sell_eur_per_share = price * fx_at_trade
    pnl_event = qty * (sell_eur_per_share - avg_cost_pre) - fees * fx_at_trade
    new_qty = qty_before - qty
    closed = new_qty <= 1e-6

    # lock_in_detector hook (post-commit, L7 silent miss accepté)
    try:
        from intelligence.lock_in_detector import detect_winner_sell
        # Note : detect_winner_sell signature legacy attend position_id (int).
        # Maintenant que positions est une VUE, l'id est m.rowid de positions_meta.
        position_id = current.get("id") if isinstance(current.get("id"), int) else None
        # L12 invariant : sold_price_eur et avg_cost doivent etre meme devise (EUR/share).
        # Avant 23/06 on passait price (USD natif) -> classify_lock_in calculait pnl_pct
        # avec USD/EUR mix, biaisant les gates 15% et halfway target.
        detect_winner_sell(
            position_id=position_id, ticker=ticker,
            qty_sold=qty, sold_price_eur=sell_eur_per_share,
            qty_before=qty_before, avg_cost=avg_cost_pre,
        )
    except Exception as e:
        log.warning(f"lock_in_detector silent miss for {ticker}: {e}", exc_info=True)

    return {
        "ticker": ticker,
        "sold_qty": qty,
        "sold_price": price,
        "avg_cost": avg_cost_pre,
        "realized_pnl_event": pnl_event,
        "remaining_qty": max(new_qty, 0),
        "closed": closed,
    }


def _enrich_with_live(d: dict, target_cur: str = "EUR") -> dict:
    """Enrich position dict with live current_price, market_value, unrealized_pnl.

    Day 13 ADR 005: FM-10 latent currency mix RESOLVED. avg_cost is EUR-canonical
    stored (empirical truth confirmed Day 13 audit, contrary to Day 11 Batch 4A
    aspirational comment about NATIVE storage). Convert avg_cost EUR -> target_cur
    via cost_in helper for coherent (price, cost) pair in same currency.
    """
    if d["qty"] <= 0:
        return d
    try:
        p = prices.get_current_price_in(d["ticker"], target_cur)
        if p:
            avg_cost_target = cost_in(d["avg_cost"], target_cur)
            d["current_price"] = p
            d["market_value"] = p * d["qty"]
            if avg_cost_target:
                d["unrealized_pnl"] = (p - avg_cost_target) * d["qty"]
                d["unrealized_pct"] = (p - avg_cost_target) / avg_cost_target
    except Exception as e:
        log.warning(f"live price fetch {d['ticker']}: {e}")
    return d


def get_position(ticker: str) -> dict | None:
    ticker = ticker.upper()
    with db() as cx:
        _ensure_tables(cx)
        r = cx.execute("SELECT * FROM positions WHERE ticker=? AND status='open'", (ticker,)).fetchone()
    if not r:
        return None
    return _enrich_with_live(dict(r))


def list_positions(status: str = "open") -> list:
    with db() as cx:
        _ensure_tables(cx)
        rows = cx.execute("SELECT * FROM positions WHERE status=? ORDER BY ticker", (status,)).fetchall()
    out = [_enrich_with_live(dict(r)) for r in rows]
    out.sort(key=lambda x: -(x.get("market_value") or 0))
    return out


def get_history(ticker: str, limit: int = 50) -> list:
    ticker = ticker.upper()
    with db() as cx:
        _ensure_tables(cx)
        rows = cx.execute(
            "SELECT * FROM position_events WHERE ticker=? ORDER BY id DESC LIMIT ?", (ticker, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def format_positions_summary(positions: list) -> str:
    if not positions:
        return "No open positions."
    lines = ["📊 Open positions:"]
    total_mv, total_upl = 0, 0
    for p in positions:
        qty, avg = p.get("qty", 0), p.get("avg_cost", 0)
        mv, upl, upct = p.get("market_value"), p.get("unrealized_pnl"), p.get("unrealized_pct")
        cur = p.get("current_price")
        if mv:
            total_mv += mv
        if upl:
            total_upl += upl
        if cur:
            sign = "🟢" if (upl or 0) > 0 else "🔴"
            # ADR 005: avg_cost EUR canonical; _enrich_with_live default target_cur=EUR
            # so avg/cur/mv/upl all in EUR. Label € (no conversion needed).
            lines.append(f"  {sign} {p['ticker']:6s} {qty:>9.3f} @ €{avg:.2f} → €{cur:.2f}")
            lines.append(f"       MV €{mv:>10,.0f}  UPL €{upl:+,.0f} ({upct:+.1%})")
        else:
            lines.append(f"  ⚪ {p['ticker']:6s} {qty:>9.3f} @ €{avg:.2f} (no live price)")
    lines.append("")
    lines.append(f"  Total MV:  €{total_mv:>11,.0f}")
    lines.append(f"  Total UPL: €{total_upl:>+11,.0f}")
    return "\n".join(lines)


def format_position_detail(p: dict, history: list) -> str:
    if not p:
        return "No open position."
    lines = [f"📋 {p['ticker']} position"]
    lines.append(f"  Qty:            {p['qty']:.3f}")
    lines.append(f"  Avg cost:       €{p['avg_cost']:.2f}")  # ADR 005: EUR canonical
    lines.append(f"  Realized PnL:   ${(p.get('realized_pnl') or 0):+,.2f}")
    if p.get("current_price"):
        lines.append(f"  Current price:  €{p['current_price']:.2f}")  # ADR 005: EUR via _enrich_with_live
        lines.append(f"  Market value:   €{p['market_value']:,.2f}")
        lines.append(f"  Unrealized PnL: €{p['unrealized_pnl']:+,.2f} ({p['unrealized_pct']:+.1%})")
    lines.append(f"  Opened:         {p.get('opened_at', '?')[:10]}")
    if history:
        lines.append("")
        lines.append("  History (last 10):")
        for h in history[:10]:
            sign = "+" if h["event_type"] == "buy" else "-" if h["event_type"] == "sell" else "~"
            ln = f"    {h.get('timestamp', '')[:10]}  {h['event_type']:6s} {sign}{h['qty']:.3f} @ ${h.get('price', 0):.2f}"
            if h.get("pnl") is not None:
                ln += f"  PnL ${h['pnl']:+,.2f}"
            lines.append(ln)
    return "\n".join(lines)
