"""Aiguillage anti-entetement — Erosion de THESE au niveau driver.

Confronte les signals arrives DEPUIS opened_at aux key_drivers /
invalidation_triggers SPECIFIQUES de la these via LLM Haiku.

Complementaire (anti-double-instrumentation L4) :
- thesis_track_record : empirique (Brier des predictions).
- thesis_health_metrics M14 : staleness temporelle (last_reviewed age).
- ICI : erosion de CONTENU au niveau driver -- l'evidence contredit-elle
  les propositions falsifiables ?

L15 fail-closed strict :
- LLM down sur 1 signal -> compte en degraded mais batch continue.
- LLM down sur >= moitie des signals -> verdict REVIEW_DUE_DEGRADED
  (jamais de verdict fabrique sur evidence partielle).
- Si _check_cost_cap leve LLMUnavailableError, traite identique.

Cout Haiku par run : 12 signaux x N theses actives = ~312 LLM calls Haiku
en mode plein. Plafond _TOP_N=12 par these limite l'explosion.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from shared import llm, storage

log = logging.getLogger(__name__)

_TOP_N = 12          # plafond cout : top N signaux par materialite depuis opened_at
_TRIGGER_CONF = 0.60  # seuil confidence pour acter un invalidation_trigger
_EROSION_NET = -1.5  # seuil net (somme ponderee erode-confirm) pour driver erode
_STALE_DAYS = 45      # 0 signal materiel depuis Nj = angle mort potentiel

_CLASSIFY_PROMPT = """Tu confrontes UN signal a UNE these d'investissement. DATE = {today}.
Ne raisonne QUE sur les donnees fournies ; n'invente aucun evenement absent.

THESE {ticker} (conviction {conviction}, direction {direction}) :
DRIVERS (propositions a confirmer) :
{drivers}
INVALIDATION_TRIGGERS (propositions qui CASSENT la these) :
{invalidations}

SIGNAL (date {sig_date}) :
"{sig_title}"
{sig_summary}

Reponds en JSON strict :
{{"bears_on": "driver"|"invalidation"|"none",
  "target_index": <int index 0-based dans la liste concernee, ou null>,
  "relation": "confirms"|"erodes"|"triggers"|"neutral",
  "confidence": <0.0-1.0>,
  "rationale": "<=20 mots, cite la proposition ET le signal>",
  "evidence_quote": "<extrait litteral du signal, ou ''>"}}
Regles : 'triggers' UNIQUEMENT si bears_on='invalidation' et la condition est factuellement remplie.
Si le signal ne touche aucune proposition -> bears_on='none', relation='neutral'.
Si pas d'evidence specifique -> confidence basse. Pas de relation forte 'par impression'."""


def _today_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _days_since(iso_ts: str | None) -> int:
    """Nombre de jours depuis un ISO timestamp. Retourne 0 si parse fail."""
    if not iso_ts:
        return 0
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return max(0, (datetime.now(UTC) - dt).days)
    except (ValueError, TypeError):
        return 0


def _safe_json_load(raw, default):
    """Tolere les 2 sources : storage._parse_thesis_row deserialize deja
    key_drivers/invalidation_triggers (liste). Mais d'autres call paths
    peuvent passer le JSON raw (str). Idempotent : list -> list, str -> parse."""
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def classify_signal_vs_thesis(thesis: dict, signal: dict) -> dict | None:
    """LLM Haiku : classifie 1 signal contre 1 these.

    Returns dict {bears_on, target_index, relation, confidence, rationale,
    evidence_quote, signal_id, materiality} ou None si LLM indisponible
    (caller gere degraded count).
    """
    drivers = _safe_json_load(thesis.get("key_drivers"), [])
    invals = _safe_json_load(thesis.get("invalidation_triggers"), [])
    prompt = _CLASSIFY_PROMPT.format(
        today=_today_iso(),
        ticker=thesis["ticker"], conviction=thesis.get("conviction", "?"),
        direction=thesis.get("direction", "long"),
        drivers="\n".join(f"  [{i}] {d}" for i, d in enumerate(drivers)) or "  (aucun)",
        invalidations="\n".join(f"  [{i}] {t}" for i, t in enumerate(invals)) or "  (aucun)",
        sig_date=signal.get("asof", "?"),
        sig_title=(signal.get("title") or "")[:200],
        sig_summary=(signal.get("summary") or "")[:500],
    )
    try:
        raw = llm.call(prompt, tier="extract", task="thesis_erosion")
    except llm.LLMUnavailableError:
        return None
    except Exception as e:
        log.warning(
            f"thesis_erosion classify call failed unexpectedly: {type(e).__name__}: {e}",
        )
        return None
    # JSON extraction tolerante (LLM peut entourer de texte)
    if not raw:
        return None
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        out = json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError):
        log.warning(
            "thesis_erosion: classify parse fail ticker=%s sig=%s",
            thesis["ticker"], signal.get("id"),
        )
        return None
    out["signal_id"] = signal.get("id")
    out["materiality"] = float(signal.get("materiality") or 1.0)
    return out


