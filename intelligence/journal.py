"""Phase 18 — Decision Journal + Error Analysis.

Auto-classify mistake tag at resolution time (J+30 or J+90).
Rules are conservative — they flag CLEAR patterns, not nuance.
Manual override (via /journal_clear or override_mistake_tag) is the escape valve.
"""
import logging
log = logging.getLogger("intelligence.journal")


SIGNIFICANT_MOVE_PCT = 0.05
LARGE_MISS_PCT = 0.10


def auto_classify_mistake(decision, price_at_horizon, horizon_days):
    """Return mistake tag string based on decision + outcome.
    Args:
        decision: dict (row from decisions table)
        price_at_horizon: float, price at J+horizon_days
        horizon_days: 30 or 90
    """
    p0 = decision.get('price_at_decision')
    if not p0 or not price_at_horizon:
        return 'unresolvable_no_price'

    ret = (price_at_horizon / p0) - 1.0
    dtype = decision.get('decision_type')
    direction = (decision.get('direction') or '').lower()

    if dtype in ('entry', 'scale_in'):
        if direction == 'short':
            if ret < -SIGNIFICANT_MOVE_PCT:
                return 'entry_correct'
            elif ret > LARGE_MISS_PCT:
                return 'entry_premature'
            return 'entry_flat'
        else:
            if ret > SIGNIFICANT_MOVE_PCT:
                return 'entry_correct'
            elif ret < -LARGE_MISS_PCT:
                return 'entry_premature'
            return 'entry_flat'

    if dtype in ('partial_exit', 'full_exit'):
        if ret > LARGE_MISS_PCT:
            return 'sold_too_early'
        elif ret < -SIGNIFICANT_MOVE_PCT:
            return 'correct_exit'
        return 'flat_exit'

    if dtype == 'override':
        if direction == 'sell':
            if ret > LARGE_MISS_PCT:
                return 'override_wrong'
            elif ret < -SIGNIFICANT_MOVE_PCT:
                return 'override_right'
            return 'override_flat'
        elif direction == 'buy':
            if ret > LARGE_MISS_PCT:
                return 'override_right'
            elif ret < -LARGE_MISS_PCT:
                return 'override_wrong'
            return 'override_flat'
        return 'override_ambiguous'

    if dtype == 'no_action_flag':
        if ret > LARGE_MISS_PCT:
            return 'missed_opportunity'
        elif ret < -LARGE_MISS_PCT:
            return 'correct_caution'
        return 'flat_no_action'

    return None


def thesis_relative_position(price, thesis_dict):
    """Where is price relative to thesis target levels?
    Priority: full -> partial -> below_entry (dominant) -> at_or_below_stop -> between_entry_and_partial.
    Handles both normal (stop < entry) and invalidation-stop (stop > entry) thesis structures.
    """
    if not thesis_dict or not price:
        return None
    entry = thesis_dict.get('entry_price')
    partial = thesis_dict.get('target_partial')
    full = thesis_dict.get('target_full')
    stop = thesis_dict.get('stop_price')

    if full and price >= full:
        return 'at_or_above_full_target'
    if partial and price >= partial:
        return 'between_partial_and_full' if full else 'at_or_above_partial'
    if entry and price < entry:
        return 'below_entry'
    if stop and price <= stop:
        return 'at_or_below_stop'
    if entry:
        return 'between_entry_and_partial'
    return 'unclassified'


def format_decision_summary(d):
    """Format a decision row as a 3-line Telegram block."""
    lines = []
    tag = d.get('mistake_tag_manual') or d.get('mistake_tag_auto') or 'pending'
    lines.append(f"#{d['id']} {d['ticker']} [{d['decision_type']}] conf={d.get('confidence_pre','?')} -> {tag}")

    p0 = d.get('price_at_decision')
    p30 = d.get('price_30d')
    r30 = d.get('return_30d_pct')
    p90 = d.get('price_90d')
    r90 = d.get('return_90d_pct')

    parts = [f"entry ${p0:.2f}" if p0 else "entry ?"]
    if r30 is not None:
        parts.append(f"30d ${p30:.2f} ({r30*100:+.1f}%)")
    elif d.get('created_at'):
        parts.append("30d pending")
    if r90 is not None:
        parts.append(f"90d ${p90:.2f} ({r90*100:+.1f}%)")
    lines.append("  " + " | ".join(parts))

    reasoning = (d.get('reasoning') or '')[:80]
    lines.append(f"  \"{reasoning}\"")
    return "\n".join(lines)
