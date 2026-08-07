"""Position Card V3 — l'unité fondamentale de PRESAGE (doctrine gravée 07/08/2026).

LE RENVERSEMENT (dicté O., critiques du 07/08)
----------------------------------------------
Le dashboard n'est plus le produit : il devient un index de Position Cards.
Tout le système converge vers la carte (tribunaux, hypothèses, contrefactuels,
biais, voyage, kill-criteria l'alimentent). La carte est organisée autour de
LA DÉCISION, pas autour de la ligne : ses blocs sont des QUESTIONS verbales,
et chaque donnée vit dans le bloc dont elle répond la question — plus jamais
groupée par table source.

LES 9 PRINCIPES (chacun tue un défaut observé sur les 2 générations d'avant)
----------------------------------------------------------------------------
P1  Ordre = questions du décideur : DOIS-JE AGIR ? → POURQUOI ? → QU'EST-CE
    QUI ME FERA CHANGER D'AVIS ? La carte ASML répondait à la 1re question
    après trois écrans — défaut mortel.
P2  Un datum n'existe que s'il peut changer une décision. Beta, PE, ISIN,
    market cap, TYPE&FACTOR : morts. C'est le test d'admission de tout champ.
P3  M1 partout — chaque nombre porte (valeur, asof, source). Une baseline de
    trigger sans date est un mensonge en devenir.
P4  Fail-honest — un étage sans données le DIT (« CF : aucun », « variant à
    écrire », « distance non instrumentée »). Jamais du vide qui ressemble à
    du calme (L31). La distance d'un trigger non mesurable ne s'invente pas
    (L15) : elle s'affiche non instrumentée.
P5  « Rien » est un verdict de première classe, daté du prochain fait qui
    pourrait le changer — et qualifié par le COÛT DE L'INACTION (règle
    mécanique déclarée, jamais un ressenti) :
        ÉLEVÉ  = over_cap actif OU kill at_risk/triggered OU fait daté ≤ 7 j
        MOYEN  = fait daté ≤ 30 j OU verdict contrefactuel pending
        FAIBLE = sinon
    La ligne affiche toujours sa raison, jamais le niveau seul.
P6  Une carte = un écran. Un seul trigger visible (état ≠ dormant, sinon
    baseline mesurable, sinon T1 déclaré) — les autres comptés « masqués ».
    Une seule leçon (CF dû > exposition ouverte > CF résolu > similaire >
    « historique jeune »).
P7  La carte LIT, ne recalcule jamais (L1/L4) : CardInputs + SteerOutput
    sont l'unique matière. Zéro re-query dans le render.
P8  La question de propriété ouvre chaque carte, avec l'état qui évite les
    faux oui : « oui · non · seulement à un meilleur prix ».
P9  20 SECONDES. Si après 20 s le lecteur ne sait pas s'il doit agir,
    pourquoi il détient, et ce qui le ferait changer d'avis — l'excédent
    n'appartient pas à la carte mais à une vue d'investigation.

COULEUR = RESSOURCE RARE : uniquement le verdict AGIR et le bandeau
fail-closed. Tout le reste monochrome — si tout est orange, rien n'est urgent.
"""
from __future__ import annotations

import contextlib
import html as _html
import json
import re
from typing import Any

#: Seuils du coût de l'inaction (P5) — jours avant un fait daté.
INACTION_HIGH_DAYS: int = 7
INACTION_MEDIUM_DAYS: int = 30

#: Un trigger est « mesurable » s'il porte un chiffre ancrable (baseline datée,
#: %, montant). Heuristique DÉCLARÉE — pas une distance : le choix du trigger
#: affiché, pas un score (L15).
_MEASURABLE_RE = re.compile(r"baseline|[\d,.]+\s*%|[€$¥₩]\s*\d|\d{2,}", re.I)


def _esc(t: Any) -> str:
    return _html.escape(str(t or ""))


def _days_until(date_iso: str | None, today: str) -> int | None:
    if not date_iso:
        return None
    with contextlib.suppress(Exception):
        from datetime import date
        d = date.fromisoformat(str(date_iso)[:10])
        return (d - date.fromisoformat(today[:10])).days
    return None


