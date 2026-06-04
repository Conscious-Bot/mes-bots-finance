"""Mode vacances : brief raw HONNETE quand LLM down (04/06/2026).

Principe (user 04/06) : "le bot arrete de pretendre juger et ne livre que le
vrai-sans-jugement". Pas de fake-scorer qui contamine le Brier ledger. Pas de
synthese fabriquee. Juste :
  1. filings bruts (SEC objectif, deja structure)
  2. signaux raw matchant les tickers du book (regex, pas LLM)
  3. autres signaux 24h (flux brut)

Tout est tag "non score" et "synthese en pause" pour honnetete. La resolution
des predictions reste autonome (track record continue a $0, Path 5/6 asset).

Source unique partagee :
  - bot.handlers.digest.cmd_digest (Telegram /digest)
  - dashboard.chat.answer        (chat copilot fallback)

Heuristiques de MATCHING (pas de scoring) :
  - Ticker symbol = case-SENSITIVE (evite "mp"->MP sur "mortgage")
  - Alias name = case-insensitive (Alphabet/google variants)
  - Filings = source EDGAR/SEC ou signal_type 8K / insider_cluster

Le tri est par recence, pas par jugement-qualite. materiality_boost reste
dans la query mais SECONDAIRE a timestamp DESC.

Cf [[design-mode-vacances]] pour la doctrine. Anti-RuleScorer #94 wired prod.
"""

from __future__ import annotations

import re
import sqlite3

# Alias map ticker -> noms communs apparaissant dans titres/contenus.
# Etendre quand on ajoute des positions au book. Source de verite unique.
TICKER_ALIASES: dict[str, list[str]] = {
    "GOOGL": ["Alphabet", "Google"],
    "GOOG": ["Alphabet", "Google"],
    "AMZN": ["Amazon"],
    "AAPL": ["Apple"],
    "MSFT": ["Microsoft"],
    "META": ["Meta", "Facebook"],
    "NVDA": ["Nvidia", "NVIDIA"],
    "AMD": ["AMD"],
    "TSLA": ["Tesla"],
    "MU": ["Micron"],
    "AVGO": ["Broadcom"],
    "TSM": ["TSMC", "Taiwan Semi"],
    "ASML": ["ASML"],
    "ARM": ["Arm Holdings"],
    "6857.T": ["Advantest"],
    "8035.T": ["Tokyo Electron"],
    "000660.KS": ["SK Hynix", "Hynix"],
    "005930.KS": ["Samsung"],
    "COIN": ["Coinbase"],
    "MSTR": ["MicroStrategy", "Strategy"],
    "PLTR": ["Palantir"],
    "SNOW": ["Snowflake"],
    "STMPA.PA": ["STMicro", "STMicroelectronics"],
    "CCJ": ["Cameco"],
    "MP": ["MP Materials"],
}


def _clean_src(s: str | None) -> str:
    if not s:
        return "(unknown)"
    i = s.find(" <")
    return (s[:i] if i > 0 else s).strip().strip('"')


def _fmt_ts(t: str | None) -> str:
    return (t or "")[5:16].replace("T", " ")


def _truncate(s: str | None, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n - 3] + "..."


def _ticker_core(tk: str) -> str:
    """Symbole nu sans suffixe d'exchange : '6857.T' -> '6857', 'STMPA.PA' -> 'STMPA'."""
    return tk.split(".")[0]


def _compile_patterns(tickers: list[str]) -> dict[str, re.Pattern]:
    """Pattern per ticker : OR de tous les mecanismes de match acceptables.

    Strategie pour eviter "MP" matchant "mortgage", "AT" matchant "at home" :
      - Cashtag `$<SYM>` : haute confiance (financier specific). Tous tickers.
      - Exchange tag `(NYSE: SYM)`, `(NASDAQ: SYM)`, `NYSE:SYM` : haute confiance.
      - Symbole nu :
          * >=4 chars : case-SENSITIVE word-boundary (GOOGL, AMZN faux pos rare)
          * <=3 chars : INTERDIT seul (trop ambigu). Cashtag ou exchange tag requis.
      - Alias (noms societe) : case-insensitive word-boundary. Tous tickers.

    Pas de LLM, pas de fenetre contextuelle (gardable simple). Si insuffisant
    en pratique, on peut ajouter dictionnaire 'noisy_neighbors' par ticker.
    """
    pats: dict[str, re.Pattern] = {}
    for tk in tickers:
        core = _ticker_core(tk)
        alternatives: list[str] = []
        # Cashtag (toujours, haute confiance)
        alternatives.append(r"\$" + re.escape(core))
        # Exchange-tagged forms
        alternatives.append(
            r"(?:NYSE|NASDAQ|TYO|HKEX|EPA|LSE|XETRA|KRX|TSE)[ ]?:[ ]?" + re.escape(core)
        )
        # Symbole nu : autorise SEULEMENT >= 4 chars (case-sensitive)
        if len(core) >= 4:
            alternatives.append(r"(?:^|[^A-Z0-9$:])" + re.escape(core) + r"(?:$|[^A-Z0-9])")
        # Alias noms societe (case-insensitive applique au pattern global ci-dessous)
        for alias in TICKER_ALIASES.get(tk, []):
            alternatives.append(r"(?:^|\W)" + re.escape(alias) + r"(?:$|\W)")
        # Compile : on a un mix case-sensitive (cashtag, symbole) et case-insensitive
        # (aliases). Solution : on compile case-sensitive par defaut, on rajoute les
        # aliases en versions multi-case via (?i:...) inline flag (Python 3.6+).
        # Mais pour simplicite et clarte : on compile case-sensitive, on uppercase
        # aliases dans le pattern + on cherche case-insensitive sur les aliases en
        # post-process. Plus simple : 2 patterns.
        pats[tk] = re.compile("|".join(alternatives))
    return pats


