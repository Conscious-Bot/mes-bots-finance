"""Sprint 9.b — Chat-driven trade intent extraction + execution.

Quand le user dit dans le chat "je vais vendre 10 TSM a 195 car cluster trop
concentre", le bot extrait l'intent + execute le meme chemin que /position_sell
sur Telegram (positions_mod.add_sell + decision log + copilot pre-trade).

Pas d'auto-execution si l'intent est ambigu : confidence < 0.7 -> on demande
clarification. Si confidence >= 0.7 -> on execute et on annote la reponse.
"""

from __future__ import annotations

import logging

from shared import llm

log = logging.getLogger(__name__)

# Words/patterns that strongly suggest a trade intent (cheap pre-filter to
# avoid LLM call on every "quelle est ma fragilite ?" message).
_INTENT_KEYWORDS = (
    "je vais", "je vends", "vendre", "vente", "trim", "lighten", "alleger", "allege",
    "j'achete", "achete", "acheter", "renforce", "renforcer", "scale in", "scale-in",
    "je sors", "exit", "close", "je clos",
    "je rentre", "ouvrir", "entrer en", "buy", "sell",
)


def _looks_like_trade_intent(message: str) -> bool:
    m = message.lower()
    return any(kw in m for kw in _INTENT_KEYWORDS)


_INTENT_PROMPT = """Tu es un parseur d'intentions de trading. Le user vient d'ecrire ce message dans son chat :

\"\"\"
{message}
\"\"\"

Determine s'il EXPRIME UNE INTENTION DE TRADE (achat ou vente d'une position). Si OUI, extrait :
- action : "buy" | "sell"
- ticker : symbole exact (TSM, ASML.AS, 4063.T, etc.)
- qty : quantite si mentionnee (float, sinon null)
- price : prix d'execution si mentionne (float, sinon null — null = market)
- reasoning : la RAISON donnee par l'user, reformulee en 1 phrase claire

IMPORTANT :
- Si le message est juste une question ("quel est mon ticker le plus expose ?"), pas une intention -> intent=null.
- Si l'intention est trop vague ("je vais alleger un peu") sans ticker ou sans qty -> set intent mais low confidence.
- Si le user dit "je devrais peut-etre vendre" (conditionnel/hypothetique) -> ce n'est PAS une intention ferme, intent=null.
- Sois STRICT : intent ferme = "je vends", "je viens de vendre", "je vais vendre TICKER", pas "envisager".

Confidence (0-1) :
- 1.0 = ticker + qty + price + reasoning tous explicites
- 0.7 = ticker + qty explicites (prix manquant OK, on prendra le prix marche)
- 0.4 = ticker ou qty manquant
- 0.0 = pas un trade intent

Reponds UNIQUEMENT en JSON :
{{
  "intent": {{
    "action": "buy" | "sell",
    "ticker": "...",
    "qty": <float | null>,
    "price": <float | null>,
    "reasoning": "..."
  }} | null,
  "confidence": <0-1>,
  "clarification_needed": "..." | null
}}

Si intent=null, confidence=0 et clarification_needed=null.
Si intent fixe mais qty/price manque, clarification_needed = "Combien d'actions ?" ou "A quel prix ?".
"""


def extract_trade_intent(message: str) -> dict | None:
    """Parse a chat message ; return intent dict or None.

    Returns :
        None  -> not a trade intent (or pre-filter rejected)
        dict  -> {intent: {...} | None, confidence: float, clarification_needed: str | None}
    """
    if not _looks_like_trade_intent(message):
        return None
    try:
        # tier=extract = Haiku, cheap (~$0.001/call)
        result = llm.call_json(_INTENT_PROMPT.format(message=message), tier="extract", max_tokens=400)
        if isinstance(result, dict):
            return result
    except Exception as e:
        log.warning(f"extract_trade_intent failed: {e}")
    return None