def _next_dated_fact(inputs: Any, today: str) -> tuple[str, str] | None:
    """(label, date) du prochain fait DATÉ du système. Aucune invention (P4)."""
    facts: list[tuple[str, str]] = []
    ev = inputs.next_event or None
    if ev and ev.get("date"):
        facts.append((str(ev.get("description") or "événement")[:40], str(ev["date"])[:10]))
    cf = inputs.last_cf or None
    if cf and cf.get("state") != "resolved" and cf.get("due"):
        facts.append((f"verdict CF ({_esc(cf.get('decision_type'))})", str(cf["due"])[:10]))
    facts = [f for f in facts if _days_until(f[1], today) is not None]
    return min(facts, key=lambda f: f[1]) if facts else None


def cost_of_inaction(inputs: Any, next_fact: tuple[str, str] | None, today: str) -> tuple[str, str]:
    """(niveau, raison) — règle mécanique P5, la raison est obligatoire."""
    if (inputs.over_cap_status or "") == "over":
        return "ÉLEVÉ", "over_cap actif — chaque jour tenu est de l'exposition non conforme"
    if (inputs.kill_status or "") in ("at_risk", "triggered"):
        return "ÉLEVÉ", f"kill-criterion {inputs.kill_status}"
    dj = _days_until(next_fact[1], today) if next_fact else None
    if dj is not None and dj <= INACTION_HIGH_DAYS:
        return "ÉLEVÉ", f"{next_fact[0]} dans {dj} j"
    if dj is not None and dj <= INACTION_MEDIUM_DAYS:
        return "MOYEN", f"{next_fact[0]} dans {dj} j"
    cf = inputs.last_cf or None
    if cf and cf.get("state") != "resolved":
        return "MOYEN", "verdict contrefactuel pending"
    return "FAIBLE", "aucun fait daté proche, aucune contrainte active"


def critical_trigger(triggers: list[str], erosion_status: list[dict]) -> tuple[str, str, int]:
    """(texte, note, n_masqués). Choix DÉCLARÉ : état ≠ dormant > baseline
    mesurable > T1. La distance ne s'invente pas (L15/P4)."""
    if not triggers:
        return "(aucun trigger écrit)", "⚠ thèse sans invalidateur", 0
    # 1. un driver érosion non-neutre pointe le trigger vivant
    for d in erosion_status or []:
        if (d.get("status") or "").lower() in ("erode", "invalidation"):
            nm = str(d.get("driver") or d.get("name") or "")[:80]
            if nm:
                return nm, f"état moteur : {d.get('status')}", max(0, len(triggers) - 1)
    # 2. le premier trigger MESURABLE (chiffre ancrable)
    for t in triggers:
        if _MEASURABLE_RE.search(t):
            return str(t)[:110], "distance : à mesurer", max(0, len(triggers) - 1)
    # 3. T1 déclaré (l'ordre d'écriture est la priorité déclarée)
    return str(triggers[0])[:110], "distance : à mesurer", max(0, len(triggers) - 1)


def single_lesson(inputs: Any, today: str = "") -> str:
    """UNE leçon (P6), en langage utilisateur : durées relatives, dates courtes.
    Priorité : CF dû > exposition biais ouverte > CF résolu > similaire > silence."""
    def _short(d: str) -> str:
        s = str(d)[:10]
        return f"{s[8:10]}/{s[5:7]}" if len(s) == 10 else s

    cf = inputs.last_cf or None
    if cf and cf.get("state") != "resolved":
        dj = _days_until(str(cf.get("due"))[:10], today) if today else None
        when = f"dans {dj} j ({_short(cf.get('due'))})" if dj is not None else f"le {_short(cf.get('due'))}"
        return (f"CF {_esc(cf.get('decision_type'))} (vs « {_esc(cf.get('branch'))} ») — "
                f"verdict {when}")
    if inputs.bias_events_open:
        b = inputs.bias_events_open[0]
        dj = _days_until(today, str(b.get("created_at"))[:10]) if today else None
        age = f" ({abs(dj)} j)" if dj is not None else ""
        return f"biais {_esc((b.get('bias') or '?').upper())} ouvert{age}"
    if cf and cf.get("state") == "resolved":
        return (f"CF {_esc(cf.get('decision_type'))} résolu : « {_esc(cf.get('branch'))} » "
                f"{cf.get('delta_pct', 0):+.1f} % — {_esc(cf.get('verdict'))}")
    sims = inputs.similar_situations or []
    if sims:
        return f"similaire : {_esc(sims[0].get('ticker'))} — {_esc(str(sims[0].get('snippet'))[:70])}"
    return "aucune leçon — historique jeune"


