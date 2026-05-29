"""Soudure ② : digest ancre au book canonique.

Brief 10 points #8 :
> "Un signal n'est pertinent que s'il rapproche une de mes theses de son
>  kill-criterion ou de sa validation. Le digest LIT LE BOOK ; il ne score
>  pas une materialite generique."

Aujourd'hui le digest filtre par perimetre canonique (Sprint 19) -- correct
mais binaire. Cette couche ajoute un SCORE de pertinence book-anchored :

3 axes de scoring :
1. Kill-criterion match : le signal touche un trigger d'invalidation actif ?
2. Validation match : le signal valide un driver de la these ?
3. Margin urgency : la position est-elle proche du stop/cible ? Un signal
   sur une position en zone tendue est plus urgent.

Score final = (10 * kill_match) + (5 * validation_match) + (margin_urgency 0-3)

Utilise par intelligence/digest.py.generate_unified_digest pour reranking.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


# Keywords associes a chaque type de kill-criterion / driver. Heuristique
# simple a base de matching mots-cles ; v1 ameliore avec embedding similarity.
_KILL_KEYWORDS = {
    "revenue_decline": ["revenue", "ca", "chiffre d'affaires", "sales", "decline", "miss", "shortfall", "lower guidance"],
    "margin_compression": ["margin", "marge", "compression", "gross margin", "pricing"],
    "guidance_baissier": ["guidance", "guidance lower", "forecast down", "outlook cut", "revised down"],
    "pricing_crack": ["pricing", "asp", "price drop", "discount", "crack"],
    "customer_loss": ["customer", "client", "lost", "departure", "qualified out", "design out"],
    "regulatory": ["regulator", "antitrust", "ftc", "doj", "ban", "tariff", "restriction"],
    "operations": ["recall", "disruption", "shutdown", "outage", "factory"],
}

_VALIDATION_KEYWORDS = {
    "ai_capex": ["capex", "datacenter", "ai", "hyperscaler", "gpu", "tpu"],
    "hbm": ["hbm", "memory", "dram"],
    "litho_euv": ["euv", "litho", "asml"],
    "foundry": ["foundry", "tsmc", "fab", "n2", "n3"],
    "defense": ["defense", "rearmament", "military", "frigate"],
    "energy": ["uranium", "nuclear", "lng", "gas", "energy"],
    "rare_earth": ["rare earth", "magnet", "neodymium"],
}


def _extract_signal_text(signal_row: dict) -> str:
    """Concat title + summary pour matching keywords."""
    title = signal_row.get("title") or ""
    summary = signal_row.get("summary") or ""
    return (title + " " + summary).lower()


def _kill_match_score(signal_text: str, kill_criteria: list[str]) -> int:
    """Score 0/5/10 selon match avec kill-criteria de la these.

    10 = mention directe d'un trigger d'invalidation (mot-cle commun >=2)
    5  = mention indirecte (mot-cle commun ==1)
    0  = pas de chevauchement detectable
    """
    if not kill_criteria or not signal_text:
        return 0
    text_lower = signal_text.lower()
    max_score = 0
    for kc in kill_criteria:
        if not isinstance(kc, str):
            continue
        kc_lower = kc.lower()
        # Cherche les keyword groups
        for _type, keywords in _KILL_KEYWORDS.items():
            kc_match = any(k in kc_lower for k in keywords)
            sig_match = sum(1 for k in keywords if k in text_lower)
            if kc_match and sig_match >= 2:
                max_score = max(max_score, 10)
            elif kc_match and sig_match >= 1:
                max_score = max(max_score, 5)
    return max_score


def _validation_match_score(signal_text: str, claim: str) -> int:
    """Score 0/3/5 selon match avec drivers/claim de la these.

    5 = validation forte (>=2 keywords du claim dans signal)
    3 = validation faible (1 keyword)
    0 = aucune
    """
    if not claim or not signal_text:
        return 0
    text_lower = signal_text.lower()
    claim_lower = claim.lower()
    max_score = 0
    for _type, keywords in _VALIDATION_KEYWORDS.items():
        claim_match = any(k in claim_lower for k in keywords)
        sig_match = sum(1 for k in keywords if k in text_lower)
        if claim_match and sig_match >= 2:
            max_score = max(max_score, 5)
        elif claim_match and sig_match >= 1:
            max_score = max(max_score, 3)
    return max_score


def _margin_urgency_score(position_view) -> int:
    """Score 0-3 selon proximite stop/cible.

    3 = position dans zone tendue (margin_to_stop < 15% OR > 85% du chemin vers target)
    2 = zone d'attention (margin_to_stop < 25% OR > 70%)
    1 = neutre (entre)
    0 = pas de these / pas calculable
    """
    if position_view is None:
        return 0
    margin_stop = position_view.margin_to_stop_pct
    frac_axis = position_view.frac_on_stop_target_axis
    if margin_stop is None or frac_axis is None:
        return 0
    # Zone tendue : tres pres stop ou tres pres cible (les 2 extremes = action)
    if margin_stop < 15 or frac_axis > 85:
        return 3
    if margin_stop < 25 or frac_axis > 70:
        return 2
    return 1


def score_signal_book_anchored(signal_row: dict) -> dict:
    """Score book-anchored d'un signal.

    Args:
        signal_row: dict avec keys title, summary, entities (JSON list tickers)

    Returns:
        {
          "score": int (0-100),
          "components": {kill: int, validation: int, urgency: int},
          "matched_tickers": [str],  # tickers du signal trouves dans le book
          "reasoning": str           # explication courte
        }
    """
    from shared import storage

    # Extract tickers from signal entities
    ents_raw = signal_row.get("entities") or ""
    if isinstance(ents_raw, str):
        try:
            ents = json.loads(ents_raw)
            if not isinstance(ents, list):
                ents = []
        except Exception:
            ents = []
    else:
        ents = ents_raw or []
    tickers = [str(t).upper() for t in ents if t]

    if not tickers:
        # Signal macro sans entites taggees -- on garde un score neutre 1
        # (pas zero pour ne pas le filtrer brutalement)
        return {
            "score": 1,
            "components": {"kill": 0, "validation": 0, "urgency": 0},
            "matched_tickers": [],
            "reasoning": "signal macro sans entites taggees",
        }

    bv = storage.get_book_view()
    # Filter tickers qui sont dans mon book
    matched = [t for t in tickers if bv.view_of(t) is not None]
    if not matched:
        return {
            "score": 0,
            "components": {"kill": 0, "validation": 0, "urgency": 0},
            "matched_tickers": [],
            "reasoning": "aucun ticker dans book canonique",
        }

    # Recupere les theses actives
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT ticker, key_drivers, invalidation_triggers "
            "FROM theses WHERE status='active' "
            f"AND ticker IN ({','.join('?' * len(matched))})",
            tuple(matched),
        ).fetchall()
    theses_by_tk: dict[str, dict] = {}
    for r in rows:
        kc_raw = r[2] or ""
        if isinstance(kc_raw, str) and kc_raw.strip().startswith("["):
            try:
                kc = json.loads(kc_raw)
                if not isinstance(kc, list):
                    kc = [str(kc)]
            except Exception:
                kc = [kc_raw]
        elif isinstance(kc_raw, str) and kc_raw.strip():
            kc = [kc_raw]
        else:
            kc = []
        claim_raw = r[1] or ""
        if isinstance(claim_raw, str) and claim_raw.startswith("["):
            try:
                kd = json.loads(claim_raw)
                claim = " ; ".join(kd) if isinstance(kd, list) else claim_raw
            except Exception:
                claim = claim_raw
        else:
            claim = claim_raw
        theses_by_tk[r[0]] = {"kill_criteria": kc, "claim": claim}

    signal_text = _extract_signal_text(signal_row)

    # Score per matched ticker, prendre le max (1 signal peut toucher plusieurs
    # positions ; le score reflete le ticker le plus impacte)
    best_score = 0
    best_components = {"kill": 0, "validation": 0, "urgency": 0}
    best_tk = None
    for tk in matched:
        th = theses_by_tk.get(tk) or {"kill_criteria": [], "claim": ""}
        pv = bv.view_of(tk)
        kill = _kill_match_score(signal_text, th["kill_criteria"])
        valid = _validation_match_score(signal_text, th["claim"])
        urgency = _margin_urgency_score(pv)
        total = kill + valid + urgency
        if total > best_score:
            best_score = total
            best_components = {"kill": kill, "validation": valid, "urgency": urgency}
            best_tk = tk

    reasoning_parts = [f"book match: {', '.join(matched[:3])}"]
    if best_components["kill"] >= 5:
        reasoning_parts.append(f"kill-criterion match ({best_tk})")
    if best_components["validation"] >= 3:
        reasoning_parts.append(f"validation driver ({best_tk})")
    if best_components["urgency"] >= 2:
        reasoning_parts.append(f"position tendue ({best_tk})")

    return {
        "score": best_score,
        "components": best_components,
        "matched_tickers": matched,
        "reasoning": " / ".join(reasoning_parts),
    }


def rank_signals_book_anchored(signal_rows: list[dict]) -> list[dict]:
    """Reranke une liste de signaux par score book-anchored DESC.

    Conserve l'ordre original en tie-break (deterministe).
    """
    scored = []
    for i, r in enumerate(signal_rows):
        result = score_signal_book_anchored(r)
        scored.append((-result["score"], i, r, result))
    scored.sort()
    return [{"signal": s[2], "book_score": s[3]} for s in scored]
