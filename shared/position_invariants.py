"""PRESAGE — Invariants du book canonique. Gate statique, echec fort.

Implementation formelle du brief 10 points du 29/05/2026 (round 5).
Le critere de fin : run_static_gate(conn) vert = book verrouille.

Les 10 invariants :

1. **Source unique** : positions est la seule verite portfolio.
2. **3 couches** : Fait / Jugement / Derive jamais melanges.
3. **2 passerelles** : tout SQL via storage.py, tout derive via
   storage.get_position_view().
4. **Un driver canonique** par position.
5. **Thèse figee** a l'entree (triggers + append-only).
6. **Lifecycle** de premiere classe (enum strict).
7. **Decision ⇒ prediction** (fermeture de boucle).
8. **Digest ancre au book**.
9. **Invariants en gate, echec fort** (ce fichier).
10. **EUR-canonique + reconciliation**.

run_static_gate() retourne une liste de violations OU leve InvariantViolation
si strict=True (defaut au demarrage). Silencieux jamais.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class InvariantViolation(Exception):
    """Le book refuse d'etre incoherent. Echec fort, pas silencieux."""


# ─────────────────────── Invariants individuels ────────────────────────────


def _check_one_driver_per_position(conn) -> list[str]:
    """Point #4 : un seul driver canonical COURANT (latest) par position.

    L'historique de ticker_axes peut contenir des re-classifications, mais
    le driver effectif (latest by id) doit etre unique. On verifie que
    chaque position en DB resout vers EXACTEMENT 1 driver actif.
    """
    violations = []
    # Latest driver per ticker via correlated subquery
    rows = conn.execute("""
        SELECT p.ticker,
               (SELECT macro_factor FROM ticker_axes ta
                WHERE ta.ticker = p.ticker
                ORDER BY id DESC LIMIT 1) as latest_driver
        FROM positions p
        WHERE p.status='open' AND p.qty > 0
    """).fetchall()
    for r in rows:
        tk, latest = r[0], r[1]
        if latest is None:
            violations.append(f"#4 {tk} en DB mais 0 driver canonical (ticker_axes vide)")
    return violations


def _check_no_active_thesis_orphan(conn) -> list[str]:
    """Point #4 + #5 : these active <=> position ouverte (pas orpheline)."""
    violations = []
    # These actives sans position ouverte
    rows = conn.execute("""
        SELECT t.id, t.ticker FROM theses t
        WHERE t.status='active'
          AND NOT EXISTS (
              SELECT 1 FROM positions p
              WHERE p.ticker=t.ticker AND p.status='open' AND p.qty > 0
          )
    """).fetchall()
    for r in rows:
        violations.append(f"#5 these_{r[0]} {r[1]} active mais aucune position ouverte")
    return violations


def _check_weights_sum_100(conn) -> list[str]:  # noqa: ARG001
    """Point #2 : somme des weight_pct = 100% (delta < 0.5%)."""
    violations = []
    try:
        from shared import views

        bv = views.compute_book_view(use_cache=False)
        s = sum(pv.weight_pct for pv in bv.by_ticker.values())
        if abs(s - 100.0) > 0.5:
            violations.append(f"#2 sum(weight_pct) = {s:.2f} != 100")
    except Exception as e:
        violations.append(f"#2 BookView indispo: {type(e).__name__}: {e}")
    return violations


def _check_no_thesis_active_blind(conn) -> list[str]:
    """Point #5 : these active doit avoir target_full OU stop_price OU
    kill_criteria definis (pas vol aveugle integral).

    Exception documentee : SNOW (open_question dans canonical, tracked
    dans property tests).
    """
    violations = []
    accepted_blind = {"SNOW"}
    rows = conn.execute("""
        SELECT t.id, t.ticker, t.entry_price, t.target_full, t.stop_price,
               t.invalidation_triggers
        FROM theses t
        INNER JOIN positions p ON p.ticker = t.ticker
        WHERE t.status='active' AND p.qty > 0 AND p.status='open'
    """).fetchall()
    for _tid, tk, entry, tgt, stop, kc in rows:
        if tk in accepted_blind:
            continue
        is_blind = (
            entry is None
            and tgt is None
            and stop is None
            and (not kc or kc == "[]")
        )
        if is_blind:
            violations.append(f"#5 {tk} these active TOTALLY blind (rien defini)")
    return violations


def _check_position_in_db_has_avg_cost(conn) -> list[str]:
    """Point #10 : avg_cost > 0 sur position ouverte (sinon donnees corrompues).

    Post-0049 (VUE NULL fail-closed) : la VUE positions retourne NULL sur
    avg_cost. Le PMP fiscal correct vient maintenant de BookLine (qui
    appelle ledger_pmp.compute_pmp_realized). On lit donc BookLine pour
    valider l'invariant — la VUE NULL est attendue, pas une corruption.
    """
    violations = []
    try:
        from shared.book import get_held_lines
        for ln in get_held_lines():
            if ln.qty and ln.qty > 0 and (ln.avg_cost_eur is None or ln.avg_cost_eur <= 0):
                violations.append(
                    f"#10 {ln.ticker} qty={ln.qty} avg_cost_eur={ln.avg_cost_eur} "
                    f"(BookLine ledger_pmp donne None/0 — ticker absent de transactions ?)"
                )
    except Exception as e:
        violations.append(f"#10 BookLine load failed: {e}")
    return violations


