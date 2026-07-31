"""SYNTHÈSE HEBDO « style live » (Format B) — cf docs/templates/weekly_synthesis_prompt.md.

Cadence : cron APScheduler dimanche 18:00 Europe/Paris sur la VM (source).
Payload = signals scorés 7j + reactions (si dispo) + events + book_context + open_questions.
Guards : T13 (réutilisé de digest) + provenance + fail-closed L15.

SPEC : mémoire `spec-weekly-synthesis-lecture-du-jour`. Le contrat de style (guide de
voix §0) vit dans le template et est injecté VERBATIM dans le prompt.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from intelligence.book_context import build_book_context
from intelligence.digest import _t13_guard
from shared import llm, storage

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "docs" / "templates" / "weekly_synthesis_prompt.md"
_OPEN_Q_PATH = Path(__file__).resolve().parent.parent / "config" / "open_questions.yaml"

# Chiffre "significatif" : ≥2 chiffres, ou décimal, ou avec %/$/€/Md/M — hors dates/ids.
_SIGNIFICANT_NUM = re.compile(r"(?<![#\w])(?:[$€]|\b)\d[\d\s.,]*\s*(?:%|Md|M\$|Md\$|Md€|bps|x)?\b")
_PROVENANCE = re.compile(r"\[#\d+\]|\[print\s+[A-Z0-9.]+", re.IGNORECASE)


# ─── Guards ──────────────────────────────────────────────────────────────────

def _provenance_guard(text: str) -> str:
    """Tout chiffre significatif doit porter [#id] ou [print TICKER]. Sinon WARN VISIBLE
    en fin de texte (jamais de censure silencieuse — cf spec §3)."""
    flagged: list[str] = []
    for line in text.splitlines():
        low = line.strip()
        if not low or low.startswith(("#", ">", "|", "-", "Perspective")):
            continue
        if _SIGNIFICANT_NUM.search(low) and not _PROVENANCE.search(low):
            flagged.append(low[:90])
    if not flagged:
        return text
    warn = "\n\n⚠ PROVENANCE — chiffre(s) sans source (à vérifier) :\n" + "\n".join(
        f"  · {f}" for f in flagged[:8]
    )
    return text + warn


# ─── Payload ─────────────────────────────────────────────────────────────────

def _signals_7d(cx, days: int = 7, min_score: float = 0.0) -> list[dict]:
    """Signaux scorés des N derniers jours (tous, pas seulement EDGAR)."""
    rows = cx.execute(
        """SELECT id, timestamp, title, summary, score, entities, narratives
           FROM signals
           WHERE timestamp >= datetime('now', ?) AND COALESCE(score, 0) >= ?
           ORDER BY COALESCE(score, 0) DESC""",
        (f"-{days} days", min_score),
    ).fetchall()
    return [dict(r) for r in rows]


def _upcoming_events(cx, horizon_days: int = 14) -> list[dict]:
    rows = cx.execute(
        """SELECT event_type, ticker, date, description FROM events
           WHERE date >= date('now') AND date <= date('now', ?)
           ORDER BY date""",
        (f"+{horizon_days} days",),
    ).fetchall()
    return [dict(r) for r in rows]


def _reactions_7d(cx, days: int = 7) -> list[dict]:
    """Table reactions optionnelle (non déployée au 31/07 → fail-soft)."""
    try:
        cols = [r[1] for r in cx.execute("PRAGMA table_info(reactions)")]
        if not cols:
            return []
        rows = cx.execute(
            "SELECT * FROM reactions WHERE created_at >= datetime('now', ?) ORDER BY created_at DESC",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def build_weekly_payload(days: int = 7) -> dict[str, Any]:
    """Assemble le payload — RIEN d'autre que ces sources (cf spec §2)."""
    open_questions = _OPEN_Q_PATH.read_text(encoding="utf-8") if _OPEN_Q_PATH.exists() else ""
    with storage.db() as cx:
        cx.row_factory = __import__("sqlite3").Row
        signals = _signals_7d(cx, days)
        events = _upcoming_events(cx)
        reactions = _reactions_7d(cx, days)
    return {
        "signals": signals,
        "reactions": reactions,
        "events": events,
        "book_context": build_book_context(),
        "open_questions": open_questions,
        "n_material": sum(1 for s in signals if (s.get("score") or 0) >= 3),
    }


# ─── Render ──────────────────────────────────────────────────────────────────

def _build_prompt(payload: dict[str, Any]) -> str:
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    sig_lines = "\n".join(
        f"[#{s['id']}] score={s.get('score')} {s.get('title', '')[:120]} — {s.get('summary', '')[:200]}"
        for s in payload["signals"][:40]
    ) or "(aucun signal matériel cette semaine)"
    ev_lines = "\n".join(
        f"- {e['date']} : {e.get('ticker') or ''} {e['description']}" for e in payload["events"]
    ) or "(aucun)"
    return (
        f"{template}\n\n===== PAYLOAD (tu ne SAIS rien hors ceci) =====\n\n"
        f"## SIGNAUX 7J (scorés)\n{sig_lines}\n\n"
        f"## RENDEZ-VOUS (events déterministes)\n{ev_lines}\n\n"
        f"## BOOK CONTEXT\n{payload['book_context']}\n\n"
        f"## QUESTIONS OUVERTES\n{payload['open_questions']}\n\n"
        f"[n_material={payload['n_material']} — si faible, applique le no-padding L3 : sections 2-4 courtes, TLDR dit « semaine mince ».]\n"
        "\n===== ÉCRIS LA SYNTHÈSE (respecte le guide de voix §0 verbatim). ====="
    )


def render_weekly(payload: dict[str, Any], *, llm_call: Callable[..., str] | None = None) -> str:
    """payload -> prompt -> LLM -> _t13_guard + _provenance_guard. Fail-closed L15 si vide."""
    if not payload or not payload.get("book_context"):
        return "SYNTHÈSE HEBDO INDISPONIBLE (incident) — payload vide / book_context en échec."
    call = llm_call or (lambda p: llm.call(p, tier="enrich", max_tokens=2800))
    try:
        text = call(_build_prompt(payload))
    except Exception as e:
        return f"SYNTHÈSE HEBDO INDISPONIBLE (incident) — {type(e).__name__}: {str(e)[:160]}"
    text = (text or "").strip()
    if not text:
        return "SYNTHÈSE HEBDO INDISPONIBLE (incident) — LLM a renvoyé une réponse vide."
    return _provenance_guard(_t13_guard(text))


def generate_weekly_synthesis(days: int = 7) -> str:
    """Entry-point (appelé par le cron VM). Retourne le texte ; le transport (mail/Telegram)
    est au caller, comme le digest."""
    return render_weekly(build_weekly_payload(days))
