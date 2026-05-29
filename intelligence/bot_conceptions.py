"""Layer 2 — bot_conceptions : digest des signaux soft + decisions + theses
+ interventions + signaux newsletter en VUE STABLE DU BOT par target.

Pour chaque ticker / sector / theme on construit une conception : narratif
court (1 paragraphe), conviction 0-100, valence -1 a +1, sources citees.

Cron hebdo (ou trigger manuel) — append-only. Query = MAX(id) per
(kind, target_key) via storage.get_latest_conception.

La conception est ensuite injectee dans :
  - copilot pre-trade prompt (avant /position_buy /position_sell /override)
  - chat context (pour repondre tailormade sur un ticker specifique)
  - dashboard panel "Vues du bot"
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta

from shared import llm, storage

log = logging.getLogger(__name__)


_PROMPT = """Tu construis la VUE INTERNE du bot sur un {kind_label} specifique.

Cette vue est une synthese stable de tout ce que le bot sait sur ce {kind_label}
a travers les inputs structures + les conversations chat passees. Pas un
verdict final, juste l'etat actuel de la comprehension.

CIBLE : {target_key}

══════════════════════ INPUTS STRUCTURES ══════════════════════

Theses actives ({n_theses}) :
{theses_block}

Decisions historiques sur ce target ({n_decisions}) :
{decisions_block}

Interventions copilot passees ({n_interventions}) :
{interventions_block}

Signaux newsletter filtres ({n_signals}) :
{signals_block}

══════════════════════ INPUTS CHAT (signaux soft) ══════════════════════

Signaux soft extraits du chat ({n_chat_signals}) :
{chat_signals_block}

══════════════════════ REGLES ══════════════════════

1. La conception est en FRANCAIS, ton direct et sec (CLAUDE.md).
2. Cite TOUJOURS evidence_ids (decision_42, signal_295, thesis_24, ces_3,
   intervention_12) — pas d'opinion sans citation.
3. Si la conception varie selon le timeframe, mentionne-le (court terme vs
   12 mois).
4. valence : -1 (le bot est convaincu negatif) -> +1 (convaincu positif),
   0 = pas de vue forte.
5. conviction : 0-100, calibre sur le sample size :
   - <3 inputs -> 30 max
   - 3-10 inputs -> 50 max
   - >10 + diversite de sources -> jusqu'a 90
6. INTERDIT : "Diversifie ton portefeuille", "Reste discipline" — generiques.

══════════════════════ FORMAT DE SORTIE (JSON strict) ══════════════════════

