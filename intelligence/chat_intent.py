"""Sprint 9.b/9.c — Chat-driven intent extraction + execution dispatcher.

Le user ecrit en langue naturelle dans le chat. On extrait l'intent (Haiku
tier=extract, cheap) puis on EXECUTE via les MEMES primitives que les slash
commands Telegram. Pas de duplication de logique.

Kinds supportes :
  Mutations (ecrivent la DB, declenchent copilot quand pertinent) :
    - buy            -> positions_mod.add_buy + log_decision + copilot
    - sell           -> positions_mod.add_sell + log_decision + copilot
    - set_field      -> storage UPDATE theses SET <field>=<value>
    - close_thesis   -> storage.close_thesis + check_exit_request
    - revisit_thesis -> storage.update_thesis_revisit + build_revisit_questions
    - override       -> record_override + copilot (partial/full/stop)
  Reads (ne mutent rien, retournent un block injecte dans la reponse) :
    - simulate_trade -> portfolio_grade.simulate_grade (avant/apres)
    - show_grade     -> portfolio_grade.compute_grade (ou latest snapshot)
    - show_brief     -> morning_brief.build_brief
    - show_asymmetry -> asymmetry.compute_thesis_asymmetry / portfolio
    - show_position  -> positions_mod.get_position + format_position_detail
"""

from __future__ import annotations

import logging
from typing import Any

from shared import llm

log = logging.getLogger(__name__)

# Cheap keyword pre-filter (skip LLM call on pure conversation).
_INTENT_KEYWORDS = (
    # buy/sell — toutes formes (present, passe, conditionnel proche)
    "vendre", "vends", "vendu", "vendue", "vendrai", "vente",
    "trim", "alleger", "allege", "lighten",
    "acheter", "achete", "achetee", "achat",
    "renforce", "renforcer", "bump", "scale in", "scale-in",
    "exit", "close", "clos", "ouvrir", "entrer en", "buy", "sell",
    "nouvelle position", "create position", "ouvert", "ouverte",
    # mutations
    "passe la conviction", "conviction", "stop a", "stop_price",
    "target", "cible a", "cible_partial", "cible_full", "objectif",
    "ferme la these", "close la these", "force exit", "exit force",
    "revisit", "revue la these",
    "override", "override partial", "override full", "override stop",
    # reads
    "simul", "simule", "sim", "what-if", "que se passe",
    "montre", "montre-moi", "donne-moi", "affiche", "show",
    "note du pf", "le grade", "le brief", "brief du matin",
    "asymetrie", "asymmetry", "position de", "ma position", "etat de",
    # full analysis
    "analyse", "analyze", "fiche", "analyse complete", "fiche complete",
    "deep dive", "details sur", "dossier", "raconte",
)


def _looks_like_intent(message: str) -> bool:
    m = message.lower()
    return any(kw in m for kw in _INTENT_KEYWORDS)


