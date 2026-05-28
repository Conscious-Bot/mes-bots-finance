"""Portfolio enrichment handlers — sectors, narratives, drift.

Read-only handlers added in Sprint 1.1 chunk Day 5 Ship B (2026-05-16).
Zero touch to measurement pipeline. Pure SQL + config.yaml read.

Three handlers:
- /portfolio_sectors    : breakdown by sector (config.yaml taxonomy)
- /portfolio_narratives : breakdown by sector_thesis_id from theses.notes
- /portfolio_drift      : positions vs portfolio_targets, over/underweight
"""

from __future__ import annotations

import logging
import re
import sqlite3

import yaml

from bot.handlers._common import config_path, db_path, telegram_safe
from shared.display import Currency, format_finance, format_pct

__all__ = [
    "cmd_portfolio_drift",
    "cmd_portfolio_narratives",
    "cmd_portfolio_sectors",
]

log = logging.getLogger("bot")


def _build_ticker_to_gics_sector() -> dict[str, str]:
    """Map every ticker in config.yaml sectors_taxonomy to its GICS sector label.

    Reads nested structure: sector -> industry -> tickers.
    Returns dict ticker -> sector_name.
    Unknown tickers default to 'unknown' via .get() fallback in callers.
    """
    cfg = yaml.safe_load(config_path().read_text())
    taxonomy = cfg.get("sectors_taxonomy", {})
    mapping: dict[str, str] = {}
    for sector, industries in taxonomy.items():
        if not isinstance(industries, dict):
            continue
        for _industry, tickers in industries.items():
            if not isinstance(tickers, list):
                continue
            for ticker in tickers:
                mapping[ticker] = sector
    return mapping


def _build_ticker_to_gics_industry() -> dict[str, str]:
    """Map every ticker in config.yaml sectors_taxonomy to its GICS industry label.

    Reads nested structure: sector -> industry -> tickers.
    Returns dict ticker -> industry_name (e.g. 'Semiconductors', 'Aerospace & Defense').
    Unknown tickers default to 'unknown' via .get() fallback in callers.
    """
    cfg = yaml.safe_load(config_path().read_text())
    taxonomy = cfg.get("sectors_taxonomy", {})
    mapping: dict[str, str] = {}
    for _sector, industries in taxonomy.items():
        if not isinstance(industries, dict):
            continue
        for industry, tickers in industries.items():
            if not isinstance(tickers, list):
                continue
            for ticker in tickers:
                mapping[ticker] = industry
    return mapping


def _build_ticker_to_sector() -> dict[str, str]:
    """Map every ticker in config.yaml universe to its sector label.

    Returns dict ticker -> sector_label (e.g. "core/semis_core", "watch", "ext/european_pea").
    Unknown tickers default to "unknown" via .get() fallback in callers.
    """
    cfg = yaml.safe_load(config_path().read_text())
    universe = cfg.get("universe", {})
    mapping: dict[str, str] = {}

    # Core has sub-categories
    for sub_cat, tickers in universe.get("core", {}).items():
        if isinstance(tickers, list):
            for t in tickers:
                mapping[t] = f"core/{sub_cat}"

    # Watch is flat list
    for t in universe.get("watch", []):
        if t not in mapping:
            mapping[t] = "watch"

    # Extended has sub-categories
    for sub_cat, tickers in universe.get("extended", {}).items():
        if isinstance(tickers, list):
            for t in tickers:
                if t not in mapping:
                    mapping[t] = f"ext/{sub_cat}"

    return mapping


_SECTOR_THESIS_RE = re.compile(r"sector_thesis_id:\s*([A-Z0-9_]+)")


def _get_caps_from_config() -> tuple[float, float]:
    """Read (narrative_max_pct, sector_max_pct) from config.yaml style section.

    Pure advisory caps surfaced in /portfolio_narratives + /portfolio_sectors as
    OVERWEIGHT markers. NOT enforcement gates. PHILOSOPHY: bot informs, Olivier acts.
    Defaults to 0.30 / 0.20 if missing.
    """
    cfg = yaml.safe_load(config_path().read_text())
    style = cfg.get("style", {})
    return (
        float(style.get("narrative_max_pct", 0.30)),
        float(style.get("sector_max_pct", 0.20)),
    )