def execute_intent(intent: dict, reasoning_fallback: str = "") -> dict:
    """Execute a parsed intent via the same primitives as /position_buy / /position_sell.

    Returns a dict :
        {
            "executed" : bool,
            "summary"  : str,  # human-readable summary for the chat reply
            "decision_id" : int | None,
            "copilot"  : dict | None,  # copilot brief if triggered
            "error"    : str | None,
        }
    """
    from intelligence import decision_copilot
    from shared import positions as positions_mod, storage

    action = intent.get("action")
    ticker = (intent.get("ticker") or "").upper()
    qty = intent.get("qty")
    price = intent.get("price")
    reasoning = (intent.get("reasoning") or reasoning_fallback or "").strip()

    if action not in ("buy", "sell"):
        return {"executed": False, "summary": "intent inconnu", "error": "bad_action"}
    if not ticker or not qty:
        return {"executed": False, "summary": "ticker ou qty manquant", "error": "incomplete"}

    # If price missing, try to use last_price from thesis or current market.
    if not price:
        try:
            from dashboard.render import _cached_price_eur

            price = _cached_price_eur(ticker) or 0
        except Exception:
            price = 0
    if not price:
        return {"executed": False, "summary": "prix indisponible", "error": "no_price"}

    qty = float(qty)
    price = float(price)

    # Detect dtype for copilot (entry / scale_in / partial_exit / full_exit)
    existing = None
    try:
        existing = positions_mod.get_position(ticker)
    except Exception as e:
        log.warning(f"get_position {ticker} failed: {e}")

    if action == "buy":
        dtype = "scale_in" if (existing and existing.get("qty", 0) > 0) else "entry"
    else:
        if existing and qty >= (existing.get("qty") or 0):
            dtype = "full_exit"
        else:
            dtype = "partial_exit"

    # 1. Copilot pre-trade (advisory)
    cop_resp, cop_iid = None, None
    if dtype != "entry":  # entry pre-mortem is handled at thesis creation
        try:
            cop_resp, cop_iid = decision_copilot.run_pre_trade_copilot(
                ticker=ticker, decision_type=dtype, reasoning=reasoning, price=price
            )
        except Exception as e:
            log.warning(f"copilot pre-trade failed for {ticker}: {e}")

    # 2. Execute trade via positions_mod (same as Telegram handlers)
    try:
        if action == "buy":
            positions_mod.add_buy(ticker, qty, price, reasoning + " | source=chat")
        else:
            positions_mod.add_sell(ticker, qty, price, reasoning + " | source=chat")
    except Exception as e:
        log.error(f"execute_intent trade failed: {e}")
        return {"executed": False, "summary": f"trade echoue: {e}", "error": str(e)}

    # 3. Log decision (same as Telegram)
    decision_id = None
    try:
        decision_id = storage.log_decision(
            ticker=ticker,
            decision_type=dtype,
            confidence=3,
            reasoning=reasoning,
            direction="long" if action == "buy" else "short",
            price_at_decision=price,
        )
    except Exception as e:
        log.warning(f"log_decision failed: {e}")

    # 4. Link copilot to decision
    if cop_iid and decision_id:
        try:
            storage.link_copilot_intervention_decision(cop_iid, decision_id)
        except Exception as e:
            log.warning(f"link_copilot_intervention_decision failed: {e}")

    eur_total = qty * price
    action_label = "ACHAT" if action == "buy" else "VENTE"
    cop_line = ""
    if cop_resp:
        verdict = cop_resp.get("verdict") or "?"
        score = cop_resp.get("pressure_score") or 0
        cop_line = f"\n→ Copilot pre-trade : **{verdict}** (pressure {score}). "
        if cop_resp.get("ancrage"):
            cop_line += cop_resp["ancrage"][:200]

    summary = (
        f"✅ {action_label} EXECUTE — {ticker} qty={qty:g} @ {price:.2f}€  "
        f"(total {eur_total:.0f}€, type={dtype}, decision_id={decision_id})"
        f"{cop_line}"
    )

    return {
        "executed": True,
        "summary": summary,
        "decision_id": decision_id,
        "copilot": cop_resp,
        "intent": intent,
        "error": None,
    }