_INTENT_PROMPT = """Tu es un parseur d'intentions pour un investisseur. Le message :

\"\"\"
{message}
\"\"\"

Detecte si l'user EXPRIME UNE OU PLUSIEURS INTENTIONS ACTIONNABLES. Un seul
message peut contenir PLUSIEURS trades (compound) — extrait-les TOUTES dans
le tableau "intents".

Pour chaque intent, choisis le `kind` parmi :

MUTATIONS (ecrivent la DB) :
  - "buy"            : intention ferme d'achat (qty+ticker minimum)
  - "sell"           : intention ferme de vente (qty+ticker minimum)
  - "set_field"      : modifier un champ d'une these (conviction/stop/target/notes)
  - "close_thesis"   : fermer une these (regret_driven ou trigger_met)
  - "revisit_thesis" : revue / questionnement mensuel d'une these
  - "override"       : override de la sortie definie (partial/full/stop)

READS (informent, ne mutent rien) :
  - "simulate_trade" : simuler l'impact d'un trade hypothetique
  - "show_grade"     : afficher la note du PF
  - "show_brief"     : afficher le brief du matin
  - "show_asymmetry" : afficher l'asymetrie risk/reward
  - "show_position"  : afficher le detail d'une position
  - "show_analysis"  : afficher l'analyse complete d'un ticker (BUSINESS QUALITY +
                      FINANCIAL HEALTH + valo) — equivalent /analyze TICKER

REGLES :
- Conditionnel ("je devrais peut-etre vendre", "et si je vendais") = PAS ferme. Si l'user demande hypothetique sur un trade = "simulate_trade".
- Une question pure ("quelle est ma fragilite ?") = pas d'intent (intent=null).
- "passe la conviction de TSM a 4" = set_field {{ticker:TSM, field:conviction, value:4}}
- "stop TSM a 180" = set_field {{ticker:TSM, field:stop_price, value:180}}
- "ferme la these CCJ car invalide" = close_thesis {{ticker:CCJ, reason:...}}
- "ma position TSM" = show_position {{ticker:TSM}}
- "analyse complete TSLA" / "raconte-moi 4063.T" / "fiche TSM" = show_analysis {{ticker:TSLA}}
- "et si je vends 5 ASML a 800 ?" = simulate_trade {{action:sell, ticker:ASML, qty:5, price:800}}

EUR vs QTY :
  - "vendu 12 actions de VRT a 70" -> qty=12, price=70
  - "vendu 834 euros de VRT" / "vendu VRT (834)" -> eur_amount=834, qty=null
  - "vendu l'entierete de VRT" / "tout VRT" -> full_exit=true, qty=null
  - "achete pour 1000 euros de CCJ" / "+1000 sur CCJ" -> eur_amount=1000
  - "nouvelle position SNOW 1450" -> kind=buy, eur_amount=1450
Le serveur convertira eur_amount -> qty via le prix courant.

Sortie JSON (tableau intents, meme si une seule action) :
{{
  "intents": [
    {{
      "kind": "<one of above>",
      "ticker": "...",
      "qty": <float|null>,
      "price": <float|null>,
      "eur_amount": <float|null>,
      "full_exit": <true|false>,
      "field": "conviction|stop_price|target_partial|target_full|entry_price|notes|horizon|status",
      "value": "...",
      "level": "partial|full|stop",
      "reason": "...",
      "action": "buy|sell",
      "reasoning": "..."
    }}
  ] | [],
  "confidence": <0-1>,
  "clarification_needed": "..." | null
}}

Confidence (sur l'ensemble) :
- 1.0  = tous params explicites pour tous les intents
- 0.7  = action+ticker explicites, EUR/qty inferable
- 0.4  = ambigu, manque ticker ou montant
- 0.0  = pas d'intention actionnable

Si rien d'actionnable, intents=[] et confidence=0.

EXEMPLE (compound) :
  "vendu tout VRT (834) et tout TER (1125), bump CCJ de +1000, nouvelle position SNOW 1450"
  -> intents = [
       {{kind:"sell", ticker:"VRT", full_exit:true, eur_amount:834}},
       {{kind:"sell", ticker:"TER", full_exit:true, eur_amount:1125}},
       {{kind:"buy", ticker:"CCJ", eur_amount:1000, reasoning:"bump"}},
       {{kind:"buy", ticker:"SNOW", eur_amount:1450, reasoning:"nouvelle position"}}
     ]
     confidence: 0.85
"""


def extract_intent(message: str) -> dict | None:
    """Parse a chat message ; return {intents: [...], confidence, ...} or None.

    Sprint 19 : retourne maintenant une LISTE d'intents pour supporter les
    messages compound ("vendu tout VRT et TER, bump CCJ, nouvelle SNOW").
    Backwards-compat : si l'LLM retourne {intent: ...} singleton (ancien
    format), on le wrap en intents: [...].
    """
    if not _looks_like_intent(message):
        return None
    try:
        result = llm.call_json(_INTENT_PROMPT.format(message=message), tier="extract", max_tokens=900)
        if not isinstance(result, dict):
            return None
        # Backwards-compat : single intent -> list
        if "intent" in result and "intents" not in result:
            single = result.pop("intent")
            result["intents"] = [single] if single else []
        # Normalize : ensure intents is a list
        if "intents" not in result or not isinstance(result["intents"], list):
            result["intents"] = []
        return result
    except Exception as e:
        log.warning(f"extract_intent failed: {e}")
    return None