def _extract_narrative(notes: str | None) -> str | None:
    """Extract sector_thesis_id from theses.notes multi-line string. Returns None if absent."""
    if not notes:
        return None
    m = _SECTOR_THESIS_RE.search(notes)
    return m.group(1) if m else None


def _compute_book_market_value(conn: sqlite3.Connection) -> tuple[float, list[dict]]:
    """Fetch open positions + compute market value, USD-canonical.

    Day 11 ADR 004 Batch 4B: USD canonical + FM-10 fix. Per-position native
    currency conversion to USD via current fx, applied to BOTH cost_basis
    and market_value for currency-coherent aggregation in downstream views
    (cmd_portfolio_sectors, cmd_portfolio_narratives).

    Returns (total_market_value_usd, list_of_position_dicts) with USD-denominated
    cost_basis + market_value. Falls back to cost_basis if live price unavailable.
    """
    from shared.positions import cost_in
    from shared.prices import get_current_price_in_usd

    rows = conn.execute("SELECT ticker, qty, avg_cost, account FROM positions WHERE status='open'").fetchall()

    positions = []
    total_mv = 0.0
    for ticker, qty, avg_cost, account in rows:
        # Day 13 ADR 005: avg_cost EUR canonical via cost_in helper.
        avg_cost_usd = cost_in(avg_cost, "USD") or 0.0
        try:
            cur_price = get_current_price_in_usd(ticker)
        except Exception:
            cur_price = None
        cost_basis = qty * avg_cost_usd
        mv = (cur_price * qty) if cur_price else cost_basis
        positions.append(
            {
                "ticker": ticker,
                "qty": qty,
                "avg_cost": avg_cost_usd,
                "account": account,
                "cost_basis": cost_basis,
                "market_value": mv,
                "has_live_price": cur_price is not None,
            }
        )
        total_mv += mv

    return total_mv, positions


