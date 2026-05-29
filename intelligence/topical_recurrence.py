"""Sprint 22 — Topical recurrence : tracker des obsessions de l'user.

Aggrege les chat_extracted_signals + chat_messages pour identifier :
  - Quels tickers reviennent le plus dans les conversations
  - Quels themes/secteurs sont mentionnes recurrement
  - Frequence (quotidien/hebdo/sporadique)
  - Evolution dans le temps (croissant/decroissant)

Ces patterns deviennent une section dediee dans le user_profile et
nourrissent le chat context : 'Tu as mentionne X 7 fois en 2 semaines,
c'est ton sujet recurrent du moment.'
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta

from shared import storage

log = logging.getLogger(__name__)


def compute_topical_recurrence(window_days: int = 60) -> dict:
    """Aggregate chat_extracted_signals + chat_messages over window."""
    cutoff = (datetime.now(UTC) - timedelta(days=window_days)).isoformat()
    out: dict = {
        "tickers_recurrence": [],
        "themes_recurrence": [],
        "sectors_recurrence": [],
        "kinds_recurrence": [],
        "window_days": window_days,
    }

    try:
        with storage.db() as cx:
            # Chat signals grouped
            rows = cx.execute(
                "SELECT ticker, theme, sector, kind, created_at FROM chat_extracted_signals "
                "WHERE created_at >= ?",
                (cutoff,),
            ).fetchall()
    except Exception as e:
        log.warning(f"topical_recurrence query failed: {e}")
        return out

    ticker_counter: Counter = Counter()
    theme_counter: Counter = Counter()
    sector_counter: Counter = Counter()
    kind_counter: Counter = Counter()
    ticker_dates: dict = {}
    theme_dates: dict = {}

    for r in rows:
        tk, theme, sec, kind, created = r
        if tk:
            ticker_counter[tk] += 1
            ticker_dates.setdefault(tk, []).append(created)
        if theme:
            theme_counter[theme] += 1
            theme_dates.setdefault(theme, []).append(created)
        if sec:
            sector_counter[sec] += 1
        kind_counter[kind or "?"] += 1

    def _frequency(n: int, w: int) -> str:
        per_week = n / (w / 7)
        if per_week >= 5:
            return "quotidien"
        if per_week >= 1:
            return "hebdo"
        if per_week >= 0.25:
            return "mensuel"
        return "sporadique"

    for tk, n in ticker_counter.most_common(10):
        dates = sorted(ticker_dates.get(tk, []))
        out["tickers_recurrence"].append({
            "ticker": tk,
            "n_mentions": n,
            "frequency": _frequency(n, window_days),
            "first_seen": (dates[0] or "")[:10] if dates else "",
            "last_seen": (dates[-1] or "")[:10] if dates else "",
        })

    for theme, n in theme_counter.most_common(8):
        dates = sorted(theme_dates.get(theme, []))
        out["themes_recurrence"].append({
            "theme": theme,
            "n_mentions": n,
            "frequency": _frequency(n, window_days),
            "first_seen": (dates[0] or "")[:10] if dates else "",
            "last_seen": (dates[-1] or "")[:10] if dates else "",
        })

    for sec, n in sector_counter.most_common(8):
        out["sectors_recurrence"].append({
            "sector": sec,
            "n_mentions": n,
            "frequency": _frequency(n, window_days),
        })

    out["kinds_recurrence"] = [
        {"kind": k, "n": n} for k, n in kind_counter.most_common(10)
    ]

    return out


def format_for_chat_context() -> str:
    """Returns a text block ready to inject in chat assemble_context."""
    r = compute_topical_recurrence(window_days=60)
    if not r["tickers_recurrence"] and not r["themes_recurrence"]:
        return "  (pas encore assez de donnees chat pour identifier des recurrences)"
    lines = [f"  Fenetre : {r['window_days']} derniers jours"]
    if r["tickers_recurrence"]:
        lines.append("  Tickers obsessionnels (mentions chat) :")
        for t in r["tickers_recurrence"][:5]:
            lines.append(
                f"    - {t['ticker']:10s} n={t['n_mentions']} freq={t['frequency']} "
                f"vu de {t['first_seen']} a {t['last_seen']}"
            )
    if r["themes_recurrence"]:
        lines.append("  Themes recurrents :")
        for t in r["themes_recurrence"][:5]:
            lines.append(
                f"    - {(t['theme'] or '?')[:35]:35s} n={t['n_mentions']} freq={t['frequency']}"
            )
    return "\n".join(lines)