# Backwards-compat alias (Sprint 9.b used extract_trade_intent for buy/sell only).
def extract_trade_intent(message: str) -> dict | None:
    parsed = extract_intent(message)
    if not parsed:
        return None
    intent = parsed.get("intent") or {}
    if intent.get("kind") in ("buy", "sell"):
        # Reshape for legacy callers : intent.action = kind
        intent["action"] = intent["kind"]
        return parsed
    return None


# =============================================================================
# DISPATCHERS — execute_intent switches on intent.kind
# =============================================================================


def execute_intents(intents: list[dict], reasoning_fallback: str = "") -> dict:
    """Execute multiple intents in sequence. Returns aggregated result.

    Each intent runs through execute_intent. Errors don't stop the chain :
    we report success/failure per intent so the user sees the partial state.
    """
    if not intents:
        return {"executed": False, "summary": "aucun intent", "n_executed": 0}
    results = []
    summaries = []
    n_ok = n_fail = 0
    for it in intents:
        r = execute_intent(it, reasoning_fallback=reasoning_fallback)
        results.append(r)
        if r.get("executed"):
            n_ok += 1
        else:
            n_fail += 1
        summaries.append(r.get("summary", ""))
    return {
        "executed": n_ok > 0,
        "n_executed": n_ok,
        "n_failed": n_fail,
        "n_total": len(intents),
        "results": results,
        "summary": "\n\n".join(summaries),
    }


def execute_intent(intent: dict, reasoning_fallback: str = "") -> dict:
    """Dispatch by intent.kind. Returns {executed, summary, error, ...}."""
    kind = (intent or {}).get("kind") or intent.get("action")  # legacy buy/sell shape
    if not kind:
        return {"executed": False, "summary": "intent inconnu (kind absent)", "error": "no_kind"}
    handlers = {
        "buy": _exec_buy_sell,
        "sell": _exec_buy_sell,
        "set_field": _exec_set_field,
        "close_thesis": _exec_close_thesis,
        "revisit_thesis": _exec_revisit_thesis,
        "override": _exec_override,
        "simulate_trade": _exec_simulate_trade,
        "show_grade": _exec_show_grade,
        "show_brief": _exec_show_brief,
        "show_asymmetry": _exec_show_asymmetry,
        "show_position": _exec_show_position,
        "show_analysis": _exec_show_analysis,
    }
    h = handlers.get(kind)
    if not h:
        return {"executed": False, "summary": f"kind={kind} non supporte", "error": "unsupported_kind"}
    try:
        return h(intent, reasoning_fallback)
    except Exception as e:
        log.exception(f"execute_intent {kind} crashed: {e}")
        return {"executed": False, "summary": f"crash dispatcher {kind}: {e}", "error": str(e)}


# -----------------------------------------------------------------------------
# Mutations
# -----------------------------------------------------------------------------


