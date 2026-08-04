"""GATE ACT-006 — le LLM propose les urgents, ce gate dispose. Mécanique, pas vigilance (L27).

POURQUOI (spec digest v2.3 Fix 1, jamais implémentée — constat 03/08/2026)
--------------------------------------------------------------------------
Le prompt DEMANDE au LLM « VERDICT: X urgent … NOMME les urgents ». Résultat
observé deux jours de suite : des urgents fabriqués sur de l'évidence
secondaire (tweets, « insider dump », « late-cycle confirmé ») et des claims
« touche le kill-criterion explicite » alors que `kill_criteria_alerts`
affichait 713/713 dormant — pas un seul invalidateur franchi, jamais.

La spec dit : « Le LLM ne peut PLUS nommer un urgent. […] l'insider selling
non vérifié aux Form 4 reste `secondaire` et ne peut pas porter un urgent.
"0 urgent" est un résultat NORMAL et fréquent. »

CE QUE CE GATE FAIT (post-génération, déterministe)
---------------------------------------------------
1. Parse la ligne VERDICT et les urgents nommés.
2. Un urgent ne TIENT que s'il est porté par ≥1 signal PRIMAIRE
   (`signal_type` ∈ {catalyst, data}) taggé sur ce ticker dans la fenêtre.
   Narratives et opinions seules → dégradé en monitoring, à découvert
   (annotation visible, jamais silencieux).
3. Toute mention « kill-criterion » dans le corps est confrontée au statut
   RÉEL du moteur (`kill_criteria_alerts`, source unique L1) : si le dernier
   statut du ticker est dormant/absent, la mention reçoit un correctif
   littéral inline. Le gate ne supprime pas la phrase — il la désarme.
4. La ligne VERDICT est RÉÉCRITE avec les comptes corrigés + un trailer GATE
   listant chaque dégradation et sa raison.
5. Fail-loud : si le gate lui-même casse, le digest sort PRÉFIXÉ d'un
   bandeau incident « verdicts NON vérifiés » — un échec du contrôle ne doit
   jamais se lire comme un contrôle réussi (L15).

CE QUE CE GATE NE FAIT PAS (déclaré, pas caché)
-----------------------------------------------
`date_du_fait` comme CHAMP obligatoire exige une extraction à l'enrichissement
(schéma signals + prompt amont) — hors de portée d'un gate post-hoc. C'est le
résidu d'ACT-006, tracé au registre. Ce gate ferme les deux jambes mécanisables
aujourd'hui : le tier d'évidence et l'ancrage kill-criterion.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

#: Types de signaux comptant comme évidence PRIMAIRE (hiérarchie
#: config/policy.yaml `evidence_weight` : filings/prints/données ≥ 0.75 ;
#: presse/opinions ≤ 0.35). `signal_type` est le proxy disponible en base.
PRIMARY_SIGNAL_TYPES: frozenset[str] = frozenset({"catalyst", "data"})

#: Statuts de kill_criteria_alerts qui AUTORISENT une claim de franchissement.
#: Tout le reste (dormant, absent, inconnu) = la claim est désarmée.
KILL_STATUSES_ALLOWING_CLAIM: frozenset[str] = frozenset({"triggered", "at_risk"})

_VERDICT_RE = re.compile(r"^.*VERDICT\s*:.*$", re.M)
_URGENT_RE = re.compile(r"urgent\s*:\s*\*{0,2}([A-Z0-9][A-Z0-9.\-]{0,11})\*{0,2}", re.I)
_KILL_MENTION_RE = re.compile(r"kill[- _]?crit[eè]r\w*", re.I)

_DISARM_NOTE = (
    " [GATE ACT-006 : proximité thématique, AUCUN kill-criterion franchi — "
    "kill_criteria_monitor: {status}]"
)


def _signal_tickers(sig: dict[str, Any]) -> set[str]:
    """Tickers taggés d'un signal (colonne entities, JSON ou liste)."""
    ents = sig.get("entities")
    if isinstance(ents, str):
        try:
            ents = json.loads(ents)
        except Exception:
            return set()
    if not isinstance(ents, list):
        return set()
    return {str(e).upper() for e in ents if e}


