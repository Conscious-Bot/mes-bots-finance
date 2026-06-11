"""Writers pour la table thesis_predictions (SPEC_THESIS_ALPHA_RESOLVER pièces 3).

Trois primitives :
1. insert_thesis_pose(...) — fail-closed L15 sur convert None / pas de variant
                              view, UNIQUE handling, log skip
2. get_due_thesis_predictions(today) — récupère paris arrivés à maturité non résolus
3. update_thesis_resolve_fields(id, ...) — UN seul UPDATE atomique (contrat
                                            critique : trigger 2 mord si splitté)

Décisions tranchées :
- Gate no_bet à la pose (décision A 11/06) : |delta| < ε_delta → skip insert
  + log event 'no_variant_view'. Table = uniquement vrais paris vs consensus.
  'no_bet' reste enum dans CHECK migration (code mort inoffensif, garde option
  future sans nouvelle migration).
- Mapping classify_direction → DB :
    'correct'   → direction_correct=1, exclude_reason=NULL
    'incorrect' → direction_correct=0, exclude_reason=NULL
    'neutral'   → direction_correct=NULL, exclude_reason='neutral'
    None        → ne PAS résoudre (alpha incalculable, §4 retry/abandon)
- 'no_bet' au resolve : jamais (gate à la pose). Si jamais on bascule en
  mode B futur, ce mapping handle déjà.

Doctrine L17 : passerelle DB unique = shared.storage.db() context manager.
Auto-commit à la sortie du with bloc. Pas de sqlite3.connect direct.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

# Re-export L17 : on importe IntegrityError via storage (passerelle unique)
# au lieu de sqlite3 direct → test_no_new_sqlite3_bypass passe.
from shared.storage import IntegrityError, db, log_event

log = logging.getLogger(__name__)

# ε_delta par défaut : aligné classify_direction (1.0 = 1% native).
# Override possible par config future si besoin.
DEFAULT_EPSILON_DELTA_PCT = 1.0


def insert_thesis_pose(
    *,
    ticker: str,
    asof: date,
    asof_price_native: float,
    native_currency: str,
    pt_consensus_raw: float,
    pt_consensus_currency: str,
    pt_native_asof: float,
    fx_at_asof: float,
    your_target_native: float,
    your_delta_native_pct: float,
    thesis_summary: str,
    resolve_due_date: date,
    confidence: float | None = None,
    source: str | None = None,
    notes: str | None = None,
    epsilon_delta_pct: float = DEFAULT_EPSILON_DELTA_PCT,
) -> int | None:
    """Insert une pose dans thesis_predictions, fail-closed sur 3 cas.

    Returns:
        int : id de la ligne insérée si succès
        None : si skip (no variant view / dedup UNIQUE) ; raison loggée

    Fail-closed cas 1 — |your_delta| < ε_delta (gate no_bet) :
        Décision A 11/06 : pas de variant view = pas un pari à scorer.
        Skip insert + log event 'no_variant_view_at_pose'.

    Fail-closed cas 2 — UNIQUE(ticker, asof, your_target_native) collision :
        Pose déjà existante → log event 'pose_duplicate' et return None.
        Pas un crash — le caller peut retry avec asof différent ou
        new target.

    Le caller est responsable d'avoir :
    - converti pt_consensus_raw → pt_native_asof via convert_consensus_pt_to_native
    - calculé your_delta_native_pct via compute_your_delta_native_pct
    - posé asof_price_native cohérent avec asof (prix observé à la date)
    """
    # Gate 1 : no_bet (décision A)
    if abs(your_delta_native_pct) < epsilon_delta_pct:
        log.info(
            f"thesis_pose skip 'no_variant_view' : ticker={ticker} asof={asof} "
            f"your_delta={your_delta_native_pct:+.2f}% < ε={epsilon_delta_pct}%"
        )
        log_event(
            "no_variant_view_at_pose",
            {
                "ticker": ticker,
                "asof": str(asof),
                "your_delta_native_pct": your_delta_native_pct,
                "epsilon_delta_pct": epsilon_delta_pct,
                "thesis_summary": thesis_summary,
            },
        )
        return None

    new_id: int | None = None
    dupe_err: str | None = None
    # Passerelle L17 : context manager auto-commit + auto-close
    with db() as cx:
        try:
            cur = cx.execute(
                """
                INSERT INTO thesis_predictions (
                    ticker, asof, asof_price_native, native_currency,
                    pt_consensus_raw, pt_consensus_currency, pt_native_asof, fx_at_asof,
                    your_target_native, your_delta_native_pct, confidence, thesis_summary,
                    resolve_due_date, source, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker, str(asof), asof_price_native, native_currency,
                    pt_consensus_raw, pt_consensus_currency, pt_native_asof, fx_at_asof,
                    your_target_native, your_delta_native_pct, confidence, thesis_summary,
                    str(resolve_due_date), source, notes,
                ),
            )
            new_id = cur.lastrowid
        except IntegrityError as e:
            # UNIQUE(ticker, asof, your_target_native) collision = duplicate
            dupe_err = str(e)

    # Hors du with : connexion fermée, locks libérés → log_event safe
    if dupe_err is not None:
        log.warning(
            f"thesis_pose UNIQUE collision (déjà posé) : ticker={ticker} "
            f"asof={asof} target={your_target_native} — skip. err={dupe_err}"
        )
        log_event(
            "thesis_pose_duplicate",
            {
                "ticker": ticker,
                "asof": str(asof),
                "your_target_native": your_target_native,
                "error": dupe_err,
            },
        )
        return None

    log.info(f"thesis_pose inserted id={new_id} ticker={ticker} asof={asof} "
             f"delta={your_delta_native_pct:+.1f}% due={resolve_due_date}")
    return new_id