def _exec_buy_sell(intent: dict, reasoning_fallback: str) -> dict:
    """Mirror /position_buy /position_sell handlers.

    Sprint 19 : support eur_amount (converti en qty via prix courant) +
    full_exit=true (vend toute la position existante).
    """
    from intelligence import decision_copilot
    from shared import positions as positions_mod, storage

    action = intent.get("action") or intent.get("kind")
    ticker = (intent.get("ticker") or "").upper()
    qty = intent.get("qty")
    price = intent.get("price")
    eur_amount = intent.get("eur_amount")
    full_exit_flag = bool(intent.get("full_exit"))
    reasoning = (intent.get("reasoning") or reasoning_fallback or "").strip()

    if action not in ("buy", "sell"):
        return {"executed": False, "summary": "action inconnue", "error": "bad_action"}
    if not ticker:
        return {"executed": False, "summary": "ticker manquant", "error": "incomplete"}

    # Get price (live cached) if not specified
    if not price:
        try:
            from dashboard.render import _cached_price_eur

            price = _cached_price_eur(ticker) or 0
        except Exception:
            price = 0
    if not price:
        return {"executed": False, "summary": f"prix indisponible pour {ticker}", "error": "no_price"}
    price = float(price)

    existing = positions_mod.get_position(ticker)

    # Sprint 19 : resolve qty from full_exit OR eur_amount OR explicit qty
    if action == "sell" and full_exit_flag:
        if not existing or not existing.get("qty"):
            return {"executed": False, "summary": f"full_exit demande mais pas de position sur {ticker}", "error": "no_position"}
        qty = float(existing["qty"])
    elif eur_amount and not qty:
        qty = round(float(eur_amount) / price, 4)
    elif not qty:
        return {"executed": False, "summary": "qty / eur_amount / full_exit manquant", "error": "incomplete"}

    qty = float(qty)

    if action == "buy":
        dtype = "scale_in" if (existing and existing.get("qty", 0) > 0) else "entry"
    else:
        dtype = "full_exit" if (existing and qty >= (existing.get("qty") or 0) - 1e-6) else "partial_exit"

    # Boucle-de-soi V0 re-injection : si sell-winner detecte ET measure_bias
    # montre un cout cumule, on enrichit le reasoning avec le contexte de biais.
    # Le copilot LLM voit le chiffre et peut le citer dans son verdict.
    if dtype in ("partial_exit", "full_exit") and existing:
        try:
            from intelligence import self_loop as _sl

            _entry = (existing.get("avg_cost") or 0)
            _pnl_pct = ((price - _entry) / _entry * 100) if _entry > 0 else None
            _held = None
            _opened = existing.get("opened_at")
            if _opened:
                from datetime import UTC as _UTC, datetime as _dt
                try:
                    _od = _dt.fromisoformat(_opened.replace("Z", "+00:00"))
                    if _od.tzinfo is None:
                        _od = _od.replace(tzinfo=_UTC)
                    _held = (_dt.now(_UTC) - _od).days
                except Exception:
                    _held = None
            _bias_ctx = _sl.bias_context_for_prompt(
                ticker, dtype, current_pnl_pct=_pnl_pct, held_days=_held
            )
            if _bias_ctx:
                reasoning = (reasoning or "") + "\n\n" + _bias_ctx
        except Exception as _e:
            log.warning(f"self_loop bias_context_for_prompt failed: {_e}")

    cop_resp, cop_iid = None, None
    if dtype != "entry":
        try:
            cop_resp, cop_iid = decision_copilot.run_pre_trade_copilot(
                ticker=ticker, decision_type=dtype, reasoning=reasoning, price=price
            )
        except Exception as e:
            log.warning(f"copilot pre-trade {ticker}: {e}")

    # SNAPSHOT PRE-EXECUTION pour la boucle-de-soi (V0 ancre contrefactuelle).
    # Capture qty AVANT le sell -- c'est l'ancre du "hold strict" contrefactuel.
    # Doit etre fait AVANT add_sell, sinon l'ancre est faussee.
    _anchor_qty_before = (existing.get("qty") if existing else 0) or 0
    _anchor_conviction = None
    _anchor_thesis_id = None
    try:
        with storage.db() as _cx:
            _th = _cx.execute(
                "SELECT id, conviction FROM theses WHERE ticker=? AND status='active' "
                "ORDER BY id DESC LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            if _th:
                _anchor_thesis_id = _th[0]
                _anchor_conviction = _th[1]
    except Exception:
        pass

    if action == "buy":
        positions_mod.add_buy(ticker, qty, price, reasoning + " | source=chat")
    else:
        positions_mod.add_sell(ticker, qty, price, reasoning + " | source=chat")

    # thesis_id deja recupere pour l'ancre, reutiliser
    thesis_id = _anchor_thesis_id

    decision_id = storage.log_decision(
        ticker=ticker,
        decision_type=dtype,
        confidence=3,
        reasoning=reasoning,
        direction="long" if action == "buy" else "short",
        price_at_decision=price,
        thesis_id=thesis_id,
    )

    # Boucle-de-soi V0 : capture l'ancre contrefactuelle juste apres
    # log_decision (besoin de decision_id). Branche = "hold" pour sells,
    # "would_have_sold" pour buy (V1 etendra, V0 ne traque que les sells).
    if decision_id and dtype in ("partial_exit", "full_exit", "scale_in"):
        try:
            from intelligence import self_loop as _sl
            from shared import edgar as _edgar

            # Bias hypothese auto-tag : winner sell = candidat biais #1
            _bias_hyp = []
            if dtype in ("partial_exit", "full_exit") and existing:
                _entry = existing.get("avg_cost") or 0
                if _entry > 0 and (price - _entry) / _entry > 0.10:
                    _bias_hyp.append("vend_winners_trop_tot")

            _currency = _edgar.get_currency_for_ticker(ticker) if hasattr(_edgar, "get_currency_for_ticker") else None
            _sl.record_anchor(
                decision_id=decision_id,
                ticker=ticker,
                decision_type=dtype,
                qty_before=_anchor_qty_before,
                price_at_decision=price,
                price_at_decision_eur=price,
                currency=_currency,
                thesis_id=_anchor_thesis_id,
                conviction_at_t0=_anchor_conviction,
                bias_hypothesis=_bias_hyp,
                reasoning=reasoning,
                counterfactual_branch="hold" if dtype != "scale_in" else "would_have_sold",
            )
        except Exception as _e:
            log.warning(f"self_loop record_anchor failed {ticker}: {_e}")
    if cop_iid and decision_id:
        try:
            storage.link_copilot_intervention_decision(cop_iid, decision_id)
        except Exception as e:
            log.warning(f"link copilot/decision: {e}")

    eur_total = qty * price
    label = "ACHAT" if action == "buy" else "VENTE"
    cop_line = ""
    if cop_resp:
        ver = cop_resp.get("verdict") or "?"
        ps = cop_resp.get("pressure_score") or 0
        cop_line = f"\n→ Copilot : **{ver}** (pressure {ps}). {(cop_resp.get('ancrage') or '')[:200]}"

    return {
        "executed": True,
        "summary": (
            f"✅ {label} EXECUTE — {ticker} qty={qty:g} @ {price:.2f}€ "
            f"(total {eur_total:.0f}€, type={dtype}, decision_id={decision_id}){cop_line}"
        ),
        "decision_id": decision_id,
        "copilot": cop_resp,
    }


def _exec_set_field(intent: dict, _: str) -> dict:
    """Mirror /thesis_set TICKER FIELD VALUE via shared/storage helper."""
    from shared import storage

    ticker = intent.get("ticker") or ""
    field = intent.get("field") or ""
    value = intent.get("value")
    if not ticker or not field or value is None:
        return {"executed": False, "summary": "ticker/field/value manquant", "error": "incomplete"}
    ok, msg, old_val = storage.update_thesis_field(ticker, field, value)
    if not ok:
        return {"executed": False, "summary": msg, "error": "rejected"}
    return {"executed": True, "summary": f"✅ {msg}", "field": field, "old": old_val, "new": value}


def _exec_close_thesis(intent: dict, _: str) -> dict:
    """Mirror /exit_force TICKER reason (regret-tagged)."""
    from intelligence import thesis as thesis_mod
    from shared import storage

    ticker = (intent.get("ticker") or "").upper()
    reason = (intent.get("reason") or "").strip()
    if not ticker or not reason:
        return {"executed": False, "summary": "ticker ou raison manquant", "error": "incomplete"}
    t = storage.get_thesis_by_ticker(ticker, status="active")
    if not t:
        return {"executed": False, "summary": f"pas de these active sur {ticker}", "error": "no_thesis"}
    try:
        check = thesis_mod.check_exit_request(ticker)
        note_suffix = "[regret_driven]" if check.get("status") == "no_trigger" else "[trigger_met]"
    except Exception:
        note_suffix = "[regret_driven]"
    storage.close_thesis(t["id"], status="realized", reason=f"{note_suffix} {reason}")
    return {
        "executed": True,
        "summary": f"✅ These {ticker} fermee 'realized' {note_suffix}. Raison : {reason}",
        "thesis_id": t["id"],
    }


def _exec_revisit_thesis(intent: dict, _: str) -> dict:
    """Mirror /thesis_revisit TICKER."""
    from intelligence import thesis as thesis_mod
    from shared import storage

    ticker = (intent.get("ticker") or "").upper()
    if not ticker:
        return {"executed": False, "summary": "ticker manquant", "error": "incomplete"}
    t = storage.get_thesis_by_ticker(ticker)
    if not t:
        return {"executed": False, "summary": f"these introuvable : {ticker}", "error": "no_thesis"}
    questions = thesis_mod.build_revisit_questions(t)
    storage.update_thesis_revisit(t["id"])
    return {
        "executed": True,
        "summary": f"✅ Revisit marque sur {ticker} (#{t['id']})\n\n{questions}",
        "thesis_id": t["id"],
    }


def _exec_override(intent: dict, _: str) -> dict:
    """Mirror /override TICKER level reason."""
    from intelligence import decision_copilot
    from intelligence.price_monitor import record_override
    from shared import storage

    ticker = (intent.get("ticker") or "").upper()
    level = (intent.get("level") or "").lower()
    reason = (intent.get("reason") or "").strip()
    if not ticker or level not in ("partial", "full", "stop") or not reason:
        return {"executed": False, "summary": "ticker/level/reason manquant ou level != partial|full|stop", "error": "incomplete"}
    dtype = {"partial": "partial_exit", "full": "full_exit", "stop": "override"}.get(level, "override")
    cop_resp: Any = None
    try:
        t = storage.get_thesis_by_ticker(ticker, status="active") or {}
        cp_price = t.get("last_price") or t.get("entry_price") or 0
        _cp_out = decision_copilot.run_pre_trade_copilot(
            ticker=ticker, decision_type=dtype, reasoning=reason, price=cp_price
        )
        cop_resp = _cp_out[0] if _cp_out else None
    except Exception as e:
        log.warning(f"copilot pre-trade override {ticker}: {e}")
    try:
        record_override(ticker, level, reason)
    except Exception as e:
        return {"executed": False, "summary": f"record_override echoue: {e}", "error": str(e)}
    cop_line = ""
    if cop_resp:
        ver = cop_resp.get("verdict") or "?"
        ps = cop_resp.get("pressure_score") or 0
        cop_line = f"\n→ Copilot : **{ver}** (pressure {ps}). {(cop_resp.get('ancrage') or '')[:200]}"
    return {
        "executed": True,
        "summary": f"✅ Override {level} enregistre sur {ticker}. Raison : {reason}{cop_line}",
        "copilot": cop_resp,
    }


# -----------------------------------------------------------------------------
# Reads
# -----------------------------------------------------------------------------


def _exec_simulate_trade(intent: dict, _: str) -> dict:
    """Mirror /grade sim TICKER buy|sell QTY [PRICE]."""
    from intelligence import portfolio_grade as _grade

    ticker = (intent.get("ticker") or "").upper()
    action = (intent.get("action") or "").lower()
    qty = intent.get("qty")
    price = intent.get("price") or 0
    if not ticker or action not in ("buy", "sell") or not qty:
        return {"executed": False, "summary": "ticker/action/qty manquant", "error": "incomplete"}
    if not price:
        try:
            from dashboard.render import _cached_price_eur

            price = _cached_price_eur(ticker) or 0
        except Exception:
            price = 0
    sim = _grade.simulate_grade(
        {"type": "full_exit" if (action == "sell" and intent.get("full_exit")) else action,
         "ticker": ticker, "qty": float(qty), "price_eur": float(price)}
    )
    delta = sim["delta_score"]
    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "·")
    diag = "\n".join(f"  · {d}" for d in (sim["diagnosis"] or ["aucune dim ne bouge >=5pts"]))
    return {
        "executed": True,
        "summary": (
            f"📊 SIM {action} {ticker} qty={qty} @ {price:.2f}€\n"
            f"Avant : {sim['before']['overall_grade']} ({sim['before']['overall_score']}/100)\n"
            f"Après : {sim['after']['overall_grade']} ({sim['after']['overall_score']}/100)\n"
            f"Δ {arrow} {delta:+d} pts\n\nDimensions qui bougent :\n{diag}"
        ),
        "simulation": sim,
    }


