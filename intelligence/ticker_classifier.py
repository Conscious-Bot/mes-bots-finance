"""Sprint 12 — Refactor critique : tagger chaque ticker sur 4 axes pour
redefinir REDONDANCE (driver+stage match) et DECORRELATION (macro_factor
diversity), per la review utilisateur.

Pourquoi : la critique pointait que Sprint 6 prompt narrative confondait
'meme theme' avec 'meme driver+stage' — d'ou des faux flags type
'Safran redondant avec Thales' (propulsion vs electronique = stages
differents) ou 'AMD redondant avec TSMC' (client fabless vs fondeur).

Axes :
  - demand_driver     : ce qui fait bouger la demande (AI capex, defense
                        rearmament, memory cycle, ...)
  - value_chain_stage : etage de la chaine (fabless designer, pure foundry,
                        equipment maker, wafer supplier, operator, ...)
  - moat_source       : nature du moat (monopoly tech, switching cost,
                        brand+aftermarket, scale, ...)
  - macro_factor      : le grand facteur macro derriere (AI capex /
                        rates / defense / energy / rare earths / ...)

Redondance ⟺ demand_driver ET value_chain_stage coincident.
Decorrelation = uniqueness of macro_factor au sein des c>=4 positions.
"""

from __future__ import annotations

import json
import logging
import time

from shared import llm, storage

log = logging.getLogger(__name__)


_PROMPT = """Tu classifies un ticker boursier sur 4 axes precis. Ne donne JAMAIS de jugement bullish/bearish — c'est purement descriptif.

TICKER : {ticker}
INFO USER (these active si dispo) :
{thesis_block}

══════════════════════ AXES (definitions strictes) ══════════════════════

1. demand_driver : ce qui fait bouger la DEMANDE pour ce produit/service.
   Doit etre TRES SPECIFIQUE, 4-8 mots.
   ✓ "AI capex hyperscalers"        ✓ "Memory cycle HBM/DRAM"
   ✓ "Defense rearmament EU"        ✓ "Uranium nuclear renaissance"
   ✓ "Rare earths China substitute" ✓ "Cloud workloads aftermarket"
   ✗ "Tech" / "Semis" / "Industrials" (trop large)

2. value_chain_stage : etage exact dans la chaine de valeur.
   ✓ "Pure foundry leading-edge"     ✓ "Fabless designer GPU/ASIC"
   ✓ "EUV litho equipment monopoly"  ✓ "ATE test equipment"
   ✓ "HBM/DRAM memory IDM"           ✓ "EDA software duopoly"
   ✓ "Wafer materials silicon"       ✓ "Engine OEM aftermarket annuity"
   ✓ "Defense electronics integrator" ✓ "Pure mining operator"
   ✗ "Semiconductors" / "Defense" (= secteur, pas stage)

3. moat_source : nature concrete du moat economique.
   ✓ "Tech monopoly EUV no substitute"      ✓ "EDA switching cost 10y+"
   ✓ "Engine duopoly + LEAP aftermarket"   ✓ "Foundry scale + tech lead"
   ✓ "Brand + national security buyer"      ✓ "Geographic reserves rare"
   ✓ "Network effects cloud lock-in"        ✓ "Regulatory moat"

4. macro_factor : le GRAND facteur macro derriere. Une seule etiquette parmi :
   - "AI capex"
   - "AI inference/compute demand"
   - "Memory cycle"
   - "Defense rearmament"
   - "Energy commodities"
   - "Rare earths / materials"
   - "Rates / financials"
   - "Consumer cyclical"
   - "Healthcare innovation"
   - "Industrial reshoring"
   - "Crypto / digital assets"
   - "Other" (si rien ne colle)
   ⚠ Si le ticker joue 2 facteurs avec poids comparables, mets le DOMINANT
   et utilise alt_drivers pour le secondaire.

══════════════════════ EXEMPLES (calibration) ══════════════════════

TSM :
  demand_driver  : "AI capex hyperscalers + leading-edge nodes"
  value_chain_stage : "Pure foundry leading-edge N2/N3"
  moat_source : "Scale + tech lead + customer lock"
  macro_factor : "AI capex"

ASML.AS :
  demand_driver : "AI capex hyperscalers + leading-edge nodes"
  value_chain_stage : "EUV litho equipment monopoly"
  moat_source : "Tech monopoly EUV no substitute"
  macro_factor : "AI capex"

(ASML et TSM partagent demand_driver mais PAS value_chain_stage -> PAS redundant)

SNPS :
  demand_driver : "AI chip design complexity"
  value_chain_stage : "EDA software duopoly"
  moat_source : "Switching cost 10y+ + IP library"
  macro_factor : "AI capex"

(SNPS et TSM partagent macro_factor mais demand_driver different ET stage different -> PAS redundant, et SNPS est decorrelant via moat unique)

SAF.PA :
  demand_driver : "Defense rearmament EU + civil aerospace recovery"
  value_chain_stage : "Engine OEM + LEAP aftermarket annuity"
  moat_source : "Engine duopoly + LEAP aftermarket annuity"
  macro_factor : "Defense rearmament"

HO.PA :
  demand_driver : "Defense rearmament EU + cyber demand"
  value_chain_stage : "Defense electronics integrator + radar"
  moat_source : "Brand + national security buyer"
  macro_factor : "Defense rearmament"

(SAF et HO partagent macro_factor ET demand_driver MAIS value_chain_stage different -> PAS redundant, c'est diversification interne)

MU :
  demand_driver : "Memory cycle HBM/DRAM AI"
  value_chain_stage : "HBM/DRAM memory IDM"
  moat_source : "Memory duopoly capex barrier"
  macro_factor : "Memory cycle"

000660.KS (SK Hynix) :
  demand_driver : "Memory cycle HBM/DRAM AI"
  value_chain_stage : "HBM/DRAM memory IDM"
  moat_source : "HBM lead + memory duopoly"
  macro_factor : "Memory cycle"

(MU et SK Hynix partagent demand_driver ET value_chain_stage -> REDUNDANT au sens strict)

══════════════════════ FORMAT JSON ══════════════════════

{{
  "demand_driver": "...",
  "value_chain_stage": "...",
  "moat_source": "...",
  "macro_factor": "...",
  "alt_drivers": ["..."],
  "confidence": <0-100>,
  "rationale": "1-2 phrases qui justifient les 4 choix"
}}
"""


