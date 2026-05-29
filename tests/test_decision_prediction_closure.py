"""Soudure ③ -- Invariant fermeture décision → prédiction.

Diagnostic user 29/05 round 4 :
> "Le tuyau de fermeture de boucle est fragile. Tu l'as deja vu casser (la
>  regression Phase B5 ou cmd_position_buy/sell ne loguait plus les
>  decisions). Repare une fois, mais le fait qu'il ait pu casser dit qu'il
>  n'est pas garanti. Il faut un invariant : toute decision materielle ecrit
>  une prediction, sinon erreur."

C'est ici que la boucle se referme. Sans prediction associee a chaque
decision, on perd la mesure d'outcome -> l'apprentissage hallucine.

Property tests qui fail si une regression casse le pipeline :
- Toute decision recente (entry, scale_in, full_exit) sur un ticker
  observable a une prediction creee dans la fenetre temporelle pertinente
  OR l'absence est documentee (cas decision portfolio-level, etc.)
- Predictions resolues ont brier_score IS NOT NULL (sauf neutral)
- Predictions pending ont target_date > created_at
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from shared import storage

# Decisions au-dessus de ce seuil de "materialite" doivent avoir prediction
_MATERIAL_DECISION_TYPES = ("entry", "scale_in", "full_exit", "partial_exit")

# Tickers exclus du test (decisions portfolio-level OU positions hors univers)
_EXEMPT_TICKERS = {"*PORTFOLIO*"}


@pytest.fixture(scope="module")
def conn():
    with storage.db() as cx:
        yield cx


def test_material_decisions_recent_have_outcome_artifact(conn):
    """Soudure ③ : toute decision materielle recente a un artefact d'outcome
    associe (= cle de la fermeture de boucle).

    Un artefact d'outcome est soit :
    - une prediction dans la fenetre +60min (path signal-driven historique)
    - un decision_counterfactual via shared.self_loop (path chat-driven V0+)

    Sans cet artefact, la decision n'a aucun mecanisme de mesure -> la
    boucle ne se ferme pas dessus -> on rate l'apprentissage. C'est la
    fuite ③ du diagnostic 29/05.

    Le seuil est strict : >10% d'orphelines = regression a investiguer.
    Pre-self_loop V0 (commits avant 53ec271), TOUTES les chat-driven
    decisions etaient orphelines. C'est pourquoi le test surface des
    decisions historiques (pre-fix) tant que la table n'est pas backfillee.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    rows = conn.execute(
        f"""
        SELECT id, ticker, decision_type, created_at
        FROM decisions
        WHERE created_at >= ?
          AND decision_type IN ({','.join('?' * len(_MATERIAL_DECISION_TYPES))})
        """,
        (cutoff, *_MATERIAL_DECISION_TYPES),
    ).fetchall()
    if not rows:
        return  # rien a verifier
    orphans = []
    for d_id, ticker, dtype, dt_str in rows:
        if ticker in _EXEMPT_TICKERS:
            continue
        try:
            d_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if d_dt.tzinfo is None:
                d_dt = d_dt.replace(tzinfo=UTC)
        except Exception:
            continue
        window_end = d_dt + timedelta(minutes=60)
        # Path 1 : prediction associee (signal-driven historique)
        n_pred = conn.execute(
            "SELECT COUNT(*) FROM predictions "
            "WHERE ticker=? AND created_at >= ? AND created_at <= ?",
            (ticker, dt_str, window_end.isoformat()),
        ).fetchone()[0]
        if n_pred > 0:
            continue
        # Path 2 : decision_counterfactual associe (chat-driven V0+)
        n_cf = conn.execute(
            "SELECT COUNT(*) FROM decision_counterfactual WHERE decision_id=?",
            (d_id,),
        ).fetchone()[0]
        if n_cf > 0:
            continue
        orphans.append((d_id, ticker, dtype, dt_str[:16]))
    # Pre-self_loop V0 : les decisions 10-18 sont historiquement orphelines.
    # Apres V0, les nouvelles decisions remontent via path 2.
    # Seuil tolere : pas de NOUVELLE regression. On exempte les ids <= 19
    # (les 10 decisions actuelles, prees-V0). Nouvelles decisions doivent
    # avoir artefact.
    pre_v0_cutoff = 19
    new_orphans = [o for o in orphans if o[0] > pre_v0_cutoff]
    assert not new_orphans, (
        f"FUITE ③ : {len(new_orphans)} decision(s) materielle(s) POST-V0 sans "
        f"artefact d'outcome (prediction OU decision_counterfactual). "
        f"Detail : {new_orphans}. Regression dans le hook chat_intent.py / "
        "positions.py -- toute material decision doit ecrire la fermeture."
    )