def _exec_show_grade(_: dict, __: str) -> dict:
    from intelligence import portfolio_grade as _grade
    from shared import storage as _stg

    latest = _stg.get_latest_portfolio_grade()
    if not latest:
        g = _grade.compute_grade()
        return {
            "executed": True,
            "summary": f"📊 Note PF actuelle : {g['overall_grade']} ({g['overall_score']}/100) — snapshot J0",
        }
    return {
        "executed": True,
        "summary": (
            f"📊 Note PF : {latest['overall_grade']} ({latest['overall_score']}/100) "
            f"au {latest.get('snapshot_date','?')}"
        ),
    }


def _exec_show_brief(_: dict, __: str) -> dict:
    """Wraps morning_brief.build_brief — peut etre lent."""
    try:
        from intelligence import morning_brief as mb

        brief = mb.build_brief()
        chunks = mb.format_brief(brief) or []
        text = "\n\n".join(chunks)[:2500]
    except Exception as e:
        return {"executed": False, "summary": f"brief failed: {e}", "error": str(e)}
    return {"executed": True, "summary": f"☀️ Brief du matin :\n\n{text}"}


def _exec_show_asymmetry(intent: dict, _: str) -> dict:
    from intelligence import asymmetry as asym_mod
    from shared import storage

    ticker = (intent.get("ticker") or "").upper()
    if ticker:
        t = storage.get_thesis_by_ticker(ticker, status="active")
        if not t:
            return {"executed": False, "summary": f"pas de these active sur {ticker}", "error": "no_thesis"}
        r = asym_mod.compute_thesis_asymmetry(t)
        if not r:
            return {"executed": False, "summary": f"asymetrie indispo pour {ticker}", "error": "no_data"}
        return {"executed": True, "summary": "⚖️ " + asym_mod.format_asymmetry_single(r)[:2500]}
    results = asym_mod.compute_portfolio_asymmetry()
    return {"executed": True, "summary": "⚖️ " + asym_mod.format_portfolio_asymmetry(results)[:2500]}


