"""PRESAGE — Book canonique unifie. Source de verite UNIQUE sur les positions.

Avant ce module (29/05/2026), 3 jeux flottaient :
1. positions DB (qty>0, status='open') -- realite operationnelle
2. canonical_perimeter.json -- table de reference user (solidite, driver, pari)
3. target_allocation.json -- cible 70k structuree (29/05 -- avant : image seulement)

Chaque vue/monitor lisait l'un des trois en raw SQL ou en read direct,
accumulant la derive (fantomes, dénominateurs faux, sizing sur book
incomplet). Cf. VERDICT D'ENSEMBLE racine #1 du TODO.

Ce module expose `get_canonical_book()` -> liste de BookLine objets joins
des 3 sources. Toute vue/monitor doit s'y brancher. Le raw SQL sur
positions devient ANTI-PATTERN -- a refactorer vers get_canonical_book().

Contract de la BookLine :
    ticker : str
    nom : str
    wrapper : "PEA" | "CTO" | "AVUS" | None
    # Operational (DB positions) -- None si pas en DB
    qty : float | None
    avg_cost_eur : float | None
    current_eur : float | None  # qty * current_price_eur
    # Canonical (canonical_perimeter.json) -- None si hors perimetre
    driver : str | None
    pari : "principal" | "autre" | "hors-these" | None
    solidite : "Incontournable" | "Solide" | "Incertain" | "Fragile" | None
    target_status : "in_target" | "open_question" | "exit_planned" | "archived" | "unknown"
    surveillance : str | None
    # Target (target_allocation.json) -- None si pas dans cible
    target_eur : float | None
    target_pct : float | None
    theme : str | None
    tier : str | None
    # Computed
    gap_eur : float | None  # target_eur - current_eur
    in_db : bool
    in_canonical : bool
    in_target_70k : bool
    is_phantom : bool  # in DB mais exit_planned
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_CANONICAL_PATH = _REPO_ROOT / "scripts" / "canonical_perimeter.json"
_TARGET_PATH = _REPO_ROOT / "scripts" / "target_allocation.json"

# Cache (cleared via clear_cache() if needed -- rare, files change at user gesture)
_CANONICAL_CACHE: dict | None = None
_TARGET_CACHE: dict | None = None


@dataclass
class BookLine:
    ticker: str
    nom: str = ""
    wrapper: str | None = None
    # Operational
    qty: float | None = None
    avg_cost_eur: float | None = None
    current_eur: float | None = None
    # Canonical
    driver: str | None = None
    pari: str | None = None
    solidite: str | None = None
    target_status: str = "unknown"
    surveillance: str | None = None
    # Target
    target_eur: float | None = None
    target_pct: float | None = None
    theme: str | None = None
    tier: str | None = None
    # Computed
    in_db: bool = False
    in_canonical: bool = False
    in_target_70k: bool = False

    @property
    def gap_eur(self) -> float | None:
        """target_eur - current_eur (positif = a renforcer, negatif = au-dessus cible)."""
        if self.target_eur is None or self.current_eur is None:
            return None
        return self.target_eur - self.current_eur

    @property
    def is_phantom(self) -> bool:
        """In DB mais marquee exit_planned -> a sortir progressivement."""
        return self.in_db and self.target_status == "exit_planned"

    @property
    def is_planned_entry(self) -> bool:
        """In target mais pas encore en DB -> entree planifiee."""
        return self.in_target_70k and not self.in_db

    @property
    def is_consensus_keep(self) -> bool:
        """In DB + in canonical (in_target) + in target_70k -> consensus."""
        return self.in_db and self.target_status == "in_target" and self.in_target_70k


def _load_canonical() -> dict:
    global _CANONICAL_CACHE
    if _CANONICAL_CACHE is None:
        try:
            _CANONICAL_CACHE = json.loads(_CANONICAL_PATH.read_text())
        except Exception:
            _CANONICAL_CACHE = {"positions": []}
    return _CANONICAL_CACHE


def _load_target() -> dict:
    global _TARGET_CACHE
    if _TARGET_CACHE is None:
        try:
            _TARGET_CACHE = json.loads(_TARGET_PATH.read_text())
        except Exception:
            _TARGET_CACHE = {"positions": []}
    return _TARGET_CACHE


def clear_cache() -> None:
    """Force reload des 3 sources (utile apres edit JSON ou tests)."""
    global _CANONICAL_CACHE, _TARGET_CACHE
    _CANONICAL_CACHE = None
    _TARGET_CACHE = None


def _load_db_positions() -> dict[str, dict]:
    """ticker -> {qty, avg_cost_eur} pour les positions ouvertes."""
    from shared import storage

    out: dict[str, dict] = {}
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT ticker, qty, avg_cost FROM positions "
                "WHERE status='open' AND qty > 0"
            ).fetchall()
            for r in rows:
                out[r[0]] = {"qty": r[1], "avg_cost_eur": r[2]}
    except Exception:
        pass
    return out


def _current_price_eur(ticker: str) -> float | None:
    """Reuse le cached price de render.py pour eviter de re-fetch yfinance."""
    try:
        from dashboard.render import _cached_price_eur

        return _cached_price_eur(ticker)
    except Exception:
        return None


def get_canonical_book(*, with_prices: bool = True) -> list[BookLine]:
    """Source unique de verite sur le book.

    Args:
        with_prices: si True (defaut), fetch current_eur via _cached_price_eur.
                     Si False, current_eur reste None -- utile pour les tests
                     ou les jobs qui n'ont pas besoin du current price.

    Returns:
        Liste de BookLine, sortee par ticker. Inclut tout ticker present
        dans AU MOINS UNE des 3 sources (DB / canonical / target_70k).
    """
    db_pos = _load_db_positions()
    canonical = _load_canonical()
    target = _load_target()

    can_by_tk = {p["ticker"]: p for p in canonical.get("positions", [])}
    tgt_by_tk = {p["ticker"]: p for p in target.get("positions", [])}

    all_tickers = set(db_pos) | set(can_by_tk) | set(tgt_by_tk)

    book: list[BookLine] = []
    for tk in sorted(all_tickers):
        db_row = db_pos.get(tk)
        can_row = can_by_tk.get(tk)
        tgt_row = tgt_by_tk.get(tk)

        line = BookLine(
            ticker=tk,
            nom=(can_row or tgt_row or {}).get("nom") or tk,
            wrapper=(can_row or tgt_row or {}).get("wrapper"),
            qty=(db_row or {}).get("qty"),
            avg_cost_eur=(db_row or {}).get("avg_cost_eur"),
            driver=(can_row or {}).get("driver"),
            pari=(can_row or {}).get("pari"),
            solidite=(can_row or {}).get("solidite"),
            target_status=(can_row or {}).get("target_status") or "unknown",
            surveillance=(can_row or {}).get("surveillance"),
            target_eur=(tgt_row or {}).get("amount_eur"),
            target_pct=(tgt_row or {}).get("pct"),
            theme=(tgt_row or {}).get("theme"),
            tier=(tgt_row or {}).get("tier"),
            in_db=db_row is not None,
            in_canonical=can_row is not None,
            in_target_70k=tgt_row is not None,
        )
        if with_prices and line.qty is not None:
            px = _current_price_eur(tk)
            if px is not None:
                line.current_eur = line.qty * px
        book.append(line)
    return book


def book_summary() -> dict:
    """Resume du book : totaux + brackets etat. Utile pour diagnostiquer
    instantanement la coherence des 3 sources."""
    book = get_canonical_book(with_prices=True)
    current_total = sum(line.current_eur or 0 for line in book if line.in_db)
    target_total = sum(line.target_eur or 0 for line in book if line.in_target_70k)
    return {
        "current_eur": round(current_total, 2),
        "target_eur": round(target_total, 2),
        "gap_eur": round(target_total - current_total, 2),
        "progress_pct": round(current_total / target_total * 100, 1) if target_total else 0,
        "lines_in_db": sum(1 for ln in book if ln.in_db),
        "lines_in_target": sum(1 for ln in book if ln.in_target_70k),
        "lines_in_canonical": sum(1 for ln in book if ln.in_canonical),
        "phantoms": [ln.ticker for ln in book if ln.is_phantom],
        "planned_entries": [ln.ticker for ln in book if ln.is_planned_entry],
        "open_questions": [ln.ticker for ln in book if ln.target_status == "open_question"],
        "consensus_keep_count": sum(1 for ln in book if ln.is_consensus_keep),
    }