def primary_backing(ticker: str, signals: list[dict[str, Any]]) -> list[int]:
    """IDs des signaux PRIMAIRES portant ce ticker. Vide = pas d'évidence primaire."""
    tk = ticker.upper()
    out = []
    for s in signals:
        if (s.get("signal_type") or "").lower() in PRIMARY_SIGNAL_TYPES \
                and tk in _signal_tickers(s):
            out.append(int(s.get("id") or 0))
    return out


def _verdict_block(narrative: str) -> tuple[int, int] | None:
    """(début, fin) du BLOC verdict : la ligne VERDICT + ses lignes de suite
    jusqu'à la première ligne vide. Dans le format réel du digest, les urgents
    nommés sont sur la ligne SUIVANT le VERDICT — pas dessus (constat dry-run
    03/08 : un gate qui ne lisait que la ligne manquait tous les urgents)."""
    m = _VERDICT_RE.search(narrative)
    if not m:
        return None
    start = m.start()
    end = m.end()
    rest = narrative[end:]
    for line in rest.split("\n")[1:4]:  # au plus 3 lignes de continuation
        if not line.strip():
            break
        end += 1 + len(line)
    return (start, end)


_URGENT_LIST_RE = re.compile(
    r"\|\s*\*{0,2}([A-Z0-9][A-Z0-9.\-]{0,11})\*{0,2}\s*\("
)  # format 04/08 : "urgent: A (...) | B (...) | C (...)" — B et C sans le mot "urgent"


def parse_urgents(narrative: str) -> list[str]:
    """Tickers nommés urgents dans le BLOC verdict (ligne + continuation).

    Deux formats réels observés :
      03/08 : "urgent: MU | urgent: TSM"           -> _URGENT_RE suffit
      04/08 : "urgent: AVGO (...) | MU (...) | AMZN (...)" -> les suivants n'ont
              pas le mot "urgent" ; sans _URGENT_LIST_RE ils DISPARAISSAIENT du
              verdict réécrit au lieu d'être dégradés à découvert (bug attrapé
              par dry-run le 04/08, avant déploiement).
    """
    span = _verdict_block(narrative)
    if span is None:
        return []
    block = narrative[span[0]:span[1]]
    found = [t.upper() for t in _URGENT_RE.findall(block)]
    if found:  # la liste "| TICKER (" ne vaut que si un "urgent:" ouvre le bloc
        found += [t.upper() for t in _URGENT_LIST_RE.findall(block)]
    return list(dict.fromkeys(found))


def apply_evidence_gate(
    narrative: str,
    signals: list[dict[str, Any]],
    kill_status_by_ticker: dict[str, str],
) -> str:
    """Applique le gate. Fonction PURE — aucune I/O, testable seule.

    Args:
        narrative : sortie LLM (contient la ligne VERDICT).
        signals   : signaux de la fenêtre (dicts : id, signal_type, entities…).
        kill_status_by_ticker : dernier statut kill_criteria_alerts par ticker.

    Returns:
        Narrative corrigée. JAMAIS d'exception : les erreurs deviennent un
        bandeau incident préfixé (fail-loud, pas fail-silent).
    """
    try:
        return _apply(narrative, signals, kill_status_by_ticker)
    except Exception as exc:  # jamais avaler : l'échec du contrôle s'affiche
        log.error(f"evidence gate failed: {exc}")
        return (
            "⚠ GATE ACT-006 EN ÉCHEC (" + type(exc).__name__ + ") — "
            "les verdicts ci-dessous n'ont PAS été vérifiés mécaniquement.\n\n"
            + narrative
        )


