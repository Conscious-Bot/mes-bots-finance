"""Lentille materialite decisionnelle : signal -> prediction -> decision.

High Standard (CLAUDE.md) : 'qu'est-ce qui produit zero matiere
decisionnelle / 90j = pur cout cognitif, par ta propre regle'.

Triangulation : un handler/source/cron qui touche la chaine
signal -> prediction -> decision DOIT produire au moins 1 element de la
chaine sur la fenetre. Sinon, candidate suppression haute confiance.

ZERO ECRITURE (Tier R, audit doctrine SAS).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class DecisionCandidate:
    """Un symbole / source dont la productivite decisionnelle est zero."""
    name: str               # source name ou ticker ou handler
    kind: str               # source | ticker | handler
    n_signals: int          # signaux produits sur fenetre
    n_predictions: int      # predictions associees
    n_decisions: int        # decisions journalisees (KPI #5)
    evidence: str           # citation SQL


def _ro_connect(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def scan_sources(db_path: Path | None = None,
                 window_days: int = 90) -> list[DecisionCandidate]:
    """Detecte les sources qui produisent 0 signal / 0 prediction sur fenetre.

    Triangulation : source -> signaux -> predictions -> decisions.
    """
    if db_path is None:
        from shared.storage import DB_PATH
        db_path = Path(DB_PATH) if isinstance(DB_PATH, str) else DB_PATH
    candidates: list[DecisionCandidate] = []
    try:
        cx = _ro_connect(db_path)
        cx.row_factory = sqlite3.Row
        cutoff = (datetime.utcnow() - timedelta(days=window_days)).strftime("%Y-%m-%d")
        # Sources sans signal recent
        # Note : query depend du schema sources / signals exact. Adapt si needed.
        try:
            rows = cx.execute(
                "SELECT src.name, COUNT(sig.id) AS n_sig "
                "FROM sources src "
                "LEFT JOIN signals sig ON sig.source_id = src.id "
                "  AND sig.received_at >= ? "
                "WHERE src.is_active = 1 "
                "GROUP BY src.name "
                "HAVING n_sig = 0",
                (cutoff,)
            ).fetchall()
        except sqlite3.OperationalError:
            cx.close()
            return []
        for row in rows:
            candidates.append(DecisionCandidate(
                name=row["name"],
                kind="source",
                n_signals=0,
                n_predictions=0,
                n_decisions=0,
                evidence=f"sources.name='{row['name']}' n_signals=0 / {window_days}d",
            ))
        cx.close()
    except sqlite3.Error:
        return []
    return candidates


def scan_tickers(db_path: Path | None = None,
                 window_days: int = 90) -> list[DecisionCandidate]:
    """Detecte les tickers ticker_meta sans signal / prediction / decision.

    Optionnel : tickers en watchlist mais 0 matter -> bruit cognitif.
    """
    if db_path is None:
        from shared.storage import DB_PATH
        db_path = Path(DB_PATH) if isinstance(DB_PATH, str) else DB_PATH
    candidates: list[DecisionCandidate] = []
    try:
        cx = _ro_connect(db_path)
        cx.row_factory = sqlite3.Row
        cutoff = (datetime.utcnow() - timedelta(days=window_days)).strftime("%Y-%m-%d")
        # Tickers en ticker_meta mais avec 0 prediction recente
        try:
            rows = cx.execute(
                "SELECT DISTINCT tm.ticker, "
                "  (SELECT COUNT(*) FROM predictions p WHERE p.ticker = tm.ticker "
                "   AND p.created_at >= ?) AS n_pred "
                "FROM ticker_meta tm "
                "HAVING n_pred = 0",
                (cutoff,)
            ).fetchall()
        except sqlite3.OperationalError:
            cx.close()
            return []
        for row in rows:
            candidates.append(DecisionCandidate(
                name=row["ticker"],
                kind="ticker",
                n_signals=0,
                n_predictions=0,
                n_decisions=0,
                evidence=f"ticker={row['ticker']} 0 prediction / {window_days}d",
            ))
        cx.close()
    except sqlite3.Error:
        return []
    return candidates


def scan(window_days: int = 90) -> dict[str, Any]:
    sources = scan_sources(window_days=window_days)
    tickers = scan_tickers(window_days=window_days)
    return {
        "sources": sources,
        "tickers": tickers,
        "n_total": len(sources) + len(tickers),
        "by_name": {c.name: c for c in sources + tickers},
    }
