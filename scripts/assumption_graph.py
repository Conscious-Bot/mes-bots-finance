#!/usr/bin/env python3
"""Graphe d'hypothèses PRESAGE — validation, propagation d'OBLIGATIONS, hash (v3).

Conforme aux axiomes :
  A3 — aucune constante dans le code : les poids viennent de policy.yaml
  A8 — aucune dérivée persistée : le compte de preuves et la force d'étayage
       sont CALCULÉS ici, jamais réécrits dans le YAML
  A9 — reproductibilité : hash de la structure PARSÉE (pas du fichier), pour
       épingler l'état du graphe et des politiques dans chaque décision

Le moteur ne renvoie pas seulement ce qui casse : il renvoie CE QU'IL FAUT FAIRE
(registre `actions`, style Flight Rules), en distinguant les actions bloquantes.

Usage :
    python3 scripts/assumption_graph.py              # audit + méta-règles + hash
    python3 scripts/assumption_graph.py --fail H12   # simulation d'une chute
    python3 scripts/assumption_graph.py --hash       # hashes seuls (pour épingler)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from contextlib import suppress
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG_A = ROOT / "config" / "assumptions.yaml"
CFG_P = ROOT / "config" / "policy.yaml"
SOLVER_VERSION = "assumption_graph/3.0"
SEV = ["EXISTENTIAL", "CRITICAL", "HIGH", "MEDIUM", "LOW"]
BASES = {"empirical", "theoretical", "engineering", "institutional", "asserted"}
RELS = {"requires", "supports", "modulates", "correlated"}
FAILED = {"FALSIFIEE", "PARTIELLEMENT_FALSIFIEE"}


def canonical_hash(obj) -> str:
    """Hash de la STRUCTURE parsée (A9) : commentaires et mise en forme ignorés."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()[:16]


def load():
    a = yaml.safe_load(CFG_A.read_text(encoding="utf-8"))
    p = yaml.safe_load(CFG_P.read_text(encoding="utf-8"))
    return a, p


def support_strength(sup: dict, pol: dict) -> tuple[float, str]:
    """FORCE D'ÉTAYAGE (fiabilité du STATUT, pas P(hypothèse vraie)).

    Aucune constante ici : tout vient de policy.support_policy (A3).
    """
    sp = pol["support_policy"]
    basis = (sup or {}).get("basis", "asserted")
    ev = (sup or {}).get("evidence") or []
    n = len(ev)  # DÉRIVÉ des objets de preuve, jamais stocké (A8)
    val = sp["base_by_basis"].get(basis, sp["base_by_basis"]["asserted"])
    if n:
        val += min(sp["evidence_gain_max"], sp["evidence_gain_coef"] * (n**0.5))
    val += sp["bonus_reproducible"] if (sup or {}).get("reproducible") else 0
    val += sp["bonus_external"] if (sup or {}).get("external_validation") else 0
    val = min(sp["cap_total"], val)
    if basis == "asserted" and not n:
        return min(val, sp["cap_asserted_no_evidence"]), "affirmée, 0 preuve → plafonnée"
    return val, f"{basis}, {n} preuve(s)"


# Méta-règles que CE moteur sait appliquer. Toute règle déclarée dans
# policy.yaml et absente d'ici fait ÉCHOUER la validation (fail-closed) :
# une règle déclarée mais non exécutée est une illusion d'enforcement — même
# classe d'erreur qu'un backup vert sur une donnée périmée. Le moteur doit
# échouer bruyamment sur ce qu'il ne sait pas appliquer, jamais le survoler.
IMPLEMENTED_META_RULES = {
    "existential_requires_edges",
    "existential_requires_action",
    "failed_requires_blocking_action",
    "asserted_cannot_be_TENUE",
    "low_severity_no_gerant_owner",
    "tenue_requires_exposure",
}

# Types de preuve qui constituent une EXPOSITION : un contact réel avec le monde
# où le falsifieur aurait PU se déclencher. Un argument théorique ou institutionnel
# n'est pas un test — « jamais mis en défaut » n'est pas « confirmé ».
EXPOSURE_TYPES = {"incident", "drill", "observation"}