def _apply(
    narrative: str,
    signals: list[dict[str, Any]],
    kill_status_by_ticker: dict[str, str],
) -> str:
    urgents = parse_urgents(narrative)
    kept: list[str] = []
    demoted: list[tuple[str, str]] = []  # (ticker, raison)

    for tk in urgents:
        backing = primary_backing(tk, signals)
        if backing:
            kept.append(tk)
        else:
            demoted.append((
                tk,
                "aucun signal primaire (catalyst/data) — évidence secondaire seule "
                "ne peut pas porter un urgent (spec v2.3)",
            ))

    out = narrative

    # ── désarmer les claims kill-criterion non soutenues par le moteur ──
    status_norm = {k.upper(): (v or "").lower() for k, v in kill_status_by_ticker.items()}
    if _KILL_MENTION_RE.search(out):
        # tickers du digest = urgents + tickers des signaux (périmètre concerné)
        mentioned = set(urgents)
        for s in signals:
            mentioned |= _signal_tickers(s)
        any_allowed = any(
            status_norm.get(tk, "") in KILL_STATUSES_ALLOWING_CLAIM for tk in mentioned
        )
        if not any_allowed:
            # Aucun ticker du périmètre n'a un kill-criterion réellement actif :
            # chaque mention reçoit le correctif inline, une fois par ligne.
            corrected_lines = []
            for line in out.split("\n"):
                if _KILL_MENTION_RE.search(line) and "GATE ACT-006" not in line:
                    line = line.rstrip() + _DISARM_NOTE.format(
                        status=_dominant_status(status_norm) or "dormant/absent"
                    )
                corrected_lines.append(line)
            out = "\n".join(corrected_lines)

    # ── réécrire le BLOC verdict avec les comptes corrigés ──
    span = _verdict_block(out)
    if span and (demoted or urgents):
        block = out[span[0]:span[1]]
        mon = re.search(r"(\d+)\s*monitoring", block)
        noi = re.search(r"(\d+)\s*noise", block)
        n_mon = (int(mon.group(1)) if mon else 0) + len(demoted)
        n_noi = int(noi.group(1)) if noi else 0
        new_block = f"VERDICT (gated): {len(kept)} urgent / {n_mon} monitoring / {n_noi} noise"
        if kept:
            new_block += "\n" + " | ".join(f"**urgent: {t}**" for t in kept)
        # (les dégradations vivent dans le trailer, une seule fois — pas de doublon)
        out = out[:span[0]] + new_block + out[span[1]:]

    # ── trailer : chaque dégradation, à découvert ──
    n_tagged = sum(1 for s_ in signals if _signal_tickers(s_))
    if demoted or (urgents and not n_tagged):
        trailer = ["", "─── GATE ACT-006 (mécanique — le LLM propose, le gate dispose) ───"]
        for tk, why in demoted:
            trailer.append(f"  ↓ {tk} : urgent→monitoring — {why}")
        if urgents and n_tagged == 0:
            trailer.append(
                f"  ⚠ CÉCITÉ DÉCLARÉE : 0/{len(signals)} signaux de la fenêtre ont des "
                "tickers taggés (enrichissement entities en retard) — le gate ne peut "
                "VALIDER aucun urgent. Ce 0 urgent signifie « invérifiable », pas « calme »."
            )
        out += "\n" + "\n".join(trailer)

    return out


def _dominant_status(status_norm: dict[str, str]) -> str | None:
    vals = [v for v in status_norm.values() if v]
    if not vals:
        return None
    return max(set(vals), key=vals.count)


def fetch_kill_status_by_ticker(cx: Any) -> dict[str, str]:
    """Dernier statut kill_criteria_alerts par ticker — source unique (L1).

    Le gate ne réimplémente PAS la logique du monitor : il lit son dernier mot.
    """
    try:
        rows = cx.execute(
            "SELECT ticker, status FROM kill_criteria_alerts "
            "WHERE id IN (SELECT max(id) FROM kill_criteria_alerts GROUP BY ticker)"
        ).fetchall()
        return {str(t): str(s) for t, s in rows}
    except Exception as exc:
        log.warning(f"kill status fetch failed: {exc}")
        return {}  # dict vide = aucune claim autorisée (fail-closed)
