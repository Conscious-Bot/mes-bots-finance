"""Sprint 22 — Decision anniversary review.

Daily : check si des decisions ont un anniversaire J+30/J+90/J+180 today.
Pour chacune, surface un prompt de reflexion :
  'Il y a X jours, tu as fait Y pour raison Z. Outcome actuel : W.
   Qu'en penses-tu maintenant ?'

Ces reflexions deviennent des chat_extracted_signals (kind=reflection_prompt)
qui nourrissent le user_profile et le chat context.

Fait que le bot devienne une 'memoire-miroir' qui pousse l'user a re-examiner
ses propres decisions au fil du temps.
"""

from __future__ import annotations

import logging

from shared import notify, storage

log = logging.getLogger(__name__)


_ANNIVERSARIES = [30, 60, 90, 180, 365]


def _fetch_anniversary_decisions() -> list[dict]:
    """Returns decisions hitting an anniversary today (within +/- 1 day window)."""
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT id, created_at, ticker, decision_type, reasoning, "
                "resolved_30d_at, return_30d_pct, "
                "CAST(julianday('now') - julianday(created_at) AS INTEGER) AS age_days "
                "FROM decisions "
                "WHERE created_at IS NOT NULL "
                "ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        cols = ["id", "created_at", "ticker", "decision_type", "reasoning",
                "resolved_30d_at", "return_30d_pct", "age_days"]
        decisions = [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception as e:
        log.warning(f"fetch_anniversary_decisions failed: {e}")
        return []
    # Filter to anniversary windows
    out = []
    for d in decisions:
        age = d.get("age_days") or 0
        for ann in _ANNIVERSARIES:
            if abs(age - ann) <= 1:  # +/- 1 day window
                d["anniversary_days"] = ann
                out.append(d)
                break
    return out


def _format_anniversary_message(d: dict) -> str:
    ann = d.get("anniversary_days", 0)
    tk = d.get("ticker", "?")
    dtype = d.get("decision_type", "?")
    reasoning = (d.get("reasoning") or "")[:180]
    ret = d.get("return_30d_pct")
    ret_str = ""
    if ret is not None:
        ret_str = f" Return J+30 actuel : {ret:+.1f}%."
    elif ann >= 30:
        ret_str = " Pas encore resolved J+30."
    return (
        f"🔄 ANNIVERSAIRE J+{ann} — decision_{d['id']} {tk} {dtype}\n\n"
        f"Il y a {ann} jours, tu as decide :\n  \"{reasoning}\"\n"
        f"{ret_str}\n\n"
        f"Reflechir : la these tient-elle toujours ? Tu reprendrais la meme decision aujourd'hui ?"
    )


def check_today() -> dict:
    """Run daily check + push Telegram + persist as chat_extracted_signal."""
    anniversaries = _fetch_anniversary_decisions()
    if not anniversaries:
        return {"n_anniversaries": 0, "notified": 0}

    # Digest UNIQUE (cure bruit 30/06 : anniversaires en rafale = dérangeant).
    # Un seul Telegram groupé au lieu d'un message par décision. La persistance
    # chat_signal reste par-décision (DB, aucun bruit user-facing).
    notified = 0
    try:
        if len(anniversaries) == 1:
            _digest = _format_anniversary_message(anniversaries[0])
        else:
            _rows = []
            for d in anniversaries:
                _r = d.get("return_30d_pct")
                _rs = f" · J+30 {_r:+.1f}%" if _r is not None else ""
                _rows.append(
                    f"• J+{d['anniversary_days']} decision_{d['id']} {d['ticker']} "
                    f"{d.get('decision_type', '?')}{_rs}"
                )
            _digest = (
                f"🔄 {len(anniversaries)} anniversaires de décision aujourd'hui :\n"
                + "\n".join(_rows)
                + "\n\nRéfléchir : ces thèses tiennent-elles toujours ?"
            )
        notify.send_text(_digest)
        notified = 1
    except Exception as e:
        log.warning(f"anniversary digest notify failed: {e}")

    for d in anniversaries:
        # Persist as chat_extracted_signal so it nourishes user_profile
        # next refresh + chat context
        try:
            storage.insert_chat_signal(
                chat_message_id=None,
                kind="reflection_prompt",
                ticker=d.get("ticker"),
                valence=0,
                confidence=80,
                evidence_quote=(
                    f"J+{d['anniversary_days']} review of decision_{d['id']} "
                    f"{d['ticker']} {d['decision_type']}: {(d.get('reasoning') or '')[:200]}"
                ),
                note=(
                    f"Anniversary J+{d['anniversary_days']} de decision_{d['id']}. "
                    f"Return J+30 : {d.get('return_30d_pct', 'pending')}. "
                    "Prompt reflexion user pour ne pas oublier le rationale historique."
                ),
            )
        except Exception as e:
            log.warning(f"anniversary persist failed: {e}")

    log.info(f"decision_anniversary : {len(anniversaries)} anniversaires, {notified} notifies")
    return {
        "n_anniversaries": len(anniversaries),
        "notified": notified,
        "details": [
            {
                "decision_id": d["id"],
                "ticker": d["ticker"],
                "ann_days": d["anniversary_days"],
            }
            for d in anniversaries
        ],
    }