def compute_thesis_erosion(thesis_id: int) -> dict:
    """Verdict d'erosion pour une these active. Fail-closed L15.

    Returns dict {thesis_id, ticker, verdict, steer, driver_status,
    n_confirm, n_erode, n_invalidation_hit, degraded}.
    """
    thesis = storage.get_thesis(thesis_id)
    if not thesis or thesis.get("status") != "active":
        return {"verdict": "N/A", "reason": "these non active"}

    signals = storage.get_material_signals_since(
        ticker=thesis["ticker"],
        since_iso=thesis["opened_at"],
        limit=_TOP_N,
    )

    # Anti-entetement : aucune evidence confrontee depuis l'entree
    if not signals:
        days = _days_since(thesis.get("opened_at"))
        verdict = "STALE_UNUPDATED" if days >= _STALE_DAYS else "INTACT"
        steer = (
            f"aucune evidence depuis {days}j — angle mort potentiel"
            if verdict == "STALE_UNUPDATED"
            else "pas d'evidence nouvelle, these non contredite"
        )
        return _persist(
            thesis, verdict, classified=[], signals=[],
            degraded=False, steer=steer,
        )

    classified: list[dict] = []
    degraded_count = 0
    for s in signals:
        c = classify_signal_vs_thesis(thesis, s)
        if c is None:
            degraded_count += 1
        else:
            classified.append(c)

    # L15 fail-closed : si majorite non classee -> REFUSE verdict de contenu
    if degraded_count and degraded_count >= len(signals) / 2:
        return _persist(
            thesis, "REVIEW_DUE_DEGRADED",
            classified=classified, signals=signals,
            degraded=True,
            steer=f"{degraded_count}/{len(signals)} signals non classes (LLM degrade) — revue manuelle",
        )

    drivers = _safe_json_load(thesis.get("key_drivers"), [])
    net = dict.fromkeys(range(len(drivers)), 0.0)
    n_conf = n_ero = n_inval = 0
    for c in classified:
        w = float(c.get("materiality", 1.0)) * float(c.get("confidence", 0.0))
        rel = c.get("relation")
        idx = c.get("target_index")
        bears_on = c.get("bears_on")
        conf = float(c.get("confidence", 0))
        if bears_on == "invalidation" and rel == "triggers" and conf >= _TRIGGER_CONF:
            n_inval += 1
        elif bears_on == "driver" and isinstance(idx, int) and idx in net:
            if rel == "confirms":
                net[idx] += w
                n_conf += 1
            elif rel == "erodes":
                net[idx] -= w
                n_ero += 1

    driver_status = [
        {
            "driver": d,
            "net": round(net[i], 2),
            "status": (
                "broken" if net[i] <= _EROSION_NET else
                "eroding" if net[i] < 0 else
                "intact"
            ),
        }
        for i, d in enumerate(drivers)
    ]

    if n_inval >= 1:
        verdict = "INVALIDATION_HIT"
        steer = "invalidation declenchee — revue pour exit (territoire kill_criteria)"
    elif any(ds["net"] <= _EROSION_NET for ds in driver_status):
        broken = next(ds["driver"] for ds in driver_status if ds["net"] <= _EROSION_NET)
        verdict = "EROSION_DETECTED"
        steer = f"driver erode : « {broken} » — re-justifie ou allege"
    else:
        verdict = "INTACT"
        steer = "drivers confirmes/neutres, these tient"

    return _persist(
        thesis, verdict, classified=classified, signals=signals,
        degraded=bool(degraded_count), steer=steer,
        driver_status=driver_status,
        n_conf=n_conf, n_ero=n_ero, n_inval=n_inval,
    )


def _persist(
    thesis: dict, verdict: str,
    *,
    classified: list[dict], signals: list[dict],  # noqa: ARG001 -- classified reserve futur audit
    degraded: bool, steer: str,
    driver_status: list | None = None,
    n_conf: int = 0, n_ero: int = 0, n_inval: int = 0,
) -> dict:
    storage.insert_thesis_erosion(
        thesis_id=thesis["id"], ticker=thesis["ticker"], verdict=verdict,
        n_confirm=n_conf, n_erode=n_ero, n_invalidation_hit=n_inval,
        driver_status_json=json.dumps(driver_status or [], ensure_ascii=False),
        signals_considered_json=json.dumps([s.get("id") for s in signals]),
        degraded=degraded, steer=steer,
    )
    return {
        "thesis_id": thesis["id"],
        "ticker": thesis["ticker"],
        "verdict": verdict,
        "steer": steer,
        "driver_status": driver_status or [],
        "n_confirm": n_conf,
        "n_erode": n_ero,
        "n_invalidation_hit": n_inval,
        "degraded": degraded,
    }


def compute_all_active_theses() -> dict:
    """Run erosion compute sur toutes les theses actives.

    Returns stats {checked, intact, erosion_detected, invalidation_hit,
    stale_unupdated, review_due_degraded, errors}.
    """
    stats = {
        "checked": 0,
        "intact": 0,
        "erosion_detected": 0,
        "invalidation_hit": 0,
        "stale_unupdated": 0,
        "review_due_degraded": 0,
        "errors": 0,
    }
    try:
        with storage.db() as cx:
            ids = [r[0] for r in cx.execute(
                "SELECT id FROM theses WHERE status='active' ORDER BY conviction DESC",
            ).fetchall()]
    except Exception as e:
        log.warning(f"compute_all_active_theses: fetch theses failed: {e}")
        return stats

    for tid in ids:
        try:
            out = compute_thesis_erosion(tid)
            stats["checked"] += 1
            v = out.get("verdict", "").lower()
            key = {
                "intact": "intact",
                "erosion_detected": "erosion_detected",
                "invalidation_hit": "invalidation_hit",
                "stale_unupdated": "stale_unupdated",
                "review_due_degraded": "review_due_degraded",
            }.get(v)
            if key:
                stats[key] += 1
        except Exception as e:
            log.warning(f"compute_thesis_erosion {tid} failed: {e}")
            stats["errors"] += 1
            continue
    return stats