# =============================================================================
# PASSIVE EXTRACTION (Sprint 9.d) — tout message lambda devient une mine d'info
# =============================================================================

_PASSIVE_PROMPT = """Tu extrais des SIGNAUX SOFT (PAS des actions) depuis un message chat.

Un signal soft = une opinion / un doute / une preoccupation / un endorsement
qu'un investisseur laisse echapper EN CONVERSATION, sans formaliser. Ces
signaux nourrissent la comprehension de son thinking au fil du temps.

Message :

\"\"\"
{message}
\"\"\"

KINDS possibles (extraits SEULEMENT si presents, sinon ignore) :
  - concern              : doute / inquietude exprimee ("TSLA me fait peur")
  - conviction_drift     : changement subtil de conviction ("plus j'y pense plus je doute de CCJ")
  - conviction_endorse   : renforcement subtil ("je crois vraiment a la these MP")
  - topic_interest       : interet pour un sujet ("j'ai lu sur les terres rares")
  - sentiment            : sentiment positif/negatif general ("AI overcrowded")
  - heuristic            : mental model exprime ("je sors si la these change pas en 30j")
  - sector_view          : vue sur un secteur ("defense devient overcrowded")
  - thematic_view        : vue sur un theme ("HBM cycle pas convaincant")
  - blind_spot           : reconnaissance d'angle mort ("je connais mal pharma")

REGLES :
- N'INVENTE PAS. Si rien de saillant -> retourne {{"signals": []}}.
- Cite TOUJOURS evidence_quote = extrait exact du message qui supporte.
- Pas de signal sur les questions purement informationnelles ("quelle est ma fragilite ?").
- Signaux de trade explicites (buy/sell) sont DEJA captes ailleurs, ignore-les ici.
- Plusieurs signaux possibles dans 1 message.

Sortie JSON :
{{
  "signals": [
    {{
      "kind": "concern|conviction_drift|conviction_endorse|topic_interest|sentiment|heuristic|sector_view|thematic_view|blind_spot",
      "ticker": "TKR" | null,
      "sector": "..." | null,
      "theme": "..." | null,
      "valence": <-1 a +1 ; negatif = doute/concern, positif = endorsement>,
      "confidence": <0-1>,
      "evidence_quote": "...",
      "note": "interpretation 1 phrase"
    }}
  ]
}}
"""