{{
  "conception_text": "Vue actuelle du bot en 3-6 phrases. Cite evidence_ids. Mentionne court-terme vs long-terme si pertinent. Ne masque pas la dissonance (ex. user bullish reasoning vs Brier defavorable). 800 chars max.",
  "conviction": <0-100>,
  "valence": <-1 a +1>,
  "key_drivers_internal": ["1-3 drivers que le bot considere comme dominants"],
  "open_questions": ["1-3 angles morts ou questions non resolues"],
  "evidence_ids_cited": ["thesis_24", "decision_12", "ces_3", ...]
}}
"""


def _format_thesis(t: dict) -> str:
    tid = t.get("id")
    conv = t.get("conviction", "?")
    direction = t.get("direction", "?")
    entry = t.get("entry_price")
    target_full = t.get("target_full")
    stop = t.get("stop_price")
    drivers = (t.get("key_drivers") or "")[:300]
    return (
        f"  - thesis_{tid} c{conv} {direction} | entry {entry} / target {target_full} / stop {stop}\n"
        f"    drivers: {drivers}"
    )


def _format_decision(d: dict) -> str:
    did = d.get("id")
    dt = d.get("created_at", "")[:10]
    dtype = d.get("decision_type", "?")
    reasoning = (d.get("reasoning") or "")[:240]
    ret = d.get("return_30d_pct")
    ret_s = f" return30d={ret:+.1f}%" if isinstance(ret, int | float) else ""
    return f"  - decision_{did} [{dt}] {dtype}: {reasoning}{ret_s}"


def _format_intervention(i: dict) -> str:
    iid = i.get("id")
    dt = (i.get("created_at") or "")[:10]
    ver = i.get("verdict", "?")
    score = i.get("pressure_score", "?")
    anc = (i.get("ancrage") or "")[:200]
    return f"  - intervention_{iid} [{dt}] {ver} score={score}: {anc}"


def _format_signal(s: dict) -> str:
    sid = s.get("id")
    dt = (s.get("timestamp") or "")[:10]
    title = (s.get("title") or "")[:140]
    score = s.get("score", "?")
    return f"  - signal_{sid} [{dt}] score={score}: {title}"


def _format_chat_signal(cs: dict) -> str:
    cid = cs.get("id")
    kind = cs.get("kind", "?")
    val = cs.get("valence")
    val_s = f"{val:+.1f}" if isinstance(val, int | float) else "?"
    quote = (cs.get("evidence_quote") or "")[:180]
    return f"  - ces_{cid} [{kind}] val={val_s}: \"{quote}\""


def _fetch_target_context(kind: str, target_key: str, months_window: int = 6) -> dict:
    """Pull all structured inputs for a (kind, target_key) over the window."""
    window_start = (datetime.now(UTC) - timedelta(days=months_window * 30)).isoformat()
    out: dict = {
        "theses": [], "decisions": [], "interventions": [],
        "signals": [], "chat_signals": [],
    }
    with storage.db() as cx:
        if kind == "ticker":
            t_rows = cx.execute(
                "SELECT id, ticker, conviction, direction, opened_at, key_drivers, "
                "entry_price, target_partial, target_full, stop_price, status "
                "FROM theses WHERE ticker=? AND status IN ('active','realized')",
                (target_key,),
            ).fetchall()
            tcols = ["id", "ticker", "conviction", "direction", "opened_at", "key_drivers",
                     "entry_price", "target_partial", "target_full", "stop_price", "status"]
            out["theses"] = [dict(zip(tcols, r, strict=False)) for r in t_rows]

            d_rows = cx.execute(
                "SELECT id, created_at, decision_type, reasoning, resolved_30d_at, return_30d_pct "
                "FROM decisions WHERE ticker=? AND created_at >= ? ORDER BY created_at DESC LIMIT 20",
                (target_key, window_start),
            ).fetchall()
            dcols = ["id", "created_at", "decision_type", "reasoning", "resolved_30d_at", "return_30d_pct"]
            out["decisions"] = [dict(zip(dcols, r, strict=False)) for r in d_rows]

            try:
                i_rows = cx.execute(
                    "SELECT id, created_at, decision_type, verdict, pressure_score, ancrage, return_30d_pct "
                    "FROM bot_copilot_interventions WHERE ticker=? AND created_at >= ? "
                    "ORDER BY created_at DESC LIMIT 15",
                    (target_key, window_start),
                ).fetchall()
                icols = ["id", "created_at", "decision_type", "verdict", "pressure_score",
                         "ancrage", "return_30d_pct"]
                out["interventions"] = [dict(zip(icols, r, strict=False)) for r in i_rows]
            except Exception:
                pass

            s_rows = cx.execute(
                "SELECT id, timestamp, title, score "
                "FROM signals WHERE timestamp >= ? "
                "AND (entities LIKE ? OR title LIKE ?) AND score >= 4 "
                "ORDER BY timestamp DESC LIMIT 15",
                (window_start, f"%{target_key}%", f"%{target_key}%"),
            ).fetchall()
            scols = ["id", "timestamp", "title", "score"]
            out["signals"] = [dict(zip(scols, r, strict=False)) for r in s_rows]

            try:
                cs_rows = cx.execute(
                    "SELECT id, kind, valence, evidence_quote, note, created_at "
                    "FROM chat_extracted_signals WHERE ticker=? AND created_at >= ? "
                    "ORDER BY created_at DESC LIMIT 20",
                    (target_key, window_start),
                ).fetchall()
                cscols = ["id", "kind", "valence", "evidence_quote", "note", "created_at"]
                out["chat_signals"] = [dict(zip(cscols, r, strict=False)) for r in cs_rows]
            except Exception:
                pass

        elif kind in ("sector", "theme"):
            # Whitelisted column (kind in {"sector","theme"}) — safe interpolation.
            field_col = "sector" if kind == "sector" else "theme"
            try:
                cs_rows = cx.execute(
                    f"SELECT id, kind, valence, evidence_quote, note, created_at "
                    f"FROM chat_extracted_signals WHERE {field_col}=? AND created_at >= ? "
                    "ORDER BY created_at DESC LIMIT 30",
                    (target_key, window_start),
                ).fetchall()
                cscols = ["id", "kind", "valence", "evidence_quote", "note", "created_at"]
                out["chat_signals"] = [dict(zip(cscols, r, strict=False)) for r in cs_rows]
            except Exception:
                pass
    return out


def synthesize_conception(kind: str, target_key: str, months_window: int = 6) -> tuple[dict | None, int | None]:
    """Run Opus synthesis. Returns (result_dict, conception_id)."""
    ctx = _fetch_target_context(kind, target_key, months_window=months_window)
    n_inputs = sum(len(ctx[k]) for k in ("theses", "decisions", "interventions", "signals", "chat_signals"))
    if n_inputs == 0:
        log.info(f"no inputs for {kind}={target_key}, skip")
        return None, None

    kind_label = {"ticker": "ticker", "sector": "secteur", "theme": "theme narratif"}.get(kind, kind)

    prompt = _PROMPT.format(
        kind_label=kind_label,
        target_key=target_key,
        n_theses=len(ctx["theses"]),
        theses_block="\n".join(_format_thesis(t) for t in ctx["theses"]) or "  (aucune)",
        n_decisions=len(ctx["decisions"]),
        decisions_block="\n".join(_format_decision(d) for d in ctx["decisions"]) or "  (aucune)",
        n_interventions=len(ctx["interventions"]),
        interventions_block="\n".join(_format_intervention(i) for i in ctx["interventions"]) or "  (aucune)",
        n_signals=len(ctx["signals"]),
        signals_block="\n".join(_format_signal(s) for s in ctx["signals"]) or "  (aucun)",
        n_chat_signals=len(ctx["chat_signals"]),
        chat_signals_block="\n".join(_format_chat_signal(cs) for cs in ctx["chat_signals"]) or "  (aucun)",
    )

    t0 = time.time()
    try:
        result = llm.call_json(prompt, tier="synthesize", max_tokens=1200)
    except Exception as e:
        log.warning(f"conception synthesis {kind}={target_key} failed: {e}")
        return None, None
    elapsed_ms = int((time.time() - t0) * 1000)

    if not isinstance(result, dict) or "conception_text" not in result:
        log.warning(f"conception synthesis {kind}={target_key} bad response shape")
        return None, None

    conviction = int(result.get("conviction") or 0)
    valence = float(result.get("valence") or 0)
    sources_json = json.dumps({
        "thesis_ids": [t["id"] for t in ctx["theses"]],
        "decision_ids": [d["id"] for d in ctx["decisions"]],
        "intervention_ids": [i["id"] for i in ctx["interventions"]],
        "signal_ids": [s["id"] for s in ctx["signals"]],
        "chat_signal_ids": [cs["id"] for cs in ctx["chat_signals"]],
        "evidence_ids_cited": result.get("evidence_ids_cited") or [],
        "key_drivers_internal": result.get("key_drivers_internal") or [],
        "open_questions": result.get("open_questions") or [],
    }, ensure_ascii=False)

    cid = storage.insert_bot_conception(
        kind=kind,
        target_key=target_key,
        conception_text=result.get("conception_text") or "",
        conviction=conviction,
        valence=valence,
        sources_json=sources_json,
        n_signals_used=n_inputs,
        llm_meta={"elapsed_ms": elapsed_ms},
    )
    log.info(
        f"conception {kind}={target_key} conv={conviction} val={valence:+.2f} "
        f"n_inputs={n_inputs} id={cid}"
    )
    return result, cid


def synthesize_all_active_tickers(months_window: int = 6) -> dict:
    """Iterate over all tickers with an active thesis ; synthesize each one."""
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT DISTINCT ticker FROM theses WHERE status='active' ORDER BY ticker"
        ).fetchall()
    tickers = [r[0] for r in rows]
    log.info(f"synthesize_all_active_tickers : {len(tickers)} tickers")
    out = {"ok": 0, "skip": 0, "fail": 0}
    for tk in tickers:
        try:
            _, cid = synthesize_conception("ticker", tk, months_window=months_window)
            if cid:
                out["ok"] += 1
            else:
                out["skip"] += 1
        except Exception as e:
            log.warning(f"conception {tk} crashed: {e}")
            out["fail"] += 1
        time.sleep(0.5)
    return out


def format_conception_for_copilot(kind: str, target_key: str) -> str:
    """Format the latest conception as a block to inject in copilot prompt."""
    c = storage.get_latest_conception(kind, target_key)
    if not c:
        return f"  (pas encore de conception bot sur {target_key})"
    val = c.get("valence")
    val_s = f"{val:+.2f}" if isinstance(val, int | float) else "?"
    return (
        f"  Conviction bot sur {target_key} : {c.get('conviction', 0)}/100, valence {val_s} "
        f"(n_signals={c.get('n_signals_used', 0)}, {(c.get('created_at') or '')[:10]})\n"
        f"  {c.get('conception_text', '')}"
    )