def _check_exposure(hid: str, h: dict, sup: dict, pol: dict) -> list[str]:
    """`tenue_requires_exposure` — existence, FIDÉLITÉ et FRAÎCHEUR de l'épreuve.

    Trois façons pour une hypothèse d'être TENUE à tort :
      a) jamais exposée      → « jamais mis en défaut » n'est pas « confirmé »
      b) exposée trop faible → un constat passif ne teste pas une hypothèse porteuse
      c) exposée trop vieux  → l'épreuve périme ; sans re-drill, retour au cas (a)

    Tout est dérivé de `type` et `date` des preuves : aucun champ nouveau (A8).
    """
    from datetime import date as _date

    ep = pol.get("exposure_policy") or {}
    fid_by_type = ep.get("fidelity_by_type") or {}
    sev = h.get("severity", "LOW")
    min_fid = (ep.get("min_fidelity_by_severity") or {}).get(sev, 0.0)
    half_life = (ep.get("half_life_days_by_severity") or {}).get(sev)
    evs = sup.get("evidence") or []
    out: list[str] = []

    expo = [ev for ev in evs if ev.get("type") in EXPOSURE_TYPES]
    if not expo:
        types = sorted({ev.get("type") for ev in evs}) or ["aucune"]
        return [f"{hid} TENUE sans EXPOSITION (preuves de type {types}) — "
                "jamais mise à l'épreuve, statut honnête = NON_TESTEE"]

    # (b) fidélité : le meilleur contact atteint-il le niveau exigé par le poids ?
    # key= obligatoire : sans lui, un TIE de fidélité fait comparer les dicts ev
    # entre eux -> TypeError (constaté 04/08, emitter 8h en échec chaque matin).
    best = max(((fid_by_type.get(ev.get("type"), 0.0), ev) for ev in expo),
               key=lambda t: t[0])
    if best[0] < min_fid:
        out.append(
            f"{hid} TENUE avec exposition de FIDÉLITÉ INSUFFISANTE "
            f"({best[1].get('type')}={best[0]:.1f} < {min_fid:.1f} exigé pour {sev}) — "
            "un constat passif ne teste pas une hypothèse porteuse ; exige un drill"
        )

    # (c) fraîcheur : l'épreuve la plus récente est-elle encore valide ?
    dates = []
    for ev in expo:
        d = ev.get("date")
        if isinstance(d, _date):
            dates.append(d)
        elif isinstance(d, str):
            with suppress(ValueError):
                dates.append(_date.fromisoformat(d[:10]))
    if dates and half_life:
        age = (_date.today() - max(dates)).days
        if age > half_life:
            out.append(
                f"{hid} TENUE sur une exposition PÉRIMÉE ({age}j > {half_life}j "
                f"pour {sev}) — re-drill requis, sinon retour à « tenue par "
                "absence de contradiction »"
            )
    return out


def blocking_obligations() -> dict:
    """Obligations bloquantes ACTIVES + hypothèses en défaut + péremption la plus proche.

    SOURCE UNIQUE de cette lecture (L1) : le dashboard, le heartbeat et tout autre
    consommateur passent par ici — jamais par une réimplémentation du filtre.

    Fail-closed : toute erreur de lecture rend un état EXPLICITE (`error`), jamais
    un dict vide qui se lirait « aucune obligation » — un registre illisible n'est
    pas un registre serein.

    Retourne : {obligations: [{id, do, hypotheses}], failed: [ids],
                next_expiry_days: int|None, next_expiry_id: str|None, error: str|None}
    """
    from datetime import date as _d
    out = {"obligations": [], "failed": [], "next_expiry_days": None,
           "next_expiry_id": None, "error": None}
    try:
        a_doc, pol = load()
    except Exception as e:
        out["error"] = f"registre illisible : {e}"
        return out
    A, ACT = a_doc.get("assumptions", {}), a_doc.get("actions", {})
    at_risk = {"SOUS_TENSION", "INCONNUE"} | FAILED

    by_action: dict[str, list[str]] = {}
    for hid, h in A.items():
        if h.get("status") in FAILED:
            out["failed"].append(hid)
        if h.get("status") in at_risk:
            for aid in h.get("actions") or []:
                if ACT.get(aid, {}).get("blocking"):
                    by_action.setdefault(aid, []).append(hid)
    out["obligations"] = [
        {"id": aid, "do": ACT[aid]["do"], "hypotheses": sorted(hs)}
        for aid, hs in sorted(by_action.items())
    ]

    hl = (pol.get("exposure_policy") or {}).get("half_life_days_by_severity") or {}
    for hid, h in A.items():
        if h.get("status") != "TENUE":
            continue
        life = hl.get(h.get("severity"))
        if not life:
            continue
        dts = []
        for ev in (h.get("support") or {}).get("evidence") or []:
            if ev.get("type") in EXPOSURE_TYPES and ev.get("date"):
                d = ev["date"]
                with suppress(ValueError, TypeError):
                    dts.append(d if isinstance(d, _d) else _d.fromisoformat(str(d)[:10]))
        if dts:
            left = life - (_d.today() - max(dts)).days
            if out["next_expiry_days"] is None or left < out["next_expiry_days"]:
                out["next_expiry_days"], out["next_expiry_id"] = left, hid
    return out


