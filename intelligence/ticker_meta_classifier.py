"""Sprint 14 — Classifier Sonnet pour fade-rate + SPOF + reverse-DCF.

Produit per ticker :
  - fade_rate_score : 0 (annuity infinie type ASML/SAF aftermarket) →
                      100 (revert immediat type Lasertec/memoire au pic)
  - moat_durability_years : 5 ans ? 20 ans ? 50 ans ?
  - upstream_critical_deps : nodes upstream dont la societe depend pour
                             >30% revenu OU >30% capacite
                             (ex: AMD → TSMC N3 ; AVGO → TSMC N3 ; SK Hynix
                             → ASML EUV)
  - valo_what_priced_in : 1 phrase reverse-DCF
  - valo_pe_or_proxy : P/E ou multiple equivalent
  - valo_above_bull_case : True si expectations > bull case
"""

from __future__ import annotations

import json
import logging
import time

from shared import llm, storage

log = logging.getLogger(__name__)


_PROMPT = """Tu produis 4 metriques structurees pour un ticker boursier dans le cadre Mauboussin / strategic analysis. Pas d'opinion bullish/bearish — descriptif factuel.

TICKER : {ticker}
INFO USER (these active si dispo) :
{thesis_block}

══════════════════════ 1. FADE-RATE (Mauboussin) ══════════════════════

Score 0-100 : a quelle vitesse ROIC revient au cost of capital ?
  - 0     : annuity quasi-infinie (Coca, Wrigley, ASML monopoly EUV,
            engine aftermarket Safran/GE Vernova)
  - 25    : fade lent, moat solide 15-25 ans (TSM scale+tech, Synopsys
            switching cost, Mauboussin's "good fade")
  - 50    : fade typique secteur tech (5-10 ans avant erosion notable)
  - 75    : fade rapide (cycle court, exposition cycle commodity)
  - 100   : revert immediat / peak cycle / single-customer dependency
            (Lasertec exposition concentree, memoire au pic, single-product)

══════════════════════ 2. UPSTREAM CRITICAL DEPS ══════════════════════

Pour ce ticker, liste les UPSTREAM NODES dont il depend pour >30% de son
revenu OU >30% de sa capacite. Format : node = chokepoint identifie.

Examples :
  - AMD       : ["TSMC N3", "TSMC N5"] (fabless, 100% TSMC pour leading-edge)
  - AVGO      : ["TSMC N3"]
  - ALAB      : ["TSMC N5"]
  - SK Hynix  : ["ASML EUV", "Samsung tools indirect"]
  - MU        : ["ASML EUV"]
  - 6857.T    : (autonome, equipement)
  - ASML.AS   : ["Zeiss optics", "Trumpf lasers"] (mais ASML est lui-meme le node)
  - SAF.PA    : ["GE engine partnership"] (annuity LEAP)
  - HO.PA     : (autonome, integrateur)
  - TSM       : ["ASML EUV", "TEL deposition"]

Si autonome ou peu de deps critiques : retourne [].

══════════════════════ 3. REVERSE-DCF / WHAT'S PRICED IN ══════════════════════

Une phrase factuelle decrivant la trajectoire que le prix actuel suggere
(reverse-DCF mental). Format : "X% revenue growth through Y, Z% margin
expansion, no shock".

valo_above_bull_case = True si tu estimes que ce qui est price-in DEPASSE
le bull case raisonnable (ex: AMD ~92x P/E forward, memoire DRAM au pic).

══════════════════════ 4. MOAT DURABILITY ══════════════════════

Nombre d'annees raisonnable avant erosion notable du moat. Exemples :
  - ASML EUV monopoly : 20 ans (next-gen High-NA + Hyper-NA)
  - TSM scale lead    : 10-15 ans
  - SNPS EDA switch   : 15-20 ans
  - Memory IDM        : 3-5 ans (cycle)
  - Engine aftermarket: 25+ ans (LEAP cycle)
  - Fabless designer  : 3-7 ans (chip cycle)

══════════════════════ FORMAT JSON ══════════════════════

{{
  "fade_rate_score": <0-100>,
  "moat_durability_years": <int>,
  "upstream_critical_deps": [
    {{"node": "TSMC N3", "share_of_revenue_or_capacity": 0.6}}
  ],
  "valo_what_priced_in": "1 phrase factuelle...",
  "valo_pe_or_proxy": <float ou null>,
  "valo_above_bull_case": <true|false>,
  "rationale": "1-2 phrases qui justifient le fade_rate + l'evaluation valo"
}}
"""


def _format_thesis(ticker: str) -> str:
    try:
        t = storage.get_thesis_by_ticker(ticker, status="active")
    except Exception:
        t = None
    if not t:
        return "  (pas de these active)"
    return (
        f"  conviction c{t.get('conviction','?')}\n"
        f"  key_drivers: {(t.get('key_drivers') or '')[:500]}\n"
        f"  notes: {(t.get('notes') or '')[:200]}"
    )


def classify_one(ticker: str) -> tuple[dict | None, int | None]:
    prompt = _PROMPT.format(ticker=ticker, thesis_block=_format_thesis(ticker))
    t0 = time.time()
    try:
        result = llm.call_json(prompt, tier="enrich", max_tokens=800)
    except Exception as e:
        log.warning(f"meta_classify {ticker} failed: {e}")
        return None, None
    elapsed_ms = int((time.time() - t0) * 1000)
    if not isinstance(result, dict) or "fade_rate_score" not in result:
        return None, None
    deps = result.get("upstream_critical_deps") or []
    deps_json = json.dumps(deps, ensure_ascii=False) if deps else None
    mid = storage.insert_ticker_meta(
        ticker=ticker,
        fade_rate_score=int(result.get("fade_rate_score") or 50),
        moat_durability_years=int(result.get("moat_durability_years") or 0) or None,
        upstream_critical_deps_json=deps_json,
        valo_what_priced_in=str(result.get("valo_what_priced_in") or "")[:400],
        valo_pe_or_proxy=float(result.get("valo_pe_or_proxy") or 0) or None,
        valo_above_bull_case=bool(result.get("valo_above_bull_case", False)),
        rationale=str(result.get("rationale") or "")[:500],
        llm_meta={"elapsed_ms": elapsed_ms},
    )
    return result, mid


def classify_all_held_tickers() -> dict:
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT DISTINCT ticker FROM positions WHERE qty > 0 AND status='open' "
            "ORDER BY ticker"
        ).fetchall()
    tickers = [r[0] for r in rows]
    log.info(f"meta_classify_all_held : {len(tickers)} tickers")
    out = {"ok": 0, "skip": 0, "fail": 0}
    for tk in tickers:
        try:
            _, mid = classify_one(tk)
            if mid:
                out["ok"] += 1
            else:
                out["skip"] += 1
        except Exception as e:
            log.warning(f"classify {tk} crashed: {e}")
            out["fail"] += 1
        time.sleep(0.3)
    return out
