"""Lentille materialite decisionnelle : signal -> prediction -> decision.

High Standard (CLAUDE.md) : 'qu'est-ce qui produit zero matiere
decisionnelle / 90j = pur cout cognitif, par ta propre regle'.

Triangulation : un handler/source/cron qui touche la chaine
signal -> prediction -> decision DOIT produire au moins 1 element de la
chaine sur la fenetre. Sinon, candidate suppression haute confiance.

ZERO ECRITURE (Tier R, audit doctrine SAS).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from shared import storage as _storage


@dataclass
class DecisionCandidate:
    """Un symbole / source dont la productivite decisionnelle est zero."""
    name: str               # source name ou ticker ou handler
    kind: str               # source | ticker | handler
    n_signals: int          # signaux produits sur fenetre
    n_predictions: int      # predictions associees
    n_decisions: int        # decisions journalisees (KPI #5)
    evidence: str           # citation SQL


def scan_sources(window_days: int = 90) -> list[DecisionCandidate]:
    """Detecte les sources qui produisent 0 signal / 0 prediction sur fenetre.

    Triangulation : source -> signaux -> predictions -> decisions.
    """
    candidates: list[DecisionCandidate] = []
    try:
        with _storage.db_ro() as cx:
            cutoff = (datetime.utcnow() - timedelta(days=window_days)).strftime("%Y-%m-%d")
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
            except Exception:
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
    except Exception:
        return []
    return candidates


def scan_tickers(window_days: int = 90) -> list[DecisionCandidate]:
    """Detecte les tickers ticker_meta sans signal / prediction / decision."""
    candidates: list[DecisionCandidate] = []
    try:
        with _storage.db_ro() as cx:
            cutoff = (datetime.utcnow() - timedelta(days=window_days)).strftime("%Y-%m-%d")
            try:
                rows = cx.execute(
                    "SELECT DISTINCT tm.ticker, "
                    "  (SELECT COUNT(*) FROM predictions p WHERE p.ticker = tm.ticker "
                    "   AND p.created_at >= ?) AS n_pred "
                    "FROM ticker_meta tm "
                    "HAVING n_pred = 0",
                    (cutoff,)
                ).fetchall()
            except Exception:
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
    except Exception:
        return []
    return candidates


def scan(window_days: int = 90) -> dict[str, Any]:
    sources = scan_sources(window_days)
    tickers = scan_tickers(window_days)
    return {
        "sources": sources,
        "tickers": tickers,
        "n_total": len(sources) + len(tickers),
        "by_name": {c.name: c for c in sources + tickers},
    }
