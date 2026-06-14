"""research_brief — Spec #152 / chantier #150 G3.

Fournit a Olivier de la matiere factuelle structuree (faits chiffres + consensus
+ news + cadre causal) sans franchir la barriere #150 : ZERO jugement, ZERO
direction ("achete", "vends", "tu devrais"), ZERO ranking, ZERO probabilite
de bot.

Architecture :
    /research <ticker|theme>
        -> bot/handlers/research.py:cmd_research
        -> intelligence/research_brief.py:fetch(target, user_id)
            -> backend Bigdata.com (if BIGDATA_API_KEY set)
            -> backend stub (placeholder if no key)
            -> format markdown per SPEC §4
            -> log to research_brief_log

Backends pluggables : Bigdata-real si key, stub si pas (clean separation
permet de wirer la clé sans toucher le handler).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime

log = logging.getLogger("bot")

# ZERO ANCHORING : ces patterns sont INTERDITS dans toute response generee.
# Si une response matche un de ces patterns, on ABORT + log warning.
_VERDICT_PATTERNS = [
    re.compile(r"\bachete[rsz]?\b", re.IGNORECASE),
    re.compile(r"\bvend[rsz]?\b", re.IGNORECASE),
    re.compile(r"\brecommand[eé]\b", re.IGNORECASE),
    re.compile(r"\btu devrais\b", re.IGNORECASE),
    re.compile(r"\bil faut (acheter|vendre|prendre)\b", re.IGNORECASE),
    re.compile(r"\bprobable que (le )?(titre|stock|action)\b", re.IGNORECASE),
    re.compile(r"\boverweight\b|\bunderweight\b", re.IGNORECASE),
    re.compile(r"\b(probabilite|probabilité|odds) (de|que|of) \d", re.IGNORECASE),
]


class _BigdataBackend:
    """Backend Bigdata.com via bigdata-client SDK (officiel)."""

    def __init__(self, api_key: str):
        from bigdata_client import Bigdata
        self.client = Bigdata(api_key=api_key)

    def search(self, query_text: str, n_chunks: int = 10) -> list[dict]:
        """Run focused search. Returns list of dict {headline, date, source, text}."""
        from bigdata_client.daterange import RollingDateRange
        from bigdata_client.query import Similarity

        try:
            q = Similarity(query_text)
            s = self.client.search.new(query=q, date_range=RollingDateRange.LAST_THIRTY_DAYS)
            docs = list(s.run(limit=n_chunks))
            return [
                {
                    "headline": getattr(d, "headline", "?"),
                    "date": str(getattr(d, "timestamp", "?"))[:10],
                    "source": getattr(getattr(d, "source", None), "name", "?"),
                    "text": "\n".join(c.text for c in getattr(d, "chunks", [])[:2]),
                }
                for d in docs
            ]
        except Exception as e:
            log.warning(f"bigdata search err: {e}")
            return []


class _StubBackend:
    """Backend stub : placeholder structuree quand BIGDATA_API_KEY absent.

    Indique explicitement que les sources ne sont pas wirees. NE INVENTE PAS
    de chiffres : retourne un message clair "wire pending" plutot que de fake
    des donnees (doctrine fail-closed L15 + retrospectif_plafonne L13).
    """

    def search(self, query_text: str, n_chunks: int = 10) -> list[dict]:
        return [{
            "headline": "BIGDATA_API_KEY not configured",
            "date": datetime.now(UTC).date().isoformat(),
            "source": "stub",
            "text": (
                f"Sources Bigdata.com non wired. Set BIGDATA_API_KEY env var "
                f"pour fetch real data. Query was: '{query_text[:100]}'"
            ),
        }]


def _backend() -> _BigdataBackend | _StubBackend:
    """Resolve backend : Bigdata if key, else stub. Fail-soft."""
    key = os.environ.get("BIGDATA_API_KEY")
    if not key:
        return _StubBackend()
    try:
        return _BigdataBackend(api_key=key)
    except ImportError:
        log.warning("bigdata-client SDK not installed, falling back to stub")
        return _StubBackend()


def _format_markdown(target: str, facts: list[dict], consensus: list[dict], news: list[dict]) -> str:
    """Format per SPEC §4. ZERO jugement, ZERO direction."""
    asof = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def _bullets(items: list[dict], limit: int = 5) -> str:
        if not items:
            return "_(aucun resultat sur cette requete)_"
        out = []
        for item in items[:limit]:
            date = item.get("date", "?")
            head = item.get("headline", "?")[:120]
            src = item.get("source", "?")
            out.append(f"• [{date}] {head} — {src}")
        return "\n".join(out)

    parts = [
        f"🔍 *RESEARCH BRIEF* — `{target}`",
        f"_asof : {asof}_",
        "",
        "═══ *FAITS CHIFFRÉS* ═══",
        _bullets(facts, limit=4),
        "",
        "═══ *CONSENSUS ANALYSTE* ═══",
        _bullets(consensus, limit=3),
        "",
        "═══ *NEWS RÉCENTS (14j)* ═══",
        _bullets(news, limit=5),
        "",
        "─────",
        "_Sources : Bigdata.com — https://bigdata.com_",
        "_Pas de jugement. Toi de calibrer._",
    ]
    return "\n".join(parts)


def _check_no_verdict(markdown: str) -> bool:
    """Returns True si markdown contains a verdict pattern (FAIL).

    Test mecanise barriere #150 : aucune direction/probabilite/recommandation
    dans le brief. Cf SPEC §5.4.
    """
    for pat in _VERDICT_PATTERNS:
        if pat.search(markdown):
            log.warning(f"research_brief verdict pattern detected: {pat.pattern}")
            return True
    return False


def fetch(target: str, user_id: str) -> dict:
    """Generate research brief for target. Returns dict with markdown + meta.

    Args:
        target: ticker (AAPL) or theme (data center power grid)
        user_id: pour rate-limit + audit trail

    Returns:
        {
            "ok": bool,
            "markdown": str (Telegram-ready),
            "error": str | None,
            "cost_usd": float,
            "response_chars": int,
        }
    """
    target = (target or "").strip()
    if not target or len(target) > 100:
        return {"ok": False, "error": "Cible invalide. Format : ticker (AAPL) ou theme court."}

    # Rate-limit check via shared/storage helper
    try:
        from shared.storage import check_research_brief_rate_limit
        allowed, retry_minutes = check_research_brief_rate_limit(user_id, max_per_hour=1)
        if not allowed:
            return {
                "ok": False,
                "error": f"Rate-limit : 1 brief/h. Prochain dispo dans {retry_minutes} min.",
            }
    except Exception:
        pass  # Rate-limit silent-miss : if storage indispo, allow fetch

    backend = _backend()
    target_type = "ticker" if (target.isupper() and len(target) <= 6) else "theme"

    # 3 queries per spec §3
    facts = backend.search(f"{target} revenue gross margin guidance recent quarter", n_chunks=10)
    consensus = backend.search(f"{target} analyst consensus price target recommendation", n_chunks=8)
    news = backend.search(f"{target} news significant developments last 14 days", n_chunks=12)

    markdown = _format_markdown(target, facts, consensus, news)

    # Anti-anchoring gate (SPEC §5.4)
    if _check_no_verdict(markdown):
        log.error(f"research_brief verdict pattern in output for target={target!r} — REFUSE send")
        # Log fail to research_brief_log
        try:
            from shared.storage import insert_research_brief_log
            insert_research_brief_log(
                user_id=user_id, target=target, target_type=target_type,
                success=False, cost_actual_usd=0.0,
                error_reason="verdict_pattern_detected", response_chars=len(markdown),
            )
        except Exception:
            pass
        return {
            "ok": False,
            "error": "Brief rejete : verdict pattern detecte. Cure : voir log + revoir prompt format.",
        }

    # Log success
    cost_estimate = 0.05  # Bigdata calls + minimal LLM overhead, ~$0.05/brief typique
    try:
        from shared.storage import insert_research_brief_log
        insert_research_brief_log(
            user_id=user_id, target=target, target_type=target_type,
            success=True, cost_actual_usd=cost_estimate,
            error_reason=None, response_chars=len(markdown),
        )
    except Exception:
        pass

    return {
        "ok": True,
        "markdown": markdown,
        "cost_usd": cost_estimate,
        "response_chars": len(markdown),
    }
