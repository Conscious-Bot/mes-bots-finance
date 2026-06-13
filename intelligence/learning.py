"""PredictionLedger: register et resolve des predictions.

Registration: signaux score>=6 + sentiment clair + tickers -> 1 prediction par ticker.
Resolution: apres target_date, fetch current_price, compare a baseline.
- bullish + ticker >=+5% : correct
- bullish + ticker <=-5% : incorrect
- sinon : neutral
credibility_delta (OUTCOME_DELTA) est calcule + stocke sur la ligne pour audit,
mais PLUS applique a sources.credibility (ADR 007: credibilite = autorite unique
Brier via recal mensuel). Voir docs/adrs/007.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from shared import llm, math_helpers, prices, storage


def _mark_signal_pending_llm(signal_id: int) -> None:
    """#93 Composant A2 : marque scoring_status='pending_llm' pour retry quand API up."""
    import sqlite3

    conn = sqlite3.connect(storage._DB_PATH)
    try:
        conn.execute(
            "UPDATE signals SET scoring_status='pending_llm' WHERE id=?",
            (int(signal_id),),
        )
        conn.commit()
    finally:
        conn.close()

log = logging.getLogger(__name__)

HORIZON_DAYS = 30
OUTCOME_THRESHOLD = 0.05

OUTCOME_DELTA = {
    "correct": 0.03,
    "incorrect": -0.05,
    "neutral": 0.0,
}

# Resolution Rules Registry (#110 lock criteria, advisor 04/06/2026)
# Toute methodology_version qui peut etre ecrite OU resolue DOIT etre listee ici
# avec sa regle de resolution figee a la date frozen_at. Cf docs/LESSONS.md L13
# et docs/smoke_test_lock_in_2026-06-04.md.
#
# Le but : pas de regle de resolution silencieusement modifiee qui re-evalue
# retroactivement des predictions deja loggees. Le critere de resolution est
# part du contrat ecrit au moment de l'enregistrement de la prediction.
#
# Ajouter une nouvelle methodology_version = un commit explicite ici. Sans ca,
# register_prediction et resolve_due_predictions refusent.
RESOLUTION_RULES: dict[str, dict[str, object]] = {
    "v0": {
        "threshold": 0.05,
        "frozen_at": "2026-05-26",
        "doc": "pre-V1 legacy, archived per ADR-014",
    },
    "v1": {
        "threshold": 0.05,
        "frozen_at": "2026-05-26",
        "doc": "estimate_probability formula, mono-bucket [0.50-0.72]. J-day 10/06 wrapup",
    },
    "v2": {
        "threshold": 0.05,
        "frozen_at": "2026-05-31",
        "doc": "signal_scorer_v2 base-rate-first LLM 3 etapes. Canonical forward",
    },
    "rule_v1_fallback": {
        "threshold": 0.05,
        "frozen_at": "2026-06-03",
        "doc": "RuleScorer deterministe, FLAG OFF en prod (#94/#105 calibration pending)",
    },
    "rule_v1_shadow": {
        "threshold": 0.05,
        "frozen_at": "2026-06-03",
        "doc": "RuleScorer shadow paired-prediction (#96)",
    },
}


def resolution_rule_for(methodology_version: str) -> dict[str, object] | None:
    """Return the frozen resolution rule for a methodology_version, or None.

    Source de verite unique des regles de resolution. Refus silencieux si la
    methodology_version n'est pas dans le registry = guard #110 (lock criteria).
    """
    return RESOLUTION_RULES.get(methodology_version)

# Phase Solidification P2 — diversification horizon par signal_type
# Rationale: catalyst = event-driven (jours/semaines), narrative = slow-burn (mois),
# opinion/data = standard horizon. Évite cluster temporel de resolutions.
SIGNAL_TYPE_HORIZONS = {
    "catalyst": 14,  # event-driven, short window
    "data": 30,  # macro prints, medium
    "opinion": 30,  # opinion pieces, medium
    "narrative": 60,  # slow-burn themes, long
}


