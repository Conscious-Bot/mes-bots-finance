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

# Phase 1.5 absorption_roadmap : target migre vers YAML versionne avec _meta block.
# YAML canonical, JSON gardé en fallback transitoire (suppression Phase 2 si propre).
# Lecture : YAML d'abord, JSON ensuite. Si YAML present + valide via Pydantic,
# c'est lui qui gagne. cf docs/templates/workflow_yaml_pattern.md + L17 LESSONS.
_TARGET_YAML_PATH = _REPO_ROOT / "config" / "target_allocation.yaml"
_TARGET_JSON_PATH = _REPO_ROOT / "scripts" / "target_allocation.json"

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
    current_price_eur: float | None = None
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
    # Thesis joints (added 29/05 round 2 for migration)
    thesis_id: int | None = None
    conviction: int | None = None
    entry_price: float | None = None
    target_partial: float | None = None
    target_full: float | None = None
    stop_price: float | None = None
    invalidation_triggers: str | None = None
    # Macro factor (ticker_axes) -- THE single source of truth for "AI capex" etc
    macro_factor: str | None = None
    # Quality meta (ticker_meta) -- fade_rate + bull case flags
    fade_rate_score: int | None = None
    moat_durability_years: int | None = None
    valo_above_bull_case: bool = False
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
    def pnl_pct(self) -> float | None:
        """(current_price - avg_cost) / avg_cost * 100. None si l'un des deux manque."""
        if not self.avg_cost_eur or not self.current_price_eur:
            return None
        return (self.current_price_eur - self.avg_cost_eur) / self.avg_cost_eur * 100

    @property
    def weight_market_eur(self) -> float:
        """Poids en MARKET VALUE (= current_eur). Fallback cost basis si current
        price indispo. C'est l'unique definition de 'poids' apres la migration."""
        if self.current_eur is not None:
            return self.current_eur
        if self.qty is not None and self.avg_cost_eur is not None:
            return self.qty * self.avg_cost_eur
        return 0.0

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

    @property
    def is_blind(self) -> bool:
        """Position en vol aveugle : these active sans entry, target_full,
        stop_price OU invalidation_triggers (cf F7 audit nuit)."""
        if not self.in_db:
            return False
        if self.entry_price is None:
            return True
        if self.target_full is None:
            return True
        if self.stop_price is None:
            return True
        return not self.invalidation_triggers or self.invalidation_triggers == "[]"


def _load_canonical() -> dict:
    global _CANONICAL_CACHE
    if _CANONICAL_CACHE is None:
        try:
            _CANONICAL_CACHE = json.loads(_CANONICAL_PATH.read_text())
        except Exception:
            _CANONICAL_CACHE = {"positions": []}
    return _CANONICAL_CACHE


def _load_target() -> dict:
    """Lit la cible book. YAML canonique (Phase 1.5), JSON fallback transitoire.

    Returns dict en forme JSON legacy (keys: positions, phantoms_in_db_not_in_target,
    _meta). Les callers downstream n'ont pas a changer leur acces.

    YAML est valide via Pydantic TargetAllocationConfig au load. Validation echec
    -> log.warning + fallback JSON (preserve disponibilite, le YAML est WIP).
    Si JSON aussi absent -> dict vide (legacy behavior).
    """
    global _TARGET_CACHE
    if _TARGET_CACHE is not None:
        return _TARGET_CACHE

    # Try YAML first (canonical)
    if _TARGET_YAML_PATH.exists():
        try:
            import yaml

            from intelligence.target_allocation_schema import TargetAllocationConfig
            raw = yaml.safe_load(_TARGET_YAML_PATH.read_text())
            # Valide via Pydantic. by_alias=True garde _meta avec son nom.
            cfg = TargetAllocationConfig.model_validate(raw)
            _TARGET_CACHE = cfg.model_dump(by_alias=True, mode="json")
            return _TARGET_CACHE
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"target_allocation.yaml invalide ({type(e).__name__}: {e}). "
                f"Fallback JSON. cf L17 LESSONS."
            )

    # Fallback JSON
    try:
        _TARGET_CACHE = json.loads(_TARGET_JSON_PATH.read_text())
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


def _load_theses_active() -> dict[str, dict]:
    """ticker -> these active (1 par ticker = la plus recente)."""
    from shared import storage

    out: dict[str, dict] = {}
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT t.id, t.ticker, t.conviction, t.entry_price, "
                "t.target_partial, t.target_full, t.stop_price, "
                "t.invalidation_triggers "
                "FROM theses t WHERE t.status='active' ORDER BY t.id DESC"
            ).fetchall()
            for r in rows:
                if r[1] not in out:
                    out[r[1]] = {
                        "thesis_id": r[0],
                        "conviction": r[2],
                        "entry_price": r[3],
                        "target_partial": r[4],
                        "target_full": r[5],
                        "stop_price": r[6],
                        "invalidation_triggers": r[7],
                    }
    except Exception:
        pass
    return out


def _load_ticker_axes() -> dict[str, dict]:
    """ticker -> {macro_factor, driver, stage, moat}."""
    from shared import storage

    try:
        return {a["ticker"]: a for a in storage.get_all_latest_ticker_axes()}
    except Exception:
        return {}


def _load_ticker_meta() -> dict[str, dict]:
    """ticker -> {fade_rate_score, moat_durability_years, valo_above_bull_case}."""
    from shared import storage

    try:
        return {m["ticker"]: m for m in storage.get_all_latest_ticker_meta()}
    except Exception:
        return {}