def _fmt_trigger(txt: str) -> str:
    """Stylisation d'AFFICHAGE (aucune interprétation) : la première
    parenthèse et tout ce qui suit passent en retrait gris — les baselines
    sont du contexte, le falsifieur est le sujet."""
    t = _esc(str(txt))
    i = t.find("(")
    if i > 8:
        return t[:i] + '<span class="v3-base">' + t[i:] + '</span>'
    return t


def render_position_card(inputs: Any, steer_v2: Any) -> str:
    """La carte V3. Fonction PURE de (CardInputs, SteerOutput) → HTML (P7)."""
    thesis = inputs.thesis or {}
    ticker = inputs.ticker
    bl = inputs.book_line
    today = str(getattr(bl, "price_asof", "") or thesis.get("last_reviewed") or "")[:10]

    try:
        from shared.ticker_names import get_short_name
        name = get_short_name(ticker) or ticker
    except Exception:
        name = ticker

    # ── matière première ────────────────────────────────────────────────────
    raw = thesis.get("invalidation_triggers") or []
    if isinstance(raw, str):
        with contextlib.suppress(Exception):
            raw = json.loads(raw or "[]")
    triggers = [str(t) for t in raw] if isinstance(raw, list) else []

    variant = str(thesis.get("variant_perception") or "")
    own = variant.split(" | ")[0].split(" ; ")[0].strip()[:130]
    ca_fresh = (
        inputs.counter_argument_brief
        if (inputs.counter_argument_at or "") >= str(thesis.get("opened_at") or "")[:10]
        else None
    )
    anti = str(ca_fresh or (triggers[1] if len(triggers) > 1 else (triggers[0] if triggers else ""))).strip()[:140]
    # A8 : la base est nommée — un contre-argument LLM n'a pas le même poids
    # qu'un invalidateur écrit par le gérant.
    anti_src = "copilot, LLM" if ca_fresh else "thèse"

    px = getattr(bl, "last_price_native", None) if bl else None
    ccy = (getattr(bl, "last_price_currency", None) if bl else None) or thesis.get("stop_currency") or ""
    stop = thesis.get("stop_value")
    stop_dist = None
    if px and stop:
        with contextlib.suppress(Exception):
            stop_dist = (float(px) - float(stop)) / float(px) * 100

    # ── DOIS-JE AGIR ? (le verdict d'abord, en euros) ───────────────────────
    verdict_cls, verdict = "act-none", ""
    forbid = ""
    v = getattr(getattr(steer_v2, "verdict", None), "value", "HOLD") if steer_v2 else "HOLD"
    line_eur = (getattr(bl, "current_eur", None) if bl else None) or 0.0
    if (inputs.kill_status or "") == "triggered":
        verdict_cls, verdict = "act-hot", f"kill-criterion DÉCLENCHÉ ({str(inputs.kill_at or '')[:10]}) — la thèse commande"
        forbid = "INTERDIT : renforcer, moyenner"
    elif v in ("TRIM_TO_X", "ADD_TO_X") and steer_v2.target_qty_delta_pct:
        delta = float(steer_v2.target_qty_delta_pct)
        eur = abs(delta) / 100.0 * float(line_eur)
        gesture = "TRIM" if delta < 0 else "ADD"
        tgt = inputs.binding_target_pct
        verdict_cls = "act-warm"
        verdict = f"{gesture} ~{eur:,.0f} € ({delta:+.1f} % de la ligne)" + (f" → retour cap {tgt:.1f} %" if tgt else "")
        if gesture == "TRIM":
            forbid = "INTERDIT : renforcer (over_cap) · AUTORISÉ : trim, hold"
    elif v == "EXIT":
        verdict_cls, verdict = "act-hot", "EXIT — steer engine"
    elif v == "REVIEW":
        verdict_cls, verdict = "act-warm", "REVIEW — la thèse doit être relue avant tout geste"
    nf = _next_dated_fact(inputs, today)
    if not verdict:
        verdict = "Rien — prochain fait daté : " + (f"{nf[0]} le {nf[1]}" if nf else "aucun au registre")
    lvl, why = cost_of_inaction(inputs, nf, today)
    lvl_cls = {"ÉLEVÉ": "v3-warn-d", "MOYEN": "v3-mid"}.get(lvl, "v3-mut")
    inaction = (f'inaction : <b class="{lvl_cls}">{lvl}</b> '
                f'<span class="v3-mut">— {_esc(why)}</span>')

    # ── POURQUOI ? ──────────────────────────────────────────────────────────
    own_html = _esc(own) if own else (
        '<span class="v3-undef">⚠ POURQUOI JE POSSÈDE CETTE LIGNE : INDÉFINI</span>'
    )
    lesson = single_lesson(inputs, today)

    # ── QU'EST-CE QUI ME FERA CHANGER D'AVIS ? ──────────────────────────────
    trig, trig_note, n_hidden = critical_trigger(triggers, inputs.erosion_driver_status)
    if stop:
        s_val = f"{stop:,.0f}".replace(",", " ")
        d_cls = "v3-warn-d" if (stop_dist is not None and stop_dist < 10) else "v3-mut"
        stop_html = (f'stop&nbsp;&nbsp;<b class="v3-num">{s_val}&nbsp;{_esc(ccy)}</b>'
                     + (f'&nbsp;&nbsp;<span class="{d_cls}">{stop_dist:+.0f} %</span>'
                        if stop_dist is not None else ""))
    else:
        stop_html = '<span class="v3-undef">⚠ stop non posé</span>'
    hidden_html = f' <span class="v3-mut">· +{n_hidden} masqués</span>' if n_hidden else ""

    # ── footer M1 (P2 : poids · PRU · px→stop · asof — rien d'autre) ────────
    pru = getattr(bl, "avg_cost_eur", None) if bl else None
    qty_f = getattr(bl, "qty", None) if bl else None
    cur_eur = getattr(bl, "current_eur", None) if bl else None
    latent = None
    with contextlib.suppress(Exception):
        if pru and qty_f and cur_eur:
            latent = (float(cur_eur) / float(qty_f) / float(pru) - 1) * 100
    footer = " · ".join(x for x in (
        f"poids {inputs.weight_pct:.1f} %",
        (f"PRU {pru:,.0f} €".replace(",", " ")
         + (f" <b class='v3-num'>{latent:+.0f} %</b>" if latent is not None else "")
         if pru else None),
        (f"px {px:,.0f} {_esc(ccy)}".replace(",", " ") if px else None),
        (f"asof {today[8:10]}/{today[5:7]}" if len(today) == 10 else f"asof {today or chr(63)}"),
    ) if x)

    # ── header : badges CONDITIONNELS, monochromes ──────────────────────────
    badges = []
    if (inputs.over_cap_status or "") == "over":
        badges.append("OVER_CAP")
    if inputs.bias_events_open:
        badges.append("BIAS_OPEN")
    badges_html = "".join(f'<span class="v3-badge">{b}</span>' for b in badges)
    conv = inputs.conviction_current or thesis.get("conviction") or "?"
    horizon = thesis.get("horizon") or "?"

    bandeau = getattr(steer_v2, "bandeau", "") if steer_v2 else ""
    bandeau_html = f'<div class="v3-bandeau">{_esc(bandeau)}</div>' if bandeau else ""

    return (
        f'<div class="pc-card v3" id="card-{_esc(ticker).replace(".", "-")}">'
        f'<style>{CARD_V3_CSS}</style>'
        f'{bandeau_html}'
        f'<div class="v3-head"><b>{_esc(name)}</b> <span class="v3-mut">({_esc(ticker)}) · c{conv} · {_esc(horizon)}</span>{badges_html}</div>'
        '<div class="v3-own">SI JE N’AVAIS PAS CETTE LIGNE, L’ACHÈTERAIS-JE AUJOURD’HUI ?'
        ' <span class="v3-mut">oui · non · seulement à un meilleur prix</span></div>'
        '<div class="v3-q">DOIS-JE AGIR ?</div>'
        f'<div class="v3-verdict {verdict_cls}">{_esc(verdict)}</div>'
        + (f'<div class="v3-line v3-forbid">{_esc(forbid)}</div>' if forbid else "")
        + f'<div class="v3-line">{inaction}</div>'
        '<div class="v3-q">POURQUOI CETTE POSITION EXISTE</div>'
        f'<div class="v3-line v3-strong">{own_html}</div>'
        f'<div class="v3-line">⚖ {_esc(anti)} <span class="v3-mut">({anti_src})</span></div>'
        f'<div class="v3-line v3-mut">{_esc(lesson)}</div>'
        '<div class="v3-q">QU’EST-CE QUI ME FERA CHANGER D’AVIS ?</div>'
        f'<div class="v3-line">▸ {_fmt_trigger(trig)} <span class="v3-mut">· {_esc(trig_note)}</span>{hidden_html}</div>'
        f'<div class="v3-line">▸ {stop_html}</div>'
        f'<div class="v3-foot">{footer}</div>'
        '</div>'
    )