def extract_passive_signals(message: str, chat_message_id: int | None = None) -> list[int]:
    """Extract soft signals from a chat message + persist them.

    Skips obvious questions and very short messages. Returns list of inserted
    signal ids. Silent failure (best-effort).
    """
    if not message or len(message.strip()) < 12:
        return []
    # Skip pure interrogatives (heuristic — questions are captured as concerns
    # only via 'concern' kind which the prompt explicitly excludes for info-only Qs)
    try:
        from shared import llm, storage

        result = llm.call_json(_PASSIVE_PROMPT.format(message=message), tier="extract", max_tokens=600)
    except Exception as e:
        log.warning(f"extract_passive_signals failed: {e}")
        return []
    if not isinstance(result, dict):
        return []
    signals = result.get("signals") or []
    ids: list[int] = []
    for s in signals:
        if not isinstance(s, dict) or not s.get("kind"):
            continue
        s_kind = str(s.get("kind"))
        sid = storage.insert_chat_signal(
            chat_message_id=chat_message_id,
            kind=s_kind,
            ticker=(s.get("ticker") or None),
            sector=(s.get("sector") or None),
            theme=(s.get("theme") or None),
            valence=s.get("valence"),
            confidence=s.get("confidence"),
            evidence_quote=(s.get("evidence_quote") or "")[:500],
            note=(s.get("note") or "")[:400],
        )
        if sid:
            ids.append(sid)
    return ids