def _current_price_eur(ticker: str) -> float | None:
    """Reuse le cached price de render.py pour eviter de re-fetch yfinance."""
    try:
        from dashboard.render import _cached_price_eur

        return _cached_price_eur(ticker)
    except Exception:
        return None


def get_canonical_book(*, with_prices: bool = True) -> list[BookLine]:
    """Source unique de verite sur le book.

    Joint 5 sources :
      - positions DB (operationnel : qty, avg_cost)
      - canonical_perimeter.json (driver, pari, solidite, target_status)
      - target_allocation.json (cible 70k structuree)
      - theses (conviction, entry/target/stop/triggers)
      - ticker_axes (macro_factor) -- the ONLY source for macro classification
      - ticker_meta (fade_rate_score, valo_above_bull_case)

    Args:
        with_prices: si True (defaut), fetch current_price_eur + current_eur
                     via _cached_price_eur (throttle yfinance respecte).
                     False utile pour les tests.

    Returns:
        Liste de BookLine, sortee par ticker. Inclut tout ticker present
        dans AU MOINS UNE source.
    """
    db_pos = _load_db_positions()
    canonical = _load_canonical()
    target = _load_target()
    theses = _load_theses_active()
    axes = _load_ticker_axes()
    meta = _load_ticker_meta()

    can_by_tk = {p["ticker"]: p for p in canonical.get("positions", [])}
    tgt_by_tk = {p["ticker"]: p for p in target.get("positions", [])}

    all_tickers = set(db_pos) | set(can_by_tk) | set(tgt_by_tk)

    book: list[BookLine] = []
    for tk in sorted(all_tickers):
        db_row = db_pos.get(tk)
        can_row = can_by_tk.get(tk)
        tgt_row = tgt_by_tk.get(tk)
        th_row = theses.get(tk) or {}
        ax_row = axes.get(tk) or {}
        mt_row = meta.get(tk) or {}

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
            thesis_id=th_row.get("thesis_id"),
            conviction=th_row.get("conviction"),
            entry_price=th_row.get("entry_price"),
            target_partial=th_row.get("target_partial"),
            target_full=th_row.get("target_full"),
            stop_price=th_row.get("stop_price"),
            invalidation_triggers=th_row.get("invalidation_triggers"),
            macro_factor=ax_row.get("macro_factor"),
            fade_rate_score=mt_row.get("fade_rate_score"),
            moat_durability_years=mt_row.get("moat_durability_years"),
            valo_above_bull_case=bool(mt_row.get("valo_above_bull_case")),
            in_db=db_row is not None,
            in_canonical=can_row is not None,
            in_target_70k=tgt_row is not None,
        )
        if with_prices and line.qty is not None:
            px = _current_price_eur(tk)
            if px is not None:
                line.current_price_eur = px
                line.current_eur = line.qty * px
        book.append(line)
    return book


def get_book_index() -> dict[str, BookLine]:
    """Index ticker -> BookLine pour lookup O(1). Utile dans les boucles
    de panel/monitor qui ont besoin de jointer par ticker rapide."""
    return {line.ticker: line for line in get_canonical_book(with_prices=True)}


def get_held_lines() -> list[BookLine]:
    """Filtered : seulement les positions ouvertes (in_db=True).
    Substitution drop-in pour les anciens _positions() readers."""
    return [line for line in get_canonical_book(with_prices=True) if line.in_db]


# ─────────────────────── Nouveau : Position canonique (FAIT/JUGEMENT/...) ──
# Refactor round 3 sur directive user. La couche BookLine ci-dessus est
# preservee pour backward compat. La couche Position est la "vraie" source.


def get_canonical_positions() -> list:
    """Construit des Position (shared.position) -- objet canonique avec
    layers strictes FAIT / JUGEMENT / DERIVE / HISTORIQUE.

    A terme remplace get_canonical_book(). Aujourd'hui les deux coexistent
    pendant la migration des readers."""
    from shared.position import position_from_sources

    db_pos = _load_db_positions()
    canonical = _load_canonical()
    target = _load_target()
    theses = _load_theses_active()
    axes = _load_ticker_axes()
    meta = _load_ticker_meta()

    can_by_tk = {p["ticker"]: p for p in canonical.get("positions", [])}
    tgt_by_tk = {p["ticker"]: p for p in target.get("positions", [])}

    all_tickers = set(db_pos) | set(can_by_tk) | set(tgt_by_tk)
    positions = []
    for tk in sorted(all_tickers):
        cur_eur = _current_price_eur(tk)
        positions.append(position_from_sources(
            ticker=tk,
            db_row=db_pos.get(tk),
            canonical_row=can_by_tk.get(tk),
            target_row=tgt_by_tk.get(tk),
            thesis_row=theses.get(tk),
            axes_row=axes.get(tk),
            meta_row=meta.get(tk),
            current_price_eur=cur_eur,
            current_price_native=None,  # TODO : separer le prix native du prix eur
        ))
    return positions


def get_held_positions() -> list:
    """Filtered: seulement les positions tenues (qty > 0)."""
    return [p for p in get_canonical_positions() if p.in_db]


def validate_all_positions() -> dict:
    """Aggregate validate() sur toutes les positions.
    Retourne {n_total, n_clean, violations: [(ticker, [violations...])]}."""
    pos = get_canonical_positions()
    violations = []
    for p in pos:
        v = p.validate()
        if v:
            violations.append((p.ticker, v))
    return {
        "n_total": len(pos),
        "n_clean": len(pos) - len(violations),
        "n_with_violations": len(violations),
        "violations": violations,
    }


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