def _format_thesis_for_classifier(ticker: str) -> str:
    try:
        t = storage.get_thesis_by_ticker(ticker, status="active")
    except Exception:
        t = None
    if not t:
        return "  (pas de these active sur ce ticker)"
    return (
        f"  conviction c{t.get('conviction','?')}\n"
        f"  key_drivers: {(t.get('key_drivers') or '')[:600]}\n"
        f"  notes: {(t.get('notes') or '')[:300]}"
    )


def classify_ticker(ticker: str) -> tuple[dict | None, int | None]:
    """Classify a single ticker on the 4 axes. Returns (result_dict, axes_id)."""
    prompt = _PROMPT.format(ticker=ticker, thesis_block=_format_thesis_for_classifier(ticker))
    t0 = time.time()
    try:
        result = llm.call_json(prompt, tier="enrich", max_tokens=800)
    except Exception as e:
        log.warning(f"classify_ticker {ticker} failed: {e}")
        return None, None
    elapsed_ms = int((time.time() - t0) * 1000)
    if not isinstance(result, dict) or "demand_driver" not in result:
        log.warning(f"classify_ticker {ticker} bad response shape")
        return None, None
    alt = result.get("alt_drivers") or []
    alt_json = json.dumps(alt, ensure_ascii=False) if alt else None
    aid = storage.insert_ticker_axes(
        ticker=ticker,
        demand_driver=str(result.get("demand_driver", ""))[:200],
        value_chain_stage=str(result.get("value_chain_stage", ""))[:200],
        moat_source=str(result.get("moat_source", ""))[:200],
        macro_factor=str(result.get("macro_factor", "Other"))[:80],
        alt_drivers_json=alt_json,
        confidence=int(result.get("confidence") or 50),
        rationale=str(result.get("rationale") or "")[:600],
        llm_meta={"elapsed_ms": elapsed_ms},
    )
    return result, aid


def classify_all_held_tickers() -> dict:
    """Classify every ticker currently held (positions.qty>0)."""
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT DISTINCT ticker FROM positions WHERE qty > 0 AND status='open' "
            "ORDER BY ticker"
        ).fetchall()
    tickers = [r[0] for r in rows]
    log.info(f"classify_all_held_tickers : {len(tickers)} tickers")
    out = {"ok": 0, "skip": 0, "fail": 0}
    for tk in tickers:
        try:
            _, aid = classify_ticker(tk)
            if aid:
                out["ok"] += 1
            else:
                out["skip"] += 1
        except Exception as e:
            log.warning(f"classify {tk} crashed: {e}")
            out["fail"] += 1
        time.sleep(0.3)
    return out