def _compile_alias_patterns(tickers: list[str]) -> dict[str, re.Pattern]:
    """Alias-only patterns, case-insensitive. Separe pour gerer la casse propre."""
    pats: dict[str, re.Pattern] = {}
    for tk in tickers:
        aliases = TICKER_ALIASES.get(tk, [])
        if aliases:
            pats[tk] = re.compile(
                r"(?:^|\W)(" + "|".join(re.escape(a) for a in aliases) + r")(?:$|\W)",
                re.IGNORECASE,
            )
    return pats


def _match_book(
    title: str | None,
    content: str | None,
    held: list[str],
    sym_pats: dict[str, re.Pattern],
    alias_pats: dict[str, re.Pattern],
) -> list[str]:
    text = (title or "") + " " + (content or "")[:800]
    hits = []
    for tk in held:
        if sym_pats[tk].search(text) or (
            tk in alias_pats and alias_pats[tk].search(text)
        ):
            hits.append(tk)
    return hits


def build_degraded_brief(
    db_path: str,
    hours: int = 24,
    focus_tickers: list[str] | None = None,
) -> str:
    """Build a structured raw brief depuis signals table sur la fenetre 24h.

    Args:
        db_path : chemin DB SQLite.
        hours : fenetre temporelle en heures (default 24).
        focus_tickers : si fourni, filtre les sections book/other a ces tickers
                        seulement. None = tous les tickers du book.

    Returns:
        str formate avec sections === FILINGS / BOOK TOUCHES / AUTRES ===.
        Vide ("") si aucun signal ingere sur la fenetre.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Held tickers (book)
        try:
            held_rows = conn.execute(
                "SELECT ticker FROM positions WHERE status='open' AND qty > 0"
            ).fetchall()
            held = [r["ticker"] for r in held_rows]
        except Exception:
            held = []
        if focus_tickers:
            held = [t for t in held if t in focus_tickers] or list(focus_tickers)

        sym_pats = _compile_patterns(held)
        alias_pats = _compile_alias_patterns(held)

        # Filings & insider (source EDGAR/SEC ou signal_type)
        filings = conn.execute(
            "SELECT s.timestamp, s.title, src.name AS source "
            "FROM signals s LEFT JOIN sources src ON s.source_id=src.id "
            "WHERE s.timestamp >= datetime('now', ?) "
            "  AND (src.name LIKE '%EDGAR%' OR src.name LIKE '%SEC%' "
            "       OR s.signal_type LIKE '%8K%' OR s.signal_type='insider_cluster') "
            "ORDER BY s.timestamp DESC LIMIT 8",
            (f"-{hours} hours",),
        ).fetchall()

        # Raw signals
        raw = conn.execute(
            "SELECT s.timestamp, s.title, s.content, src.name AS source, "
            "  COALESCE(s.materiality_boost, 1.0) AS mb "
            "FROM signals s LEFT JOIN sources src ON s.source_id=src.id "
            "WHERE s.timestamp >= datetime('now', ?) "
            "ORDER BY mb DESC, s.timestamp DESC LIMIT 18",
            (f"-{hours} hours",),
        ).fetchall()
    finally:
        conn.close()

    if not raw and not filings:
        return ""

    # Split book-touching vs other
    book_rows, other_rows = [], []
    for r in raw:
        hits = _match_book(r["title"], r["content"], held, sym_pats, alias_pats)
        if hits:
            book_rows.append((r, hits))
        else:
            other_rows.append(r)

    # Si focus_tickers, on cache les "autres" (focus = juste le ticker demande)
    if focus_tickers:
        other_rows = []

    lines: list[str] = []

    if filings:
        lines.append(f"=== FILINGS SEC ({hours}h, {len(filings)}) -- objectif, non interprete ===")
        for f in filings:
            lines.append(f"  [{_fmt_ts(f['timestamp'])}] {_clean_src(f['source'])}")
            lines.append(f"    {_truncate(f['title'], 100)}")
        lines.append("")

    if book_rows:
        lines.append(f"=== TOUCHES BOOK ({len(book_rows)}) -- non score, synthese en pause ===")
        for r, hits in book_rows:
            tags = " ".join(f"[{t}]" for t in hits[:3])
            lines.append(f"  [{_fmt_ts(r['timestamp'])}] {_clean_src(r['source'])} {tags}")
            lines.append(f"    {_truncate(r['title'], 100)}")
        lines.append("")
    elif not filings and not focus_tickers:
        lines.append("(aucun signal touchant le book sur la fenetre)")
        lines.append("")

    if other_rows:
        lines.append(f"=== FLUX BRUT ({len(other_rows)}) -- non score, synthese en pause ===")
        for r in other_rows[:8]:
            lines.append(
                f"  [{_fmt_ts(r['timestamp'])}] {_clean_src(r['source'])} : "
                f"{_truncate(r['title'], 80)}"
            )

    return "\n".join(lines).rstrip()