#: CSS de la carte — scoped, embarqué UNE fois par le panel (pas par carte).
CARD_V3_CSS = """
.pc-card.v3{padding:16px 20px;font-size:12.5px;line-height:1.5}
.pc-card.v3 .v3-bandeau{background:#7a1f1f;color:#fff;font-weight:700;padding:6px 10px;border-radius:4px;margin-bottom:10px}
.pc-card.v3 .v3-head{font-size:15px;margin-bottom:6px}
.pc-card.v3 .v3-badge{font-family:var(--fm);font-size:9px;letter-spacing:.14em;border:1px solid var(--line);border-radius:3px;padding:2px 6px;margin-left:8px;color:var(--steel)}
.pc-card.v3 .v3-own{border:1px dashed var(--line);border-radius:6px;padding:6px 10px;margin:8px 0;font-family:var(--fm);font-size:10.5px;letter-spacing:.04em;color:var(--steel)}
.pc-card.v3 .v3-q{font-family:var(--fm);font-size:9px;letter-spacing:.18em;color:var(--steel);opacity:.75;margin:14px 0 4px}
.pc-card.v3 .v3-verdict{font-size:15px;font-weight:650;letter-spacing:-.01em}
.pc-card.v3 .act-none{color:#3a9d4e}
.pc-card.v3 .act-warm{color:#b8860b}
.pc-card.v3 .act-hot{color:#a5382a}
.pc-card.v3 .v3-line{margin:4px 0}
.pc-card.v3 .v3-strong{font-weight:600;font-size:14px;color:var(--ink);line-height:1.4}
.pc-card.v3 .v3-forbid{font-family:var(--fm);font-size:10.5px;letter-spacing:.05em;color:#b8860b;opacity:.9}
.pc-card.v3 .v3-mut{color:var(--steel);font-weight:400;font-size:11.5px}
.pc-card.v3 .v3-base{color:var(--steel);font-weight:400;font-size:11px}
.pc-card.v3 .v3-num{font-family:var(--fm);font-variant-numeric:tabular-nums;font-weight:600}
.pc-card.v3 .v3-mid{color:#b8860b}
.pc-card.v3 .v3-warn-d{color:#a5382a;font-weight:600}
.pc-card.v3 .v3-undef{color:#b8860b;font-weight:600;font-style:normal}
.pc-card.v3 .v3-warn{color:var(--steel);font-style:italic}
.pc-card.v3 .v3-foot{font-family:var(--fm);font-size:10.5px;color:var(--steel);opacity:.85;border-top:1px solid var(--line);margin-top:12px;padding-top:7px}
"""
