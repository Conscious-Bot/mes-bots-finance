"""Carte-decision #1 etape 2 : assemble_card_inputs(thesis_id) -> CardInputs.

Source UNIQUE qui assemble toutes les donnees necessaires a la carte-decision
pour 1 these active. N'invente rien (red-team user (a) : pas de signal alpha).
N'agrege qu'aux entrees existantes (CONVENTIONS §5 -- pas de duplication ecriture).

Sources lues :
- storage.get_thesis : champs theses + conviction PIT (apres etape 1)
- storage.get_position_type : type + tags + structural_justification
- shared.book : BookLine canonique (Axe 3/5 M1 propage)
- storage.get_latest_erosion_per_thesis + get_classifications_for_erosion
- storage.get_latest_kca_per_thesis + get_latest_oca_per_ticker
- bias_events.status='open' AND ticker=
- risk_watch.ballast_strict_tickers : ballast membership
- bot_copilot_interventions latest : counter-argument
- config.risk : ruin_budget_per_name_pct + allow_add_steer
- storage.get_conviction_drift : PIT drift

Discipline :
- Lit les sources, retourne None pour les champs absents -- ne RAISE PAS.
- L'etape 3 (derive_card_steer) verra les None et passera en REVIEW.
- Aucune ecriture (read-only).
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass, field

from shared import storage

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CardInputs:
    """Tous les inputs assembles pour la carte-decision #1. Immutable.

    Convention None = donnee absente (raison gere par derive_card_steer).
    """

    # Identification
    thesis_id: int
    ticker: str

    # Thesis state (storage.get_thesis + position_type couche 1)
    thesis: dict
    position_type: str             # 'structural' | 'priced' | 'tactical' | None
    position_tags: list[str] = field(default_factory=list)
    structural_justification: str | None = None

    # Conviction PIT vs current (etape 1)
    conviction_current: int | None = None
    conviction_at_entry: int | None = None
    conviction_drift_delta: int = 0
    conviction_n_drifts: int = 0
    conviction_last_drift_at: str | None = None

    # Position M1 (BookLine canonique)
    book_line: object | None = None  # shared.book.BookLine
    weight_pct: float = 0.0          # weight / total_book * 100
    total_book_eur: float = 0.0

    # Erosion (moteur #2 thesis_erosion)
    erosion_verdict: str | None = None
    erosion_computed_at: str | None = None
    erosion_driver_status: list[dict] = field(default_factory=list)
    erosion_n_confirm: int = 0
    erosion_n_erode: int = 0
    erosion_n_invalidation_hit: int = 0
    erosion_degraded: bool = False
    erosion_classifications: list[dict] = field(default_factory=list)

    # Discipline flags (composition monitors existants)
    kill_status: str | None = None        # dormant | at_risk | triggered
    kill_at: str | None = None
    over_cap_status: str | None = None    # dormant | over
    over_cap_pct: float | None = None
    bias_events_open: list[dict] = field(default_factory=list)
    ballast_membership: bool = False

    # Counter-argument (bot_copilot_interventions latest)
    counter_argument_brief: str | None = None
    counter_argument_pressure_score: int | None = None
    counter_argument_at: str | None = None

    # Sizing 3-way (levier #4 user 07/06)
    cap_for_conviction_pct: float | None = None  # target-conv (cap conviction)
    target_edge_pct: float | None = None          # target-edge-adjusted (ruin budget / downside)
    binding_target_pct: float | None = None       # min(cap_for_conviction, target_edge) = vrai plafond honnete
    sizing_binding: str | None = None             # "conv" | "edge" | "structural" -- quel axe contraint
    ruin_budget_per_name_pct: float = 1.5         # default 1.5%
    allow_add_steer: bool = False

    # Freshness flags (pour fail-closed etape 3)
    price_asof_severity: str | None = None   # 'green' | 'amber' | 'rouge' | 'unknown'
    thesis_review_age_days: int | None = None


def _fetch_bias_events_open_for_ticker(ticker: str) -> list[dict]:
    """Lit bias_events open pour 1 ticker."""
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT id, bias, action, decision_json, created_at, resolve_at "
                "FROM bias_events "
                "WHERE status='open' AND ticker=? "
                "ORDER BY created_at DESC",
                (ticker.upper(),),
            ).fetchall()
            cols = ["id", "bias", "action", "decision_json", "created_at", "resolve_at"]
            return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        log.warning(f"_fetch_bias_events_open_for_ticker failed: {e}")
        return []


def _fetch_counter_argument(ticker: str) -> dict | None:
    """Latest bot_copilot_intervention pour ticker = counter-argument adversarial."""
    try:
        with storage.db() as cx:
            row = cx.execute(
                "SELECT brief, pressure_score, created_at "
                "FROM bot_copilot_interventions "
                "WHERE ticker=? AND brief IS NOT NULL "
                "ORDER BY id DESC LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            if not row:
                return None
            return {"brief": row[0], "pressure_score": row[1], "created_at": row[2]}
    except Exception as e:
        log.warning(f"_fetch_counter_argument failed: {e}")
        return None


def _fetch_ballast_membership(ticker: str) -> bool:
    """Le ticker fait-il partie des ballast_strict_tickers ?"""
    try:
        from shared.risk_watch import load_risk_watch
        cfg = load_risk_watch()
        if not cfg or not cfg.get("risks"):
            return False
        for risk in cfg["risks"]:
            tickers = set(risk.get("ballast_strict_tickers") or [])
            if ticker.upper() in {t.upper() for t in tickers}:
                return True
        return False
    except Exception as e:
        log.warning(f"_fetch_ballast_membership failed: {e}")
        return False


def _fetch_risk_config() -> dict:
    """Lit risk knobs (ruin_budget + allow_add_steer) depuis config.yaml."""
    try:
        from shared import config
        risk = config.load().get("risk", {})
        return {
            "ruin_budget_per_name_pct": float(risk.get("ruin_budget_per_name_pct", 0.015)) * 100,
            "allow_add_steer": bool(risk.get("allow_add_steer", False)),
        }
    except Exception as e:
        log.warning(f"_fetch_risk_config failed: {e}")
        return {"ruin_budget_per_name_pct": 1.5, "allow_add_steer": False}


def _classify_price_asof(book_line) -> str | None:
    """Classify staleness depuis BookLine.price_asof via Axe 5 SLA."""
    if not book_line or not getattr(book_line, "price_asof", None):
        return "unknown"
    try:
        from shared.freshness import classify_asof
        sev, _age = classify_asof("price", book_line.price_asof)
        return sev
    except Exception:
        return "unknown"


def _thesis_review_age_days(thesis: dict) -> int | None:
    """Nombre de jours depuis last_reviewed."""
    iso = thesis.get("last_reviewed")
    if not iso:
        return None
    try:
        from datetime import UTC, datetime
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00").split(".")[0])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return max(0, (datetime.now(UTC) - dt).days)
    except Exception:
        return None


def assemble_card_inputs(thesis_id: int) -> CardInputs | None:
    """Assemble TOUTES les sources pour 1 these en CardInputs frozen.

    Returns None UNIQUEMENT si la these n'existe pas (cas degenere).
    Sinon retourne CardInputs avec champs None si une source est indisponible
    (derive_card_steer gerera).
    """
    thesis = storage.get_thesis(thesis_id)
    if not thesis:
        return None

    ticker = (thesis.get("ticker") or "").upper()

    # Position type (couche 1)
    pt = storage.get_position_type(thesis_id) or {}

    # Conviction drift (etape 1)
    drift = storage.get_conviction_drift(thesis_id) or {}

    # BookLine canonique (post-fix)
    book_line = None
    weight_pct = 0.0
    total_book_eur = 0.0
    try:
        from shared.book import get_book_index
        book_index = get_book_index()
        book_line = book_index.get(ticker)
        # Total book = sum weight_market_eur des lignes tenues
        for ln in book_index.values():
            if ln.in_db and (ln.qty or 0) > 0:
                total_book_eur += ln.weight_market_eur or 0
        if book_line and total_book_eur > 0:
            weight_pct = (book_line.weight_market_eur or 0) / total_book_eur * 100
    except Exception as e:
        log.warning(f"assemble_card_inputs book read failed: {e}")

    # Erosion verdict + classifications
    erosion = storage.get_latest_erosion_per_thesis(thesis_id) or {}
    erosion_verdict = erosion.get("verdict")
    erosion_computed_at = erosion.get("computed_at")
    erosion_classifications = []
    erosion_driver_status = []
    if erosion:
        with contextlib.suppress(Exception):
            erosion_classifications = (
                storage.get_classifications_for_erosion(erosion["id"]) or []
            )
        with contextlib.suppress(Exception):
            erosion_driver_status = json.loads(
                erosion.get("driver_status_json") or "[]"
            )

    # Monitors existants (composition, pas duplication)
    kill_alert = storage.get_latest_kca_per_thesis(thesis_id) or {}
    over_cap = storage.get_latest_oca_per_ticker(ticker) or {}

    # bias_events open
    bias_open = _fetch_bias_events_open_for_ticker(ticker)

    # Ballast membership
    is_ballast = _fetch_ballast_membership(ticker)

    # Counter-argument
    ca = _fetch_counter_argument(ticker)

    # Config risk
    risk_cfg = _fetch_risk_config()

    # Cap for conviction
    cap_pct = None
    if drift.get("current"):
        try:
            from shared.sizing_caps import cap_for_conviction
            cap_pct = cap_for_conviction(int(drift["current"])) * 100
        except Exception:
            pass

    # Target-edge-adjusted (levier #4 sizing asymetrie-first)
    # Honnete sub-Kelly N<100 : bride par budget-ruine par nom plutot que
    # conviction seule. Structural (stop=None) -> target_edge None.
    target_edge = None
    sizing_binding = None
    binding_target = cap_pct
    try:
        from shared.sizing_caps import target_edge_pct
        current_px = getattr(book_line, "current_price_eur", None) if book_line else None
        target_edge = target_edge_pct(
            entry=thesis.get("entry_price"),
            stop=thesis.get("stop_price"),
            current=current_px,
            ruin_budget_pct=risk_cfg["ruin_budget_per_name_pct"],
            direction=thesis.get("direction", "long"),
        )
        # Determine binding axis : min(cap_conv, target_edge) si les 2 dispos,
        # sinon le seul disponible. Structural = pas de target_edge -> binding="structural".
        if pt.get("position_type") == "structural" or target_edge is None:
            sizing_binding = "structural" if pt.get("position_type") == "structural" else "conv"
            binding_target = cap_pct
        elif cap_pct is not None and target_edge < cap_pct:
            sizing_binding = "edge"
            binding_target = target_edge
        else:
            sizing_binding = "conv"
            binding_target = cap_pct
    except Exception as e:
        log.warning(f"target_edge_pct compute failed: {e}")

    # Freshness pour fail-closed
    price_sev = _classify_price_asof(book_line)
    review_age = _thesis_review_age_days(thesis)

    return CardInputs(
        thesis_id=thesis_id,
        ticker=ticker,
        thesis=thesis,
        position_type=pt.get("position_type") or "priced",
        position_tags=pt.get("position_tags") or [],
        structural_justification=pt.get("structural_justification"),
        conviction_current=drift.get("current"),
        conviction_at_entry=drift.get("at_entry"),
        conviction_drift_delta=drift.get("delta", 0),
        conviction_n_drifts=drift.get("n_drifts", 0),
        conviction_last_drift_at=drift.get("last_drift_at"),
        book_line=book_line,
        weight_pct=round(weight_pct, 2),
        total_book_eur=round(total_book_eur, 2),
        erosion_verdict=erosion_verdict,
        erosion_computed_at=erosion_computed_at,
        erosion_driver_status=erosion_driver_status,
        erosion_n_confirm=erosion.get("n_confirm", 0),
        erosion_n_erode=erosion.get("n_erode", 0),
        erosion_n_invalidation_hit=erosion.get("n_invalidation_hit", 0),
        erosion_degraded=bool(erosion.get("degraded", 0)),
        erosion_classifications=erosion_classifications,
        kill_status=kill_alert.get("status"),
        kill_at=kill_alert.get("created_at"),
        over_cap_status=over_cap.get("status"),
        over_cap_pct=over_cap.get("weight_pct"),
        bias_events_open=bias_open,
        ballast_membership=is_ballast,
        counter_argument_brief=(ca or {}).get("brief"),
        counter_argument_pressure_score=(ca or {}).get("pressure_score"),
        counter_argument_at=(ca or {}).get("created_at"),
        cap_for_conviction_pct=cap_pct,
        target_edge_pct=round(target_edge, 2) if target_edge is not None else None,
        binding_target_pct=round(binding_target, 2) if binding_target is not None else None,
        sizing_binding=sizing_binding,
        ruin_budget_per_name_pct=risk_cfg["ruin_budget_per_name_pct"],
        allow_add_steer=risk_cfg["allow_add_steer"],
        price_asof_severity=price_sev,
        thesis_review_age_days=review_age,
    )