def horizon_for_signal_type(signal_type, impact_magnitude=None):
    """Map signal_type + impact_magnitude to default horizon (days).

    High impact (≥4) narrows the window for faster decisive resolution.
    Returns HORIZON_DAYS (30) as fallback for unknown signal_type.

    Invariants:
    - Output >= 7 (minimum useful horizon)
    - catalyst always shorter than narrative
    - impact_magnitude can only narrow, never extend
    """
    base = SIGNAL_TYPE_HORIZONS.get(signal_type, HORIZON_DAYS)
    if impact_magnitude is not None and impact_magnitude >= 4 and base >= 14:
        return max(7, base // 2)
    return base


CRYPTO_DENY = {
    "BTC",
    "ETH",
    "LINK",
    "SOL",
    "ADA",
    "XRP",
    "DOGE",
    "AVAX",
    "DOT",
    "MATIC",
    "LTC",
    "BCH",
    "TRX",
    "TON",
    "NEAR",
    "ATOM",
    "UNI",
    "AAVE",
    "ARB",
    "OP",
    "SUI",
    "APT",
    "INJ",
    "SEI",
    "FIL",
    "ICP",
    "ETC",
    "XLM",
    "ALGO",
    "BNB",
    "SHIB",
    "PEPE",
    "USDT",
    "USDC",
    "DAI",
}  # stock-only: symboles crypto bruts bloques a la creation (26/05/2026)


def register_prediction(
    signal_id: int,
    ticker: str,
    direction: str,
    *,
    methodology_version: str,
    horizon_days: int | None = None,
    baseline_date: str | None = None,
    signal_type: str | None = None,
    impact_magnitude: float | None = None,
    score: int | None = None,
    probability: float | None = None,
    scoring_trace_json: str | None = None,
    source_metadata_json: str | None = None,
) -> int | None:
    """ADR 014 § Hazard B (#98) : methodology_version est REQUIRED keyword-only.
    Pas de default = pas de silent-mistag. La colonne SQL n'a plus de DEFAULT
    apres migration 0028. Le caller doit specifier 'v1', 'v2', 'rule_v1_*' etc.

    Lock criteria (#110 advisor 04/06) : methodology_version DOIT etre dans
    RESOLUTION_RULES registry. Sinon refus -- pas de prediction silencieusement
    ecrite avec une regle de resolution non documentee.
    """
    if methodology_version not in RESOLUTION_RULES:
        log.error(
            f"register_prediction REFUSE : methodology_version='{methodology_version}' "
            f"absent de RESOLUTION_RULES. Ajouter dans le registry avec rule + frozen_at "
            f"AVANT d'ecrire des predictions. Voir intelligence/learning.py."
        )
        return None
    if horizon_days is None:
        horizon_days = horizon_for_signal_type(signal_type, impact_magnitude)
    if direction not in ("bullish", "bearish"):
        return None
    if baseline_date is None:
        baseline_date = datetime.now(UTC).strftime("%Y-%m-%d")
    actual_date, baseline_price = prices.get_price_on_date(ticker, baseline_date)
    if baseline_price is None or actual_date is None:
        print(f"register_prediction: no baseline price for {ticker} @ {baseline_date}")
        return None
    target = (datetime.fromisoformat(actual_date) + timedelta(days=horizon_days)).strftime("%Y-%m-%d")
    return cast(
        int | None,
        storage.insert_prediction(
            signal_id=signal_id,
            ticker=ticker,
            methodology_version=methodology_version,
            probability_override=probability,
            direction=direction,
            horizon_days=horizon_days,
            baseline_price=baseline_price,
            baseline_date=actual_date,
            target_date=target,
            score=score,
            signal_type=signal_type,
            impact_magnitude=impact_magnitude,
            scoring_trace_json=scoring_trace_json,
            source_metadata_json=source_metadata_json,
        ),
    )


def auto_register_predictions(signals: list[dict[str, Any]], horizon_days: int = HORIZON_DAYS) -> list[int]:
    """Iterate processed signals. Register predictions via SCORER V2 (base-rate-first).

    V2 (signal_scorer_v2) replaces estimate_probability formula (V1, bug mono-bucket
    [0.50-0.72] identifie 30/05). V2 prend chaque signal x ticker, LLM-elicit
    une probabilite directionnelle calibree. Direction = "watch" -> skip (sort
    du ledger, mieux que neutral mou).

    DOCTRINE 'watch' (migration 0060, chantier #150) : ce skip ne concerne que la
    voie AUTO-SCORER ici. 'watch' est CLASSE PREMIERE pour les sentinelles
    POSEES MANUELLEMENT (origin='manual', claim_type IN ('event','data') -- ex.
    S1-S10 sentinelles macro). NE PAS unifier en supprimant 'watch' du schema
    croyant que c'est un dead branch : la voie manuelle l'utilise. Si tu trouves
    ce skip et te dis "ah, watch n'est jamais ecrit, simplifions" -- non. Voir
    docs/CHANTIER_REDEVABILITY_LAYER.md G2 + tests/test_migration_0060_*.

    Filter en entree : on garde score>=6 + sentiment bullish/bearish pour limiter
    le cout LLM (eviter de scorer du noise). V2 lui meme decide ensuite : il
    peut downgrade en watch ou inverser la direction si l'evidence le justifie.
    """
    from intelligence import signal_scorer_v2

    registered: list[int] = []
    for sig in signals:
        score = sig.get("score") or 0
        sentiment = sig.get("sentiment") or ""
        if score < 6 or sentiment not in ("bullish", "bearish"):
            continue
        tickers = sig.get("tickers") or []
        if isinstance(tickers, str):
            try:
                import json

                tickers = json.loads(tickers)
            except Exception:
                tickers = []
        baseline_date = (sig.get("timestamp") or "")[:10] or None
        sig_id = sig.get("id")
        if sig_id is None:
            continue

        # Parse entities once per signal
        sig_entities = []
        try:
            ents_raw = sig.get("entities")
            if ents_raw:
                if isinstance(ents_raw, str):
                    import json as _json
                    sig_entities = _json.loads(ents_raw)
                else:
                    sig_entities = list(ents_raw)
        except Exception:
            sig_entities = []

        for tk in tickers[:5]:
            if tk.upper() in CRYPTO_DENY:
                continue

            # V2 scoring per (signal, ticker) pair
            try:
                v2 = signal_scorer_v2.score_directional_probability(
                    title=sig.get("title") or "",
                    summary=sig.get("summary"),
                    ticker=tk,
                    horizon_days=horizon_days,
                    content=sig.get("content"),
                    entities=sig_entities,
                    source_name=None,  # explicite : source-credibility est une couche apres
                )
            except llm.LLMUnavailableError as _e:
                # #93 Composant A : LLM upstream indisponible. Marque le signal
                # pending_llm pour retry quand l'API revient, et break la boucle
                # tickers (inutile de bruler le batch entier sur API down).
                log.error(
                    f"signal_scorer_v2 LLM unavailable ({_e.reason}) sig={sig_id} "
                    f"ticker={tk} -- marquage pending_llm + abort batch"
                )
                _mark_signal_pending_llm(sig_id)
                # Marque aussi les signaux restants du batch (eviter retry massif)
                for _remaining in signals[signals.index(sig) + 1 :]:
                    _rid = _remaining.get("id")
                    if _rid:
                        _mark_signal_pending_llm(_rid)
                log.info(f"learning: stop batch (LLM down). Predictions enregistrees jusque-la : {len(registered)}")
                return registered
            except Exception as e:
                log.warning(f"signal_scorer_v2 failed for sig={sig_id} ticker={tk}: {e}")
                v2 = None

            if v2 is None:
                log.info(f"V2 returned None for sig={sig_id} ticker={tk} -- skip (no V1 fallback to avoid mono-bucket pollution)")
                continue

            if v2["direction"] == "watch":
                log.info(f"V2 [{tk}] sig={sig_id} -> watch (ev={v2['evidence_strength']}) -- not registered")
                continue

            # #70 + #74 -- capture trace V2 + source metadata pour audit
            # trail full per prediction. Sans ca, impossible de defendre
            # "pourquoi cette proba?" en audit externe.
            import json as _json_t
            trace_json = _json_t.dumps(v2, ensure_ascii=False, sort_keys=True)
            src_meta_json = _json_t.dumps({
                "title": (sig.get("title") or "")[:200],
                "source_name": sig.get("source_name"),
                "gmail_id": sig.get("gmail_id"),
                "credibility_at_creation": sig.get("credibility"),
                "score_at_creation": score,
                "sentiment_at_creation": sentiment,
                "signal_timestamp": sig.get("timestamp"),
            }, ensure_ascii=False, sort_keys=True)

            pid = register_prediction(
                signal_id=sig_id,
                ticker=tk,
                direction=v2["direction"],
                # ADR 014 hazard B : V2 scorer path -> tag 'v2' explicit.
                methodology_version="v2",
                horizon_days=horizon_days if horizon_days != HORIZON_DAYS else None,
                baseline_date=baseline_date,
                signal_type=sig.get("signal_type"),
                impact_magnitude=sig.get("impact_magnitude"),
                score=score,
                probability=v2["probability"],
                scoring_trace_json=trace_json,
                source_metadata_json=src_meta_json,
            )
            if pid:
                registered.append(pid)
    return registered


def resolve_due_predictions(limit: int = 50) -> dict[str, Any]:
    """Find predictions past target_date, compute outcomes, update credibility."""
    due = storage.get_due_predictions(limit=limit)
    if not due:
        return {"resolved": 0, "details": []}
    results: dict[str, Any] = {"resolved": 0, "details": [], "skipped_event": 0}
    for pred in due:
        # Migration 0060 (chantier #150 G2) : event/data claims se resolvent sur
        # resolution_source + le fait externe, JAMAIS sur baseline_price. La
        # resolution auto prix-basee ne s'applique qu'aux claims 'price'. Pour
        # event/data, l'humain (ou un futur cron event-aware) lit la source et
        # appelle resolve_event_prediction(pred_id, outcome). Skip silent ici =
        # contamination prix-comme-preuve evitee.
        ct = pred.get("claim_type", "price")
        if ct in ("event", "data"):
            results["skipped_event"] += 1
            log.info(
                f"resolve_due_predictions SKIP event-type pred_id={pred.get('id')} "
                f"ticker={pred.get('ticker') or '<macro>'} claim_type={ct} "
                f"-- resolution manuelle ou cron dedie sur resolution_source='{pred.get('resolution_source')}'"
            )
            continue
        ticker = pred["ticker"]
        baseline_price = pred["baseline_price"]
        direction = pred["direction"]
        # Lock criteria (#110) : resolution rule lookup par methodology_version.
        # Si la methodology_version n'est pas dans le registry -> defensive skip,
        # on log et on ne resoud PAS (au lieu de subtilement appliquer OUTCOME_THRESHOLD
        # global qui pourrait ne pas etre la regle ecrite a la creation).
        mv = pred.get("methodology_version")
        rule = resolution_rule_for(mv) if mv else None
        if rule is None:
            log.warning(
                f"resolve_due_predictions SKIP pred_id={pred.get('id')} ticker={ticker} "
                f"methodology_version='{mv}' absent de RESOLUTION_RULES. "
                f"Pour resoudre, ajouter au registry retroactivement avec la regle d'epoque."
            )
            continue
        threshold_raw = rule.get("threshold", OUTCOME_THRESHOLD)
        threshold = float(threshold_raw)  # type: ignore[arg-type]  # registry values are int/float
        # Native-currency CORRECT here (not legacy).
        # This computes a RATIO (return_pct) which is FX-invariant — as long as
        # target_close and baseline_price are in same currency, the ratio holds.
        # baseline_price was set at prediction creation via same get_current_price
        # native path, so both sides match. Migrating to USD/EUR adds FX layer for
        # no math gain and breaks the symmetry. DO NOT migrate.
        # Ground-truth 31/05/2026 : utiliser close du target_date exact (pas
        # current price quand cron tourne). Avant correction : 3/6 historiques
        # mal resolus (NVDA 50, AVGO 51, MSFT 53 -> re-resolus en DB).
        target_close = prices.get_close_on(ticker, pred["target_date"])
        if target_close is None or target_close != target_close:  # None ou NaN
            continue
        return_pct = (target_close - baseline_price) / baseline_price
        if direction == "bullish":
            if return_pct >= threshold:
                outcome = "correct"
            elif return_pct <= -threshold:
                outcome = "incorrect"
            else:
                outcome = "neutral"
        else:
            if return_pct <= -threshold:
                outcome = "correct"
            elif return_pct >= threshold:
                outcome = "incorrect"
            else:
                outcome = "neutral"
        delta = OUTCOME_DELTA[outcome]
        sig = storage.get_signal(pred["signal_id"]) if pred.get("signal_id") else None
        # ADR 007: credibilite = autorite unique Brier (recal mensuel). On n'applique
        # plus le delta categoriel incremental; delta reste calcule + stocke (audit).
        new_cred = None
        prob = pred.get("probability_at_creation")
        brier_score = math_helpers.brier_for(prob, outcome)
        storage.resolve_prediction_row(
            prediction_id=pred["id"],
            final_price=target_close,
            return_pct=return_pct,
            outcome=outcome,
            credibility_delta=delta,
            brier_score=brier_score,
        )
        results["resolved"] += 1
        results["details"].append(
            {
                "pred_id": pred["id"],
                "ticker": ticker,
                "direction": direction,
                "baseline": baseline_price,
                "final": target_close,
                "return_pct": return_pct,
                "outcome": outcome,
                "delta": delta,
                "source_name": sig.get("source_name") if sig else None,
                "new_cred": new_cred,
            }
        )
    return results


def format_resolve_report(results: dict[str, Any]) -> str:
    if results["resolved"] == 0:
        return "Aucune prediction a resoudre (target_date pas encore passe)."
    lines = [f"Resolution: {results['resolved']} predictions"]
    counts = {"correct": 0, "incorrect": 0, "neutral": 0}
    for d in results["details"]:
        counts[d["outcome"]] += 1
        src = (d.get("source_name") or "?")[:20]
        lines.append(
            f"  #{d['pred_id']} {d['ticker']} {d['direction'][:4]} [{src}]: "
            f"${d['baseline']:.2f} -> ${d['final']:.2f} ({d['return_pct']:+.1%}) "
            f"-> {d['outcome'].upper()} (cred {d['delta']:+.2f})"
        )
    lines.append(f"Summary: {counts['correct']} ok / {counts['incorrect']} ko / {counts['neutral']} neutral")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "resolve":
        results = resolve_due_predictions()
        print(format_resolve_report(results))
    else:
        print("Usage: python -m intelligence.learning resolve")
        print("Running resolve anyway...")
        results = resolve_due_predictions()
        print(format_resolve_report(results))