def _check_no_recent_material_decision_orphan(conn) -> list[str]:
    """Point #7 : decision materielle recente -> prediction OU decision_counterfactual.

    Pre-V0 cutoff : decisions id<=19 sont historiquement orphelines (avant
    le hook self_loop 53ec271). Apres : nouvelle orpheline = regression.
    """
    from datetime import UTC, datetime, timedelta

    cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    rows = conn.execute("""
        SELECT id, ticker FROM decisions
        WHERE created_at >= ?
          AND decision_type IN ('entry', 'scale_in', 'full_exit', 'partial_exit')
          AND ticker != '*PORTFOLIO*'
          AND id > 19
    """, (cutoff,)).fetchall()
    violations = []
    for d_id, tk in rows:
        n_cf = conn.execute(
            "SELECT COUNT(*) FROM decision_counterfactual WHERE decision_id=?",
            (d_id,)
        ).fetchone()[0]
        if n_cf > 0:
            continue
        # Check prediction window (heuristique +60min)
        n_pred = conn.execute(
            "SELECT COUNT(*) FROM predictions p, decisions d "
            "WHERE p.ticker=? AND d.id=? "
            "AND p.created_at BETWEEN d.created_at AND datetime(d.created_at, '+60 minutes')",
            (tk, d_id),
        ).fetchone()[0]
        if n_pred == 0:
            violations.append(f"#7 decision_{d_id} {tk} sans artefact d'outcome")
    return violations


def _check_resolved_predictions_have_brier(conn) -> list[str]:
    """Point #7 + scoring : resolved + outcome != neutral => brier present."""
    rows = conn.execute("""
        SELECT id, ticker, outcome, brier_score FROM predictions
        WHERE resolved_at IS NOT NULL AND outcome != 'neutral'
          AND brier_score IS NULL
    """).fetchall()
    return [f"#7 pred_{r[0]} {r[1]} resolved outcome={r[2]} mais brier=NULL" for r in rows]


def _check_no_phantom_ghosts_in_views(conn) -> list[str]:
    """Point #10 : positions vendues sortent des vues actives.
    Une qty=0 status=open est un fantome a fermer."""
    rows = conn.execute(
        "SELECT ticker FROM positions WHERE status='open' AND (qty=0 OR qty IS NULL)"
    ).fetchall()
    return [f"#10 {r[0]} status=open mais qty=0 (fantome a fermer)" for r in rows]


# ─────────────────────── Gate statique principal ───────────────────────────


def run_static_gate(conn, *, strict: bool = True) -> list[str]:
    """Verifie les invariants du book. Retourne la liste des violations.

    Args:
        conn: connexion SQLite (typiquement storage.db())
        strict: si True (defaut), leve InvariantViolation au moindre defaut.
                Si False, retourne juste la liste pour audit.

    Returns:
        Liste vide = gate verte = book verrouille.
        Liste non-vide = violations (et exception si strict).

    Invariants verifies (mapping aux 10 points du brief) :
        #2 sum(weights) = 100%
        #4 un driver par position
        #5 thesis active <=> position ouverte + inputs presents
        #7 decision materielle -> artefact outcome
        #7 resolved prediction non-neutral -> brier present
        #10 avg_cost > 0 sur open
        #10 pas de fantome qty=0 status=open
    """
    violations: list[str] = []
    # Import des checks thesis_invariants (currency + kill_criteria substance)
    from shared.thesis_invariants import (
        check_currency_native_consistency,
        check_kill_criteria_substance,
    )

    checks = [
        _check_one_driver_per_position,
        _check_no_active_thesis_orphan,
        _check_weights_sum_100,
        _check_no_thesis_active_blind,
        _check_position_in_db_has_avg_cost,
        _check_no_recent_material_decision_orphan,
        _check_resolved_predictions_have_brier,
        _check_no_phantom_ghosts_in_views,
        check_kill_criteria_substance,
        check_currency_native_consistency,
    ]
    for check in checks:
        try:
            violations.extend(check(conn))
        except Exception as e:
            violations.append(f"check {check.__name__} crashed: {e}")

    if violations and strict:
        msg = (
            "🚨 BOOK INVARIANT VIOLATION (gate refuse l'incoherence) :\n  "
            + "\n  ".join(violations)
            + "\n\nLe book refuse d'etre incoherent. Reparer avant de continuer."
        )
        raise InvariantViolation(msg)
    return violations


def run_static_gate_silent(conn) -> dict:
    """Wrapper qui retourne un report dict (pour CI/audit/dashboard).

    Returns: {"status": "green"|"red", "n_violations": int, "violations": [...]}.
    """
    v = run_static_gate(conn, strict=False)
    return {
        "status": "green" if not v else "red",
        "n_violations": len(v),
        "violations": v,
    }