def _exec_show_position(intent: dict, _: str) -> dict:
    from shared import positions as positions_mod

    ticker = (intent.get("ticker") or "").upper()
    if not ticker:
        return {"executed": False, "summary": "ticker manquant", "error": "incomplete"}
    p = positions_mod.get_position(ticker)
    if not p:
        return {"executed": False, "summary": f"pas de position ouverte sur {ticker}", "error": "no_position"}
    hist = positions_mod.get_history(ticker)
    return {"executed": True, "summary": "📍 " + positions_mod.format_position_detail(p, hist)[:2500]}


def _exec_show_analysis(intent: dict, _: str) -> dict:
    """Mirror /analyze TICKER. Prefer cached analysis (<=7j), fallback fresh gen.

    L'analyse complete reste le contenu integral (BUSINESS QUALITY +
    FINANCIAL HEALTH + valo) — pas le smart_summary qui sert juste la
    drilldown popup.
    """
    from shared import storage

    ticker = (intent.get("ticker") or "").upper()
    if not ticker:
        return {"executed": False, "summary": "ticker manquant", "error": "incomplete"}

    try:
        with storage.db() as cx:
            row = cx.execute(
                "SELECT timestamp, content FROM analyses WHERE ticker=? "
                "ORDER BY id DESC LIMIT 1",
                (ticker,),
            ).fetchone()
    except Exception:
        row = None

    if row and row[1]:
        ts = (row[0] or "")[:10]
        content = str(row[1])[:3500]
        return {
            "executed": True,
            "summary": f"📊 ANALYSE {ticker} (cache au {ts})\n\n{content}",
            "source": "cached",
        }
    # No cache : invite to /analyze rather than blow $0.20 silently
    return {
        "executed": True,
        "summary": (
            f"Pas d'analyse en cache pour {ticker}. "
            f"Lance /analyze {ticker} sur Telegram pour generer "
            f"(15-30s, ~$0.20). L'analyse sera ensuite disponible dans le chat."
        ),
        "source": "no_cache",
    }