def get_due_thesis_predictions(
    today: date | None = None,
    limit: int = 100,
) -> list[dict]:
    """Récupère les paris dont la résolution est due (resolve_due_date ≤ today)
    et qui ne sont pas encore résolus (resolved_at IS NULL).

    Index dédié idx_thesis_predictions_due fait du WHERE rapide même sur
    grosse table.

    Args:
        today : date de référence (default = today UTC)
        limit : max rows pour éviter une avalanche au resolver

    Returns:
        list[dict] des poses à résoudre, ordonnées par resolve_due_date ASC
        (les plus anciens d'abord).
    """
    if today is None:
        today = datetime.now(UTC).date()

    with db() as cx:
        rows = cx.execute(
            """
            SELECT *
              FROM thesis_predictions
             WHERE resolve_due_date <= ?
               AND resolved_at IS NULL
          ORDER BY resolve_due_date ASC, id ASC
             LIMIT ?
            """,
            (str(today), limit),
        ).fetchall()
        return [dict(r) for r in rows]


def update_thesis_resolve_fields(
    *,
    prediction_id: int,
    resolve_price_native: float,
    alpha_realized_pct: float,
    classify_result: str,
    magnitude_score: float | None = None,
) -> bool:
    """Update atomique des 6 resolve cols (contrat trigger 2).

    UN seul UPDATE statement avec resolved_at + tous les autres resolve cols
    d'un coup. Si splitté en 2 statements, le 2e post-resolved_at se fait
    mordre par trigger 2 (WHEN OLD.resolved_at IS NOT NULL).

    Args:
        prediction_id : id de la ligne thesis_predictions à résoudre
        resolve_price_native : prix observé à resolve_due_date
        alpha_realized_pct : compute_alpha_realized_pct(resolve_price, pt_native_asof, asof_price)
        classify_result : output de classify_direction (correct/incorrect/neutral/no_bet/None)
        magnitude_score : Brier-type score si confidence posée, None sinon

    Returns:
        True si update réussi (1 ligne touchée)
        False si pred inexistante ou déjà résolue (trigger 2 mord)

    Mapping classify → (direction_correct, exclude_reason) :
        'correct'   → (1, NULL)
        'incorrect' → (0, NULL)
        'neutral'   → (NULL, 'neutral')
        'no_bet'    → (NULL, 'no_bet')  # ne devrait jamais arriver (gate à la pose)
        None        → DOIT être traité avant par caller (ne PAS appeler ce writer)
    """
    if classify_result is None:
        raise ValueError(
            "update_thesis_resolve_fields: classify_result=None signifie alpha "
            "incalculable. Ne PAS résoudre — caller doit retry (§4 SPEC) ou abandon."
        )

    direction_correct, exclude_reason = _map_classify_to_db(classify_result)

    rowcount = 0
    trigger_mord = False
    with db() as cx:
        try:
            cur = cx.execute(
                """
                UPDATE thesis_predictions SET
                    resolved_at = ?,
                    resolve_price_native = ?,
                    alpha_realized_pct = ?,
                    direction_correct = ?,
                    magnitude_score = ?,
                    exclude_reason = ?,
                    resolution_status = 'resolved'
                  WHERE id = ?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    resolve_price_native,
                    alpha_realized_pct,
                    direction_correct,
                    magnitude_score,
                    exclude_reason,
                    prediction_id,
                ),
            )
            rowcount = cur.rowcount
        except IntegrityError:
            # Trigger 2 mord si déjà résolu
            trigger_mord = True

    # Hors du with : log après release des locks
    if trigger_mord:
        log.error(
            f"update_thesis_resolve_fields : pred_id={prediction_id} déjà résolu "
            f"(trigger 2 mord)."
        )
        return False
    if rowcount == 0:
        log.warning(f"update_thesis_resolve_fields : pred_id={prediction_id} introuvable")
        return False
    log.info(
        f"thesis_resolve id={prediction_id} classify={classify_result} "
        f"alpha={alpha_realized_pct:+.2f}% direction_correct={direction_correct}"
    )
    return True


def mark_thesis_prediction_abandoned(
    *,
    prediction_id: int,
    reason: str = "price_unavailable",
) -> bool:
    """Marque un pari comme TERMINAL-abandonné (price unavailable post-grace,
    cf SPEC §4.2).

    La ligne sort du pool `get_due` (resolved_at set) ET du pool scoring
    (direction_correct=NULL, magnitude_score=NULL → exclus par construction
    de l'agrégateur qui filtre sur ces colonnes IS NOT NULL, cf SPEC §4.1
    axe lifecycle vs axe scoring).

    UN seul UPDATE atomique (contrat trigger 2) avec :
    - resolved_at = now (lifecycle terminal, sort de get_due)
    - resolution_status = 'abandoned' (axe lifecycle SPEC §4.1)
    - resolve_price_native = NULL (jamais observé)
    - alpha_realized_pct = NULL (jamais calculé)
    - direction_correct = NULL (auto-exclu scoring)
    - magnitude_score = NULL (auto-exclu Brier)
    - exclude_reason = NULL (axe scoring distinct — pas neutral/no_bet,
      c'est lifecycle pas scoring)

    Args:
        prediction_id : id de la ligne à abandonner
        reason : raison textuelle (loggée dans bot_events seulement, pas
            en DB — la doctrine SPEC §4.1 est que resolution_status='abandoned'
            suffit côté schéma, le contexte vit dans bot_events via log_event)

    Returns:
        True si update réussi (1 ligne touchée)
        False si pred introuvable OU déjà résolue (trigger 2 mord)

    Distingué de update_thesis_resolve_fields :
    - update_resolve : alpha calculé → resolution_status='resolved' +
      direction_correct in {0,1} OU exclude_reason in {'neutral','no_bet'}
    - mark_abandoned : alpha non-calculable → resolution_status='abandoned',
      tous les autres resolve cols NULL. Lifecycle distinct de scoring.
    """
    rowcount = 0
    trigger_mord = False
    with db() as cx:
        try:
            cur = cx.execute(
                """
                UPDATE thesis_predictions SET
                    resolved_at = ?,
                    resolve_price_native = NULL,
                    alpha_realized_pct = NULL,
                    direction_correct = NULL,
                    magnitude_score = NULL,
                    exclude_reason = NULL,
                    resolution_status = 'abandoned'
                  WHERE id = ?
                """,
                (datetime.now(UTC).isoformat(), prediction_id),
            )
            rowcount = cur.rowcount
        except IntegrityError:
            # Trigger 2 mord si déjà résolu (l'abandon ne re-résoud pas)
            trigger_mord = True

    # Hors du with : log après release des locks
    if trigger_mord:
        log.error(
            f"mark_thesis_prediction_abandoned : pred_id={prediction_id} déjà résolu "
            f"(trigger 2 mord). L'abandon n'overwrite pas une résolution normale."
        )
        return False
    if rowcount == 0:
        log.warning(f"mark_thesis_prediction_abandoned : pred_id={prediction_id} introuvable")
        return False
    log.info(f"thesis_abandoned id={prediction_id} reason={reason}")
    log_event(
        "thesis_resolve_abandoned",
        {"prediction_id": prediction_id, "reason": reason},
    )
    return True


def _map_classify_to_db(
    classify_result: str,
) -> tuple[int | None, str | None]:
    """Mapping classify_direction → colonnes DB.

    Returns:
        (direction_correct INTEGER | None, exclude_reason TEXT | None)

    Décision A 11/06 : 'no_bet' ne devrait jamais arriver ici (gate à la pose),
    mais le mapping est défensif au cas où.
    """
    mapping = {
        "correct": (1, None),
        "incorrect": (0, None),
        "neutral": (None, "neutral"),
        "no_bet": (None, "no_bet"),  # défensif (gate amont devrait l'empêcher)
    }
    if classify_result not in mapping:
        raise ValueError(
            f"_map_classify_to_db : classify_result={classify_result!r} hors enum "
            f"attendu {set(mapping)}"
        )
    return mapping[classify_result]