async def cmd_portfolio_sectors(update, ctx):  # noqa: ARG001
    """Show portfolio breakdown by GICS sector + industry hierarchy.

    Uses config.yaml sectors_taxonomy (manual classification: sector -> industry -> tickers).
    Sector-level advisory cap from style.sector_max_pct (default 20%).
    Hierarchical monospace display: sector header + industry sub-breakdown + tickers.
    Usage: /portfolio_sectors
    """
    try:
        ticker_to_sector = _build_ticker_to_gics_sector()
        ticker_to_industry = _build_ticker_to_gics_industry()
    except Exception as e:
        log.error(f"cmd_portfolio_sectors config load error: {e}")
        await update.message.reply_text(f"Config load error: {e}")
        return

    conn = sqlite3.connect(str(db_path()))
    try:
        total_mv, positions = _compute_book_market_value(conn)
    finally:
        conn.close()

    if not positions:
        await update.message.reply_text("No active positions.")
        return

    _, sector_cap_pct_frac = _get_caps_from_config()
    sector_cap_pct = sector_cap_pct_frac * 100

    by_si: dict[tuple[str, str], dict] = {}
    for p in positions:
        s = ticker_to_sector.get(p["ticker"], "unknown")
        i = ticker_to_industry.get(p["ticker"], "unknown")
        key = (s, i)
        if key not in by_si:
            by_si[key] = {"tickers": [], "mv": 0.0, "cost_basis": 0.0}
        by_si[key]["tickers"].append(p["ticker"])
        by_si[key]["mv"] += p["market_value"]
        by_si[key]["cost_basis"] += p["cost_basis"]

    sectors: dict[str, dict] = {}
    for (s, i), data in by_si.items():
        if s not in sectors:
            sectors[s] = {"mv": 0.0, "cost_basis": 0.0, "industries": {}}
        sectors[s]["mv"] += data["mv"]
        sectors[s]["cost_basis"] += data["cost_basis"]
        sectors[s]["industries"][i] = data

    sorted_sectors = sorted(sectors.items(), key=lambda x: x[1]["mv"], reverse=True)

    # Header
    header = f"PORTFOLIO BY SECTOR / INDUSTRY — ${total_mv:,.0f} total"
    lines = [header, ""]

    LABEL_W = 34  # sector label width (industry uses literal 32 for $ col alignment)

    def truncate(s: str, w: int) -> str:
        return s if len(s) <= w else s[: w - 1] + "…"

    for sector, data in sorted_sectors:
        pct = (data["mv"] / total_mv * 100) if total_mv else 0
        n_total = sum(len(ind["tickers"]) for ind in data["industries"].values())
        pnl_pct = ((data["mv"] / data["cost_basis"] - 1) * 100) if data["cost_basis"] else 0

        breach_suffix = ""
        if pct > sector_cap_pct and sector != "unknown":
            overweight_pp = pct - sector_cap_pct
            breach_suffix = f"  ⚠ +{overweight_pp:.1f}pp"

        label_pad = truncate(sector, LABEL_W).ljust(LABEL_W)
        sector_line = (
            f"▼ {label_pad}  ${data['mv']:>8,.0f}  {pct:5.1f}%  {n_total:>2} pos  {pnl_pct:+5.1f}%{breach_suffix}"
        )
        lines.append(sector_line)

        sorted_industries = sorted(
            data["industries"].items(),
            key=lambda x: x[1]["mv"],
            reverse=True,
        )
        for industry, ind_data in sorted_industries:
            ind_pct = (ind_data["mv"] / total_mv * 100) if total_mv else 0
            n_ind = len(ind_data["tickers"])
            ind_label_pad = truncate(industry, 32).ljust(32)
            ind_line = f"    {ind_label_pad}  ${ind_data['mv']:>8,.0f}  {ind_pct:5.1f}%  {n_ind:>2} pos"
            lines.append(ind_line)
            tickers_str = ", ".join(sorted(ind_data["tickers"]))
            lines.append(f"        {tickers_str}")
        lines.append("")

    # Summary
    breach_count = sum(
        1
        for sector, data in sorted_sectors
        if sector != "unknown" and (data["mv"] / total_mv * 100 if total_mv else 0) > sector_cap_pct
    )
    if breach_count > 0:
        lines.append(f"⚠ {breach_count} sector(s) overweight vs {sector_cap_pct:.0f}% advisory cap")
    else:
        lines.append(f"✅ All sectors within {sector_cap_pct:.0f}% advisory cap")

    unknown_tickers = []
    if "unknown" in sectors:
        for _industry, ind_data in sectors["unknown"]["industries"].items():
            unknown_tickers.extend(ind_data["tickers"])
    unknown_count = len(unknown_tickers)
    if unknown_count > 0:
        lines.append("")
        lines.append(f"⚠ {unknown_count} not classified: {', '.join(unknown_tickers)}")
        lines.append("Add to sectors_taxonomy in config.yaml under their GICS sector/industry")

    msg = "\n".join(lines)
    if len(msg) > 3800:
        msg = msg[:3800] + "\n[truncated]"

    # Monospace block for column alignment
    await update.message.reply_text(f"```\n{msg}\n```", parse_mode="Markdown")


