"""Contexte book + questions ouvertes pour le LLM d'enrichissement digest.

SPEC digest_enrichment_v2 (29/07/2026) §1-2. Deux briques :

- build_book_context()   : bloc compact généré depuis la DB (theses actives
  jointes aux poids book) à CHAQUE digest. Jamais écrit à la main (L17 :
  un contexte statique dans le prompt drifterait en une semaine).
- load_open_questions()  : lit config/open_questions.yaml (déclaratif,
  édité par Olivier uniquement) — les interrogations vivantes que le
  digest doit faire avancer.

Fail-closed partout (L15) : champ manquant → « — », jamais une valeur
inventée ; yaml illisible → liste vide + warning, jamais un crash du digest.

Câblage (phase 2, dans digest.py au moment de l'enrichissement top_n) :

    from intelligence.book_context import build_book_context, render_open_questions
    prompt = ENRICH_PROMPT.format(
        book_context=build_book_context(),
        open_questions=render_open_questions(),
        payload=signal_payload,
    )
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

_OPEN_QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "config" / "open_questions.yaml"

# Longueur max des champs libres dans une ligne de contexte (compacité :
# ~1 ligne/position, budget total ~800 tokens pour ~30 positions).
_TRUNC = 90


def _short(text: object, limit: int = _TRUNC) -> str:
    """Tronque proprement un champ libre. None/vide -> '—' (fail-closed)."""
    if not text:
        return "—"
    s = str(text).strip().replace("\n", " ")
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _parse_triggers(raw: object) -> str:
    """invalidation_triggers est stocké en JSON-string. Parse safe -> ' · ' join.

    Fail-closed : JSON invalide ou vide -> '—' (on n'invente pas de trigger).
    """
    if not raw:
        return "—"
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(items, list) or not items:
            return "—"
        return _short(" · ".join(str(i) for i in items), _TRUNC * 2)
    except (json.JSONDecodeError, TypeError):
        return "—"


def _fmt_target(value: object, currency: object, legacy: object) -> str:
    """target_full_value+currency (natif M1) prioritaire, fallback legacy
    target_full. Aucun des deux -> '—'."""
    if value:
        cur = str(currency or "").upper()
        return f"{value:g} {cur}".strip()
    if legacy:
        return f"{legacy:g}"
    return "—"


def build_book_context() -> str:
    """Bloc contexte book pour le prompt d'enrichissement. Généré à chaque
    appel depuis theses actives + poids book (sources canoniques L1).

    Format : 1 ligne/position, triée par poids décroissant :
      TICKER | 9.2% | c4 | tgt 3800000 KRW | stop — | var: ... | inval: ...

    Fail-closed : position sans BookLine -> poids '?' ; champ manquant -> '—'.
    Erreur d'accès DB/book -> bloc minimal avec mention d'échec (le digest
    continue, la section BOOK des signaux rendra '—').
    """
    from shared import book as _bk, storage as _storage

    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    try:
        theses = _storage.active_theses() or []
    except Exception as e:
        log.warning(f"book_context: active_theses failed: {e}")
        return f"BOOK [généré {ts}] : INDISPONIBLE (accès theses en échec)"

    try:
        index = _bk.get_book_index()
    except Exception as e:
        log.warning(f"book_context: get_book_index failed: {e}")
        index = {}

    total_eur = 0.0
    weights: dict[str, float] = {}
    for tk, bl in index.items():
        try:
            w = float(bl.weight_market_eur or 0.0)
        except Exception:
            w = 0.0
        weights[tk.upper()] = w
        total_eur += w

    lines: list[tuple[float, str]] = []
    for t in theses:
        ticker = (t.get("ticker") or "?").upper()
        w_eur = weights.get(ticker)
        pct = f"{w_eur / total_eur * 100:.1f}%" if (w_eur and total_eur > 0) else "?%"
        conv = t.get("conviction")
        conv_s = f"c{int(conv)}" if conv else "c—"
        tgt = _fmt_target(t.get("target_full_value"), t.get("target_full_currency"), t.get("target_full"))
        stop = _fmt_target(t.get("stop_value"), t.get("stop_currency"), t.get("stop_price"))
        variant = _short(t.get("variant_perception"))
        inval = _parse_triggers(t.get("invalidation_triggers"))
        line = (
            f"{ticker} | {pct} | {conv_s} | tgt {tgt} | stop {stop} | "
            f"var: {variant} | inval: {inval}"
        )
        lines.append((w_eur or 0.0, line))

    lines.sort(key=lambda x: x[0], reverse=True)
    header = f"BOOK [généré {ts}, {len(lines)} thèses actives, source DB] :"
    return "\n".join([header, *[ln for _, ln in lines]])


def load_open_questions() -> list[dict]:
    """Charge config/open_questions.yaml. Fail-closed : fichier absent ou
    illisible -> [] + warning (le digest tourne sans la section QUESTIONS,
    il n'invente jamais de questions)."""
    try:
        import yaml

        raw = _OPEN_QUESTIONS_PATH.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, list):
            log.warning("book_context: open_questions.yaml n'est pas une liste — ignoré")
            return []
        return [q for q in data if isinstance(q, dict) and q.get("id") and q.get("question")]
    except FileNotFoundError:
        return []
    except Exception as e:
        log.warning(f"book_context: open_questions.yaml illisible: {e}")
        return []


def render_open_questions() -> str:
    """Rend le bloc QUESTIONS OUVERTES pour le prompt. Vide -> ligne explicite
    (état honnête L3 : « aucune question déclarée », pas une section absente)."""
    qs = load_open_questions()
    if not qs:
        return "QUESTIONS OUVERTES : aucune déclarée (config/open_questions.yaml)"
    lines = ["QUESTIONS OUVERTES (config/open_questions.yaml) :"]
    for q in qs:
        marqueurs = q.get("marqueurs") or []
        m = " ; ".join(str(x) for x in marqueurs) if marqueurs else "—"
        tickers = q.get("lignes") or []
        tk = ", ".join(str(x) for x in tickers) if tickers else "—"
        lines.append(f"{q['id']}: {q['question']} [marqueurs: {m}] [lignes: {tk}]")
    return "\n".join(lines)