def validate(A: dict, E: list, ACT: dict, pol: dict) -> tuple[list, list]:
    errs, warns, ids = [], [], set(A)
    mr = pol.get("meta_rules", {})
    linked = {e["from"] for e in E} | {e["to"] for e in E}

    # Garde de classe : aucune méta-règle déclarée ne peut être ignorée en silence.
    declared = {k for k, v in mr.items()
                if isinstance(v, dict) and v.get("value") is True}
    orphelines = declared - IMPLEMENTED_META_RULES
    if orphelines:
        errs.append(
            f"méta-règle(s) déclarée(s) mais NON IMPLÉMENTÉE(S) : {sorted(orphelines)} — "
            "illusion d'enforcement. Câbler dans le moteur ou retirer de policy.yaml."
        )

    for hid, h in A.items():
        sup = h.get("support") or {}
        if sup.get("basis") not in BASES:
            errs.append(f"{hid}.support.basis invalide")
        if "observations" in sup or "confidence" in h:
            errs.append(f"{hid} : champ dérivé persisté (A8) — utiliser evidence[]")
        for ev in sup.get("evidence") or []:
            for f in ("id", "date", "source", "type", "claim"):
                if not ev.get(f):
                    errs.append(f"{hid} preuve sans '{f}'")
            # Le `type` est auto-déclaré (jugement résiduel, cf policy.exposure_policy).
            # Mitigation : un `drill` doit NOMMER le mode de défaillance qu'il rejoue.
            # Un drill qui n'ose pas dire ce qu'il reproduit n'en est pas un.
            if (ev.get("type") == "drill"
                    and (pol.get("exposure_policy") or {}).get("drill_requires_exercises")
                    and not ev.get("exercises")):
                errs.append(
                    f"{hid} preuve {ev.get('id')} taguée 'drill' sans champ 'exercises' — "
                    "un drill doit nommer le mode de défaillance rejoué (anti-étiquetage)"
                )
        if not h.get("falsifier"):
            errs.append(f"{hid} sans falsifieur")
        for aid in h.get("actions") or []:
            if aid not in ACT:
                errs.append(f"{hid} référence l'action inconnue {aid}")
        if h.get("severity") == "EXISTENTIAL":
            for f in ("logical_owner", "current_owner", "trigger", "deadline"):
                if not h.get(f):
                    errs.append(f"{hid} EXISTENTIAL sans '{f}'")
            # méta-règles logiques
            if mr.get("existential_requires_edges", {}).get("value") and hid not in linked:
                warns.append(f"{hid} EXISTENTIAL sans aucune arête — mal reliée ?")
            if mr.get("existential_requires_action", {}).get("value") and not h.get("actions"):
                warns.append(f"{hid} EXISTENTIAL sans action — décoration")
        if (mr.get("failed_requires_blocking_action", {}).get("value")
                and h["status"] in FAILED
                and not any(ACT.get(a, {}).get("blocking") for a in h.get("actions") or [])):
            warns.append(f"{hid} {h['status']} sans action BLOQUANTE")
        if (mr.get("asserted_cannot_be_TENUE", {}).get("value")
                and h["status"] == "TENUE" and sup.get("basis") == "asserted"
                and not sup.get("evidence")):
            warns.append(f"{hid} TENUE sur base affirmée sans preuve — prétention")
        if (mr.get("low_severity_no_gerant_owner", {}).get("value")
                and h.get("severity") == "LOW" and h.get("logical_owner") == "gerant"):
            warns.append(f"{hid} LOW mais propriété du gérant — incohérent")
        if mr.get("tenue_requires_exposure", {}).get("value") and h["status"] == "TENUE":
            warns.extend(_check_exposure(hid, h, sup, pol))

    for i, e in enumerate(E):
        if e.get("relation") not in RELS:
            errs.append(f"edge[{i}] relation invalide")
        if e.get("from") not in ids:
            errs.append(f"edge[{i}].from inexistante")
        if not e.get("justification") or not e.get("review"):
            errs.append(f"edge[{i}] sans justification ou cadence de revue")

    req = {}
    for e in E:
        if e["relation"] == "requires" and e["to"] in ids:
            req.setdefault(e["from"], []).append(e["to"])
    st = {}

    def visit(n, stack):
        if st.get(n) == 1:
            errs.append("cycle requires : " + " -> ".join([*stack, n]))
            return
        if st.get(n) == 2:
            return
        st[n] = 1
        for m in req.get(n, []):
            visit(m, [*stack, n])
        st[n] = 2

    for n in list(req):
        visit(n, [])
    return errs, warns


