"""
Price monitor — fetch live price per active thesis, detect FIRST crossing
of target_partial / target_full / stop_price, fire Telegram alerts with
context (insider 90d, regime, earnings proximity).

Cron: 15min, 14h-22h Paris, lundi-vendredi (US market hours coverage).

Also: populate clv_7d/30d/90d milestones once windows pass.
Also: capture user overrides via record_override() for BiasDetector training.
"""
import logging
from datetime import date, datetime

from shared import edgar, notify, prices
from shared.storage import db

log = logging.getLogger(__name__)


def _ensure_columns(cx) -> None:
    """ALTER TABLE theses — add trigger tracking columns if missing."""
    cols = [r['name'] for r in cx.execute("PRAGMA table_info(theses)").fetchall()]
    for col, typ in [
        ('triggered_partial_at', 'TEXT'),
        ('triggered_full_at',    'TEXT'),
        ('triggered_stop_at',    'TEXT'),
        ('last_price',           'REAL'),
        ('last_price_at',        'TEXT'),
    ]:
        if col not in cols:
            cx.execute(f"ALTER TABLE theses ADD COLUMN {col} {typ}")


def _ensure_overrides_table(cx) -> None:
    cx.execute("""
        CREATE TABLE IF NOT EXISTS overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            thesis_id INTEGER,
            level TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _build_context(ticker: str) -> list:
    lines = []
    try:
        brief = edgar.get_insider_brief(ticker)
        if brief and brief.get('net_m') is not None:
            net = brief['net_m']
            sign = '🔴' if net < -30 else ('🟢' if net > 5 else '⚪')
            lines.append(f"  {sign} Insider 90d: net ${net:+.0f}M "
                         f"({brief.get('n_buys',0)}B/{brief.get('n_sells',0)}S)")
    except Exception as e:
        log.warning(f"insider context {ticker}: {e}")
    try:
        from intelligence import regime as regime_mod
        r = regime_mod.detect_regime()
        if r:
            overall = r.get('overall', 'unknown') if isinstance(r, dict) else 'unknown'
            lines.append(f"  • Regime: {str(overall).upper()}")
    except Exception as e:
        log.warning(f"regime context: {e}")
    try:
        with db() as cx:
            r = cx.execute(
                "SELECT date FROM events WHERE event_type='earnings' "
                "AND ticker=? AND date >= date('now') ORDER BY date LIMIT 1",
                (ticker,)
            ).fetchone()
            if r:
                d = datetime.strptime(r['date'], '%Y-%m-%d').date()
                days_out = (d - date.today()).days
                lines.append(f"  • Earnings in {days_out}d ({r['date']})")
    except Exception:
        pass
    return lines


def _format_alert(ticker: str, level: str, thesis, current_price: float) -> str:
    entry = thesis['entry_price'] or 0
    gain_pct = ((current_price - entry) / entry * 100) if entry else 0

    if level == 'partial':
        target = thesis['target_partial']
        emoji, label = "🎯", "TARGET PARTIAL HIT"
    elif level == 'full':
        target = thesis['target_full']
        emoji, label = "🎯🎯", "TARGET FULL HIT"
    elif level == 'stop':
        target = thesis['stop_price']
        emoji, label = "🛑", "STOP HIT"
    else:
        target, emoji, label = None, "⚠", level.upper()

    target_str = f" (target was ${target})" if target else ""
    lines = [
        f"{emoji} {label} — {ticker}",
        "",
        f"  Price: ${current_price:.2f}{target_str}",
        f"  Thesis entry: ${entry:.2f} → {gain_pct:+.1f}% from baseline",
        "",
    ]

    # Position-specific recommendation
    try:
        from shared import positions as pos_mod
        pos = pos_mod.get_position(ticker)
        if pos and pos['qty'] > 0:
            qty, avg = pos['qty'], pos['avg_cost']
            mv = qty * current_price
            upl = (current_price - avg) * qty
            upct = ((current_price - avg) / avg) if avg else 0
            lines.append(f"  Your position: {qty:.3f} @ avg ${avg:.2f}")
            lines.append(f"  Market value: ${mv:,.0f} | Unreal. PnL ${upl:+,.0f} ({upct:+.1%})")
            lines.append("")
            if level == 'partial':
                lines.append(f"  → Recommended: sell {qty/3:.2f} shares (1/3 of position)")
                lines.append(f"     /position_sell {ticker} {qty/3:.2f} {current_price:.2f}")
            elif level == 'full':
                lines.append(f"  → Recommended: sell remaining {qty:.3f} shares (full exit)")
                lines.append(f"     /position_sell {ticker} {qty:.3f} {current_price:.2f}")
            elif level == 'stop':
                lines.append(f"  → Recommended: EXIT all {qty:.3f} shares — invalidation breached")
                lines.append(f"     /position_sell {ticker} {qty:.3f} {current_price:.2f}")
        else:
            generic = {'partial': 'sell 1/3 of position',
                       'full': 'sell remaining position',
                       'stop': 'EXIT — invalidation breached'}.get(level, 'review')
            lines.append(f"  → Recommended: {generic}")
            lines.append(f"     (no position registered — /position_set {ticker} <qty> <avg_cost>)")
    except Exception as e:
        log.warning(f"position lookup for alert {ticker}: {e}")
        lines.append(f"  → Recommended: {level}")

    ctx = _build_context(ticker)
    if ctx:
        lines.append("")
        lines.append("  Context:")
        lines.extend(ctx)
    lines.append("")
    lines.append(f"  Override: /override {ticker} {level} <reason>")
    return "\n".join(lines)


def _maybe_update_clv(cx, thesis, current_price: float) -> None:
    if not thesis['opened_at'] or not thesis['entry_price']:
        return
    try:
        opened_date = datetime.fromisoformat(thesis['opened_at'][:10])
    except (ValueError, TypeError):
        return
    days_since = (datetime.now() - opened_date).days
    entry = thesis['entry_price']
    keys = thesis.keys()
    for d, col_p, col_c in [(7, 'price_7d', 'clv_7d'),
                             (30, 'price_30d', 'clv_30d'),
                             (90, 'price_90d', 'clv_90d')]:
        if d <= days_since and col_c in keys and thesis[col_c] is None:
            clv = (current_price - entry) / entry
            cx.execute(
                f"UPDATE theses SET {col_p} = ?, {col_c} = ? WHERE id = ?",
                (current_price, clv, thesis['id'])
            )
            log.info(f"CLV milestone {col_c} for thesis {thesis['id']}: {clv:+.2%}")


def check_thesis_triggers() -> dict:
    """Main entry — called by cron + manual /price_check."""
    alerts_sent, fails = [], []
    with db() as cx:
        _ensure_columns(cx)
        _ensure_overrides_table(cx)
        cx.commit()
        active = cx.execute("SELECT * FROM theses WHERE status='active'").fetchall()
        if not active:
            return {'alerts': [], 'fails': [], 'theses_checked': 0}

        for t in active:
            ticker = t['ticker']
            try:
                p = prices.get_current_price(ticker)
                if not p or p <= 0:
                    fails.append(ticker)
                    continue

                direction = (t['direction'] or 'long').lower()
                crossings = []
                if direction == 'long':
                    if t['target_partial'] and p >= t['target_partial'] and not t['triggered_partial_at']:
                        crossings.append('partial')
                    if t['target_full'] and p >= t['target_full'] and not t['triggered_full_at']:
                        crossings.append('full')
                    if t['stop_price'] and p <= t['stop_price'] and not t['triggered_stop_at']:
                        crossings.append('stop')
                else:  # short
                    if t['target_partial'] and p <= t['target_partial'] and not t['triggered_partial_at']:
                        crossings.append('partial')
                    if t['target_full'] and p <= t['target_full'] and not t['triggered_full_at']:
                        crossings.append('full')
                    if t['stop_price'] and p >= t['stop_price'] and not t['triggered_stop_at']:
                        crossings.append('stop')

                now_iso = datetime.now().isoformat(timespec='seconds')
                for level in crossings:
                    msg = _format_alert(ticker, level, t, p)
                    try:
                        notify.send_text(msg)
                        cx.execute(
                            f"UPDATE theses SET triggered_{level}_at = ? WHERE id = ?",
                            (now_iso, t['id'])
                        )
                        alerts_sent.append({'ticker': ticker, 'level': level, 'price': p})
                        log.info(f"FIRED {level} alert for {ticker} @ ${p:.2f}")
                    except Exception as e:
                        log.error(f"send alert {ticker}/{level}: {e}")

                cx.execute(
                    "UPDATE theses SET last_price=?, last_price_at=? WHERE id=?",
                    (p, now_iso, t['id'])
                )
                _maybe_update_clv(cx, t, p)
            except Exception as e:
                log.error(f"price_monitor {ticker}: {e}")
                fails.append(ticker)
        cx.commit()
    return {'alerts': alerts_sent, 'fails': fails, 'theses_checked': len(active)}


def record_override(ticker: str, level: str, reason: str) -> int:
    with db() as cx:
        _ensure_overrides_table(cx)
        r = cx.execute(
            "SELECT id FROM theses WHERE ticker=? AND status='active' "
            "ORDER BY id DESC LIMIT 1", (ticker.upper(),)
        ).fetchone()
        thesis_id = r['id'] if r else None
        cur = cx.execute(
            "INSERT INTO overrides (ticker, thesis_id, level, reason) VALUES (?, ?, ?, ?)",
            (ticker.upper(), thesis_id, level, reason)
        )
        cx.commit()
        return cur.lastrowid


def list_overrides(limit: int = 20) -> list:
    with db() as cx:
        _ensure_overrides_table(cx)
        rows = cx.execute(
            "SELECT id, ticker, thesis_id, level, reason, created_at "
            "FROM overrides ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