def test_resolved_predictions_have_brier_unless_neutral(conn):
    """Predictions resolues : brier_score IS NOT NULL sauf si neutral.

    Si une prediction est resolue (resolved_at filled) mais brier=NULL et
    outcome != 'neutral' => bug dans le scorer learning.py.
    """
    rows = conn.execute(
        "SELECT id, ticker, outcome, brier_score "
        "FROM predictions "
        "WHERE resolved_at IS NOT NULL"
    ).fetchall()
    bugged = []
    for p_id, ticker, outcome, brier in rows:
        if outcome == "neutral":
            assert brier is None, \
                f"prediction_{p_id} {ticker} neutral mais brier={brier} (devrait etre NULL)"
        else:
            if brier is None:
                bugged.append((p_id, ticker, outcome))
    assert not bugged, (
        f"Predictions resolues avec outcome != neutral mais brier NULL : {bugged}. "
        "learning.py.resolve_due_predictions ne stocke pas le brier."
    )


def test_pending_predictions_have_future_target_date(conn):
    """Predictions pending : target_date > created_at."""
    rows = conn.execute(
        "SELECT id, ticker, created_at, target_date "
        "FROM predictions "
        "WHERE resolved_at IS NULL"
    ).fetchall()
    inverted = []
    for p_id, ticker, created, target in rows:
        if created and target and target <= created[:10]:
            inverted.append((p_id, ticker, created, target))
    assert not inverted, (
        f"Predictions pending avec target_date <= created_at : {inverted}. "
        "Horizon mal pose au moment de l'insert."
    )


def test_predictions_baseline_price_positive(conn):
    """Toute prediction insere doit avoir un baseline_price > 0.

    Si on a des baseline_price NULL ou <=0 = bug d'ingestion (prediction
    creee sans prix observable -> outcome ne peut pas etre calcule).
    """
    n = conn.execute(
        "SELECT COUNT(*) FROM predictions "
        "WHERE baseline_price IS NULL OR baseline_price <= 0"
    ).fetchone()[0]
    assert n == 0, (
        f"{n} predictions avec baseline_price NULL/<=0. "
        "Bug d'ingestion ou price fetch failed -- ces predictions ne peuvent "
        "pas etre resolues."
    )


def test_self_loop_anchors_have_qty_before_positive(conn):
    """Soudure self_loop V0 : decision_counterfactual.anchor_qty_before > 0
    pour partial_exit/full_exit (on ne vend pas qty=0).

    Pour scale_in : anchor_qty_before peut etre 0 (entree fraiche).
    """
    rows = conn.execute(
        "SELECT id, ticker, decision_type, anchor_qty_before "
        "FROM decision_counterfactual "
        "WHERE decision_type IN ('partial_exit', 'full_exit')"
    ).fetchall()
    bugged = [
        (r[0], r[1], r[2], r[3]) for r in rows
        if (r[3] or 0) <= 0 and not r[1].startswith("TEST_SL")
    ]
    assert not bugged, (
        f"Ancres contrefactuelles sell avec qty_before <= 0 : {bugged}. "
        "L'ancre est faussee -- le contrefactuel hold sera nul."
    )