def propagate(A: dict, E: list, ACT: dict, failed: set) -> dict:
    ids = set(A)
    invalid, unsupported, recompute, modules = set(failed), set(), set(), set()
    frontier = set(failed)
    while frontier:
        nxt = set()
        for e in E:
            if e["from"] not in frontier:
                continue
            t, r = e["to"], e["relation"]
            if r == "requires":
                if t in ids:
                    if t not in invalid:
                        invalid.add(t)
                        nxt.add(t)
                else:
                    modules.add(t)
            elif r == "supports":
                unsupported.add(t) if t in ids else modules.add(t)
            elif r == "modulates":
                recompute.add(t) if t in ids else modules.add(t)
        frontier = nxt
    obligations = {}
    for hid in invalid | unsupported | recompute:
        for aid in A.get(hid, {}).get("actions") or []:
            obligations.setdefault(aid, set()).add(hid)
        modules.update(A.get(hid, {}).get("modules") or [])
    return {"invalid": invalid, "unsupported": unsupported - invalid,
            "recompute": recompute - invalid, "modules": modules, "obligations": obligations}


def derive_severity(A: dict, E: list, ACT: dict, pol: dict) -> dict:
    """SÉVÉRITÉ DÉRIVÉE du graphe (A8) — aucune attribution humaine.

    blast = rayon de souffle réel (simulation de la chute), pondéré par la
    réversibilité (classe) et la détectabilité (trigger observable ?).
    """
    sp = pol["severity_policy"]
    w, out = sp["blast_weights"], {}
    for hid, h in A.items():
        r = propagate(A, E, ACT, {hid})
        blast = (w["invalid"] * (len(r["invalid"]) - 1)
                 + w["unsupported"] * len(r["unsupported"])
                 + w["recompute"] * len(r["recompute"])
                 + w["modules"] * len(r["modules"]))
        blast *= sp["reversibility_mult"].get(h.get("class"), 1.0)
        if not h.get("trigger"):
            blast *= sp["undetectable_mult"]
        label = "LOW"
        for lv in ("EXISTENTIAL", "CRITICAL", "HIGH", "MEDIUM"):
            if blast >= sp["thresholds"][lv]:
                label = lv
                break
        out[hid] = (round(blast, 2), label, h.get("severity"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fail")
    ap.add_argument("--hash", action="store_true")
    ap.add_argument("--severity", action="store_true",
                    help="sévérité DÉRIVÉE du graphe vs sévérité déclarée")
    ap.add_argument("--heartbeat", action="store_true",
                    help="signal POSITIF périodique (dead man's switch) + marqueur horodaté")
    args = ap.parse_args()

    a_doc, pol = load()
    A, E, ACT = a_doc["assumptions"], a_doc["edges"], a_doc["actions"]
    h_assum, h_pol = canonical_hash(a_doc), canonical_hash(pol)

    if args.hash:
        print(f"assumptions_hash={h_assum}\npolicy_hash={h_pol}\nsolver_version={SOLVER_VERSION}")
        return 0

    if args.heartbeat:
        # DEAD MAN'S SWITCH — on n'ajoute pas un gardien au gardien (récursion
        # infinie) : le moteur émet un signal POSITIF et c'est son SILENCE qui
        # alarme. Le gardien terminal est l'attention humaine — cohérent avec H10
        # plutôt qu'une fiction de surveillance supplémentaire.
        # Contrat d'interface : une ligne sur stdout + touch du marqueur.
        # Le watcher ne lit QUE le mtime du marqueur.
        from datetime import date as _d
        errs, warns = validate(A, E, ACT, pol)
        blocking = sorted({
            aid for hid, h in A.items()
            if h["status"] in FAILED or h["status"] in {"SOUS_TENSION", "INCONNUE"}
            for aid in (h.get("actions") or []) if ACT.get(aid, {}).get("blocking")
        })
        ep = pol.get("exposure_policy") or {}
        hl = ep.get("half_life_days_by_severity") or {}
        soonest, soonest_id = None, None
        for hid, h in A.items():
            if h["status"] != "TENUE":
                continue
            life = hl.get(h.get("severity"))
            if not life:
                continue
            dts = []
            for ev in (h.get("support") or {}).get("evidence") or []:
                if ev.get("type") in EXPOSURE_TYPES and ev.get("date"):
                    d = ev["date"]
                    with suppress(ValueError, TypeError):
                        dts.append(d if isinstance(d, _d) else _d.fromisoformat(str(d)[:10]))
            if dts:
                left = life - (_d.today() - max(dts)).days
                if soonest is None or left < soonest:
                    soonest, soonest_id = left, hid
        expiry = f"{soonest}j ({soonest_id})" if soonest is not None else "—"
        state = "ERREURS" if errs else "OK"
        print(f"PRESAGE registre {state} · {len(A)} hypothèses · {len(errs)} erreur(s) · "
              f"{len(warns)} avertissement(s) · {len(blocking)} obligation(s) bloquante(s) "
              f"[{', '.join(blocking) or '—'}] · prochaine péremption d'exposition : {expiry} "
              f"· graph={h_assum} policy={h_pol}")
        if not errs:
            marker = ROOT / "data" / ".registry_heartbeat_ok"
            marker.parent.mkdir(exist_ok=True)
            marker.touch()
        return 1 if errs else 0

    if args.severity:
        d = derive_severity(A, E, ACT, pol)
        deg = dict.fromkeys(A, 0)
        for e in E:
            deg[e["from"]] = deg.get(e["from"], 0) + 1
            if e["to"] in deg:
                deg[e["to"]] += 1
        # Garde anti-Goodhart : toute métrique structurelle est publiée AVEC
        # le hash du graphe et son nombre d'arêtes (une baisse de blast peut
        # signifier « plus modulaire » OU « des arêtes ont disparu »).
        print(f"MÉTRIQUES STRUCTURELLES | graph={h_assum} arêtes={len(E)} "
              f"policy={h_pol} solver={SOLVER_VERSION}")
        print("Blast Radius = propriété du MODÈLE CAUSAL, jamais de l'hypothèse (A8).")
        print("Centralité et influence décisionnelle = deux axes, JAMAIS multipliés.\n")
        print(f"{'ID':6} {'blast':>6} {'centr':>6} {'infl':>6}  {'DERIVED':13} {'DECLARED':13} écart")
        div = 0
        for hid, (b, calc, decl) in sorted(d.items(), key=lambda kv: -kv[1][0]):
            flag = ""
            if calc != decl:
                div += 1
                flag = "◀ DIVERGENCE"
            # influence décisionnelle : indisponible tant que le registre
            # d'attribution des décisions n'existe pas (jamais inventée).
            print(f"{hid:6} {b:>6.2f} {deg[hid]:>6} {'n/a':>6}  {calc:13} {decl:13} {flag}")
        print(f"\n{div}/{len(d)} divergences. AUCUNE ne justifie à elle seule une "
              f"modification (règle anti-Goodhart) :\nchaque écart exige une explication "
              f"causale — étiquetage humain erroné, arête manquante, ou solveur défaillant.")
        print("Colonne 'infl' = n/a : registre d'attribution des décisions non construit.")

        # VUE D'AUDIT — asymétrie entrée/sortie. Pas un score : une liste.
        indeg = dict.fromkeys(A, 0)
        outdeg = dict.fromkeys(A, 0)
        for e in E:
            outdeg[e["from"]] = outdeg.get(e["from"], 0) + 1
            if e["to"] in indeg:
                indeg[e["to"]] += 1
        suspects = [h for h in A if indeg[h] >= 2 and outdeg[h] <= 1]
        print("\nVUE D'AUDIT — asymétrie entrée/sortie (arête sortante probablement manquante) :")
        if not suspects:
            print("  aucune")
        for h in sorted(suspects, key=lambda x: -(indeg[x] - outdeg[x])):
            print(f"  {h}: entrant={indeg[h]} sortant={outdeg[h]} blast={d[h][0]:.2f}"
                  f" — que casse {h} en tombant ? Modéliser la sortie.")
        return 0

    errs, warns = validate(A, E, ACT, pol)
    if errs:
        print("VALIDATION ÉCHOUÉE (fail-closed) :")
        for e in errs:
            print("  -", e)
        return 1
    print(f"Validation OK — {len(A)} hypothèses, {len(E)} arêtes, {len(ACT)} actions.")
    print(f"A9 : assumptions_hash={h_assum} policy_hash={h_pol} solver={SOLVER_VERSION}\n")
    if warns:
        print("MÉTA-RÈGLES — incohérences logiques :")
        for w in warns:
            print("  ⚠", w)
        print()

    if not args.fail:
        print("(étayage = fiabilité du STATUT affiché, PAS P(l'hypothèse tient))\n")
        print(f"{'ID':6} {'SEV':12} {'STATUT':26} {'étayage':>8}  base")
        for hid, h in sorted(A.items(), key=lambda kv: (SEV.index(kv[1]["severity"]), kv[0])):
            s, why = support_strength(h.get("support"), pol)
            print(f"{hid:6} {h['severity']:12} {h['status']:26} {s:>8.2f}  {why}")
        print("\nOBLIGATIONS BLOQUANTES ACTIVES (hypothèses déjà en défaut ou sous tension) :")
        for hid, h in sorted(A.items()):
            if h["status"] in FAILED or h["status"] in {"SOUS_TENSION", "INCONNUE"}:
                for aid in h.get("actions") or []:
                    if ACT[aid].get("blocking"):
                        print(f"  [{aid}] ({hid}) {ACT[aid]['do'][:78]}")
        return 0

    failed = {x.strip() for x in args.fail.split(",")}
    if failed - set(A):
        print(f"Inconnues : {failed - set(A)}")
        return 1
    r = propagate(A, E, ACT, failed)
    print(f"=== SIMULATION : chute de {', '.join(sorted(failed))} ===\n")
    for label, key in (("INVALIDES (requires)", "invalid"),
                       ("NON ÉTAYÉES (supports)", "unsupported"),
                       ("À RECALCULER (modulates)", "recompute")):
        print(f"{label} :")
        for h in sorted(r[key]):
            print(f"  {h} [{A[h]['severity']}] {A[h]['statement'][:58]}")
        print()
    print("MODULES IMPACTÉS :", ", ".join(sorted(r["modules"])) or "—")
    print("\nOBLIGATIONS DÉCLENCHÉES :")
    for aid, src in sorted(r["obligations"].items()):
        tag = "BLOQUANTE" if ACT[aid].get("blocking") else "à planifier"
        print(f"  [{aid}] {tag:11} ← {','.join(sorted(src))}\n      {ACT[aid]['do']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