async def cmd_portfolio_narratives(update, ctx):  # noqa: ARG001
    """Show portfolio breakdown by sector_thesis_id narrative. Usage: /portfolio_narratives"""
    conn = sqlite3.connect(str(db_path()))
    try:
        total_mv, positions = _compute_book_market_value(conn)

        # Fetch theses notes for narrative extraction
        rows = conn.execute("SELECT ticker, notes FROM theses WHERE status='active'").fetchall()
        ticker_to_narrative: dict[str, str] = {}
        for ticker, notes in rows:
            narrative = _extract_narrative(notes)
            if narrative:
                ticker_to_narrative[ticker] = narrative
    finally:
        conn.close()

    if not positions:
        await update.message.reply_text("No active positions.")
        return

    # Group by narrative (fallback to "untagged" if no thesis or no sector_thesis_id)
    narratives: dict[str, dict] = {}
    for p in positions:
        narrative = ticker_to_narrative.get(p["ticker"], "untagged")
        if narrative not in narratives:
            narratives[narrative] = {"tickers": [], "mv": 0.0, "cost_basis": 0.0}
        narratives[narrative]["tickers"].append(p["ticker"])
        narratives[narrative]["mv"] += p["market_value"]
        narratives[narrative]["cost_basis"] += p["cost_basis"]

    sorted_narratives = sorted(narratives.items(), key=lambda x: x[1]["mv"], reverse=True)

    narrative_cap_pct_frac, _ = _get_caps_from_config()
    narrative_cap_pct = narrative_cap_pct_frac * 100

    lines = [
        f"\U0001f3af *PORTFOLIO BY NARRATIVE* — {format_finance(total_mv, decimals=0, currency=Currency.USD)} total\n"
    ]
    for narrative, data in sorted_narratives:
        pct = (data["mv"] / total_mv * 100) if total_mv else 0
        n = len(data["tickers"])
        pnl_pct = ((data["mv"] / data["cost_basis"] - 1) * 100) if data["cost_basis"] else 0
        tickers_str = ", ".join(sorted(data["tickers"]))
        # Day 9 V H3 refactor: centralized escape via _common.telegram_safe
        narrative_display = telegram_safe(narrative)
        breach_suffix = ""
        if pct > narrative_cap_pct and narrative != "untagged":
            overweight_pp = pct - narrative_cap_pct
            breach_suffix = f"  ⚠️ OVERWEIGHT +{overweight_pp:.1f}pp (cap {narrative_cap_pct:.0f}%)"
        lines.append(
            f"  {narrative_display}  {format_finance(data['mv'], decimals=0, currency=Currency.USD)}  "
            f"[{pct:4.1f}%]  ({n} pos, PnL {format_pct(pnl_pct, decimals=1, signed=True)}){breach_suffix}"
        )
        lines.append(f"    {tickers_str}")
        lines.append("")

    breach_count = sum(
        1
        for narrative, data in sorted_narratives
        if narrative != "untagged" and (data["mv"] / total_mv * 100 if total_mv else 0) > narrative_cap_pct
    )
    if breach_count > 0:
        lines.append(f"⚠️ {breach_count} narrative(s) overweight vs {narrative_cap_pct:.0f}% advisory cap")
    else:
        lines.append(f"✅ All narratives within {narrative_cap_pct:.0f}% advisory cap")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        msg = msg[:3900] + "\n[truncated]"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_portfolio_drift(update, ctx):  # noqa: ARG001
    """Show drift between actual positions and portfolio_targets. Usage: /portfolio_drift"""
    conn = sqlite3.connect(str(db_path()))
    try:
        # Fetch all targets with their actual positions
        rows = conn.execute("""
            SELECT pt.ticker, pt.account, pt.target_eur, pt.status, pt.phase_week,
                   pt.narrative, pt.priority,
                   COALESCE(p.qty * p.avg_cost, 0) AS cost_basis_eur,
                   p.qty, p.avg_cost
            FROM portfolio_targets pt
            LEFT JOIN positions p ON pt.ticker = p.ticker AND p.status = 'open'
            ORDER BY pt.target_eur DESC
        """).fetchall()
    finally:
        conn.close()

    if not rows:
        await update.message.reply_text("No portfolio_targets configured. Use scripts/import_portfolio_targets.py.")
        return

    # Aggregate by status
    executed: list[dict] = []
    planned: list[dict] = []
    locked: list[dict] = []
    dropped: list[dict] = []

    total_target = 0.0
    total_actual = 0.0

    for ticker, account, target_eur, status, phase_week, narrative, priority, cost_basis, _qty, _avg_cost in rows:
        target_eur = float(target_eur or 0)
        cost_basis = float(cost_basis or 0)
        drift = cost_basis - target_eur
        drift_pct = (drift / target_eur * 100) if target_eur else 0
        item = {
            "ticker": ticker,
            "account": account,
            "target": target_eur,
            "actual": cost_basis,
            "drift": drift,
            "drift_pct": drift_pct,
            "status": status,
            "phase_week": phase_week,
            "narrative": narrative or "",
            "priority": priority or "",
        }
        total_target += target_eur
        total_actual += cost_basis
        if status == "executed":
            executed.append(item)
        elif status == "locked":
            locked.append(item)
        elif status == "planned":
            planned.append(item)
        elif status == "dropped":
            dropped.append(item)

    total_drift = total_actual - total_target
    pct_deployed = (total_actual / total_target * 100) if total_target else 0

    lines = ["\U0001f4c9 *PORTFOLIO DRIFT vs TARGETS*\n"]
    lines.append(f"  Total target  : {format_finance(total_target, decimals=0, width=7)}")
    lines.append(f"  Total actual  : {format_finance(total_actual, decimals=0, width=7)}")
    lines.append(f"  Deployed      : {pct_deployed:.1f}%")
    lines.append(f"  Net drift     : {format_finance(total_drift, decimals=0, signed=True)}")
    lines.append("")

    # Executed positions with drift
    if executed:
        lines.append(f"*EXECUTED* ({len(executed)})")
        for item in sorted(executed, key=lambda x: x["drift"], reverse=False)[:15]:
            sign = (
                "\U0001f534"
                if item["drift_pct"] < -10
                else ("\U0001f7e2" if abs(item["drift_pct"]) <= 10 else "\U0001f535")
            )
            lines.append(
                f"  {sign} {item['ticker']:10s} "
                f"{format_finance(item['actual'], decimals=0, width=5)}/"
                f"{format_finance(item['target'], decimals=0, width=5)}  "
                f"drift {format_finance(item['drift'], decimals=0, signed=True)} "
                f"({format_pct(item['drift_pct'], decimals=0, signed=True)})"
            )
        lines.append("")

    # Locked (PEA)
    if locked:
        lines.append(f"*LOCKED* ({len(locked)} PEA)")
        for item in locked[:10]:
            lines.append(
                f"  \U0001f512 {item['ticker']:10s} {format_finance(item['actual'], decimals=0, width=5)}/{format_finance(item['target'], decimals=0, width=5)}"
            )
        lines.append("")

    # Planned (to execute)
    if planned:
        lines.append(f"*PLANNED* ({len(planned)} pending)")
        for item in sorted(planned, key=lambda x: (x["phase_week"] or 99, -x["target"]))[:10]:
            phase_str = f"W{item['phase_week']}" if item["phase_week"] else "—"
            prio_str = f" [{item['priority']}]" if item["priority"] else ""
            lines.append(
                f"  \u23f3 {item['ticker']:10s} {format_finance(item['target'], decimals=0, width=5)}  phase {phase_str}{prio_str}"
            )
        lines.append("")

    if dropped:
        lines.append(f"_dropped: {len(dropped)} items_")

    msg = "\n".join(lines)
    if len(msg) > 3900:
        # Chunk by sections
        chunks = []
        cur = ""
        for line in msg.split("\n"):
            if len(cur) + len(line) + 1 < 3900:
                cur += "\n" + line if cur else line
            else:
                chunks.append(cur)
                cur = line
        if cur:
            chunks.append(cur)
        for c in chunks:
            await update.message.reply_text(c, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_tiers(update, ctx):  # noqa: ARG001
    """Conviction sizing tiers : cap soft par conviction + cible conviction-normalisee.
    Source unique = config.concentration.line_cap_by_conviction (ADR 009). Price-free."""
    from shared import config as _cfg_mod, storage as _storage

    caps = _cfg_mod.load().get("concentration", {}).get("line_cap_by_conviction", {})
    if not caps:
        await update.message.reply_text("config.concentration.line_cap_by_conviction absente.")
        return

    held = {p["ticker"] for p in _storage.get_open_positions()}
    convs = []
    for t in _storage.active_theses():
        if t.get("ticker") not in held:
            continue
        try:
            c = int(t.get("conviction") or 0)
        except TypeError, ValueError:
            continue
        if c in caps:
            convs.append(c)

    n_held = len(convs)
    if n_held == 0:
        await update.message.reply_text("Aucune ligne tenue avec these active + conviction. Rien a tierer.")
        return

    sumcaps = sum(caps[c] for c in convs) or 1.0
    rows = ["tier  cap    lns  cib/ln  cib/t"]
    for tier in (5, 4, 3, 2, 1):
        cap = caps.get(tier)
        if cap is None:
            continue
        n_t = sum(1 for c in convs if c == tier)
        per_line = cap / sumcaps * 100
        rows.append(f"c{tier}   {cap * 100:4.1f}%  {n_t:3d}  {per_line:5.1f}%  {n_t * per_line:5.1f}%")

    n_c5 = sum(1 for c in convs if c == 5)
    c5_pct = n_c5 / n_held * 100
    infl = "warn >20%" if c5_pct > 20 else "ok"

    msg = (
        "*CONVICTION TIERS* — sizing soft (source: config, ADR 009)\n\n"
        "```\n" + "\n".join(rows) + "\n```\n"
        f"Somme cibles tier = 100% (conviction-normalise, {n_held} lignes tenues)\n"
        f"Inflation c5: {c5_pct:.0f}% des lignes (gate <=20%) {infl}\n\n"
        "_cap ligne = SOFT (alerte) ; invariant LIANT = cluster 35% (ADR 008/010)_\n"
        "_poids courant par ligne vs cap -> dashboard /portfolio_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
