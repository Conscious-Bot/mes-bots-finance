"""Stress-gate monitor : Axe 4 QUALITY_BAR 1er geste.

Spec : "cabler le stress-test existant (intelligence/factor_exposures.run_stress_test)
a un seuil + une alerte (la machinerie existe, l'alerte non)".

Pattern monitor canonique : docs/templates/monitor_pattern.md.

key = scenario_name
status = ok / warn / breach
transition actionable = (*, breach) -> notify Telegram

Pas de wire bias_events : stress-gate = etat structurel du book
(concentration excessive), pas comportement-utilisateur. Le canal
fomo_greed (kill_criteria + over_cap) traite deja le biais cognitif.

L21 QUALITY_BAR : config seuils en YAML declaratif (warn/breach),
live state append-only en DB (stress_gate_alerts). Si stress-test
fail (data manquante) -> raise MissingDataError, jamais fabriquer
un drawdown_pct fictif (L15).
"""

from __future__ import annotations

import logging

from shared import notify, storage

log = logging.getLogger(__name__)


class MissingStressDataError(Exception):
    """Stress-test impossible : data critique manquante (positions vides, axes manques)."""


def _load_thresholds() -> tuple[float, float, dict[str, dict], bool] | None:
    """Charge default + overrides + notify_on_breach depuis risk_watch.yaml.

    Returns (default_warn, default_breach, overrides, notify_on_breach), ou
    None si config manquante (fail-closed L15 : monitor refuse de tourner).
    """
    from shared.risk_watch import load_risk_watch
    cfg = load_risk_watch()
    if not cfg or "stress_gate" not in cfg or not cfg["stress_gate"]:
        log.warning("stress_gate config absente dans risk_watch.yaml")
        return None
    sg = cfg["stress_gate"]
    default = sg["default_thresholds"]
    return (
        float(default["warn_pct"]),
        float(default["breach_pct"]),
        sg.get("per_scenario_overrides") or {},
        bool(sg.get("notify_on_breach", True)),
    )


def classify_stress_scenario(
    result: dict,
    default_warn: float,
    default_breach: float,
    overrides: dict[str, dict],
) -> dict | None:
    """Classify un resultat run_stress_test() en {ok, warn, breach}.

    Args:
        result: dict retourne par factor_exposures.run_stress_test().
        default_warn: seuil warn global (negatif).
        default_breach: seuil breach global (negatif).
        overrides: dict scenario_name -> {warn_pct, breach_pct}.

    Returns:
        dict {scenario_name, status, drawdown_pct, warn_pct, breach_pct} ou
        None si scenario non-classifiable legitime (error/empty).

    Raises:
        MissingStressDataError : data critique manquante (drawdown_pct manquant).
    """
    if not result or "scenario" not in result:
        return None
    if "error" in result:
        return None  # scenario non-classifiable (ex unknown_scenario_or_empty_book)
    scenario_name = result["scenario"]
    if "total_drawdown_pct" not in result:
        raise MissingStressDataError(
            f"scenario {scenario_name}: total_drawdown_pct manquant"
        )
    dd = float(result["total_drawdown_pct"])

    # Override per-scenario si present
    ov = overrides.get(scenario_name) or {}
    warn = float(ov.get("warn_pct", default_warn))
    breach = float(ov.get("breach_pct", default_breach))

    if dd <= breach:
        status = "breach"
    elif dd <= warn:
        status = "warn"
    else:
        status = "ok"

    return {
        "scenario_name": scenario_name,
        "status": status,
        "drawdown_pct": dd,
        "warn_pct": warn,
        "breach_pct": breach,
    }


def _prev_status_for_scenario(scenario_name: str) -> str:
    """Lit derniere row du journal. Default 'ok' si jamais evalue.
    Decouple de tout autre journal (L4 monitor pattern)."""
    row = storage.get_latest_stress_gate_per_scenario(scenario_name)
    return row["status"] if row else "ok"


def _classify_transition(prev: str, new: str) -> str:
    """Classifie la transition entre 2 status. Actionable = enter_breach."""
    if prev == new:
        return "no_change"
    if new == "breach":
        return "enter_breach"
    if new == "warn":
        # ok -> warn ou breach -> warn (recovery partielle)
        return "recover_warn" if prev == "breach" else "enter_warn"
    if new == "ok":
        # warn -> ok ou breach -> ok (full recovery)
        return "recover_ok"
    return "no_change"


def _format_notify_message(cls: dict, all_breaches: list[dict]) -> str:
    """Format message Telegram lors entree breach."""
    n_breach = len(all_breaches)
    plural = "s" if n_breach > 1 else ""
    lines = [
        f"🚨 PRESAGE stress-gate : {n_breach} scenario{plural} en BREACH",
        "",
        f"Vient d'entrer : {cls['scenario_name']}",
        f"  Drawdown estime : {cls['drawdown_pct']:.1f}%",
        f"  Seuil breach : {cls['breach_pct']:.1f}%",
        "",
        "Tous les scenarios en breach :",
    ]
    for b in all_breaches:
        lines.append(
            f"  • {b['scenario_name']} : {b['drawdown_pct']:.1f}% "
            f"(seuil {b['breach_pct']:.1f}%)"
        )
    lines.extend([
        "",
        "Le book est sur-concentre. Cf docs/QUALITY_BAR.md Axe 4 :",
        "ballast strict insuffisant pour absorber stress factor.",
    ])
    return "\n".join(lines)


def check_all_stress_transitions() -> dict:
    """Pour chaque scenario : classify + detecte transition + notify + audit.

    Returns:
        stats {checked, ok, warn, breach, transitions, notified, errors}
    """
    stats = {
        "checked": 0,
        "ok": 0,
        "warn": 0,
        "breach": 0,
        "transitions": 0,
        "notified": 0,
        "errors": 0,
    }

    cfg = _load_thresholds()
    if cfg is None:
        log.warning("stress_gate config introuvable : monitor skip")
        return stats
    default_warn, default_breach, overrides, notify_on_breach = cfg

    from intelligence.factor_exposures import (
        _STRESS_SCENARIOS,
        run_stress_test,
    )

    # 1er pass : classify tous les scenarios pour avoir l'agregat
    classified: list[dict] = []
    for scenario_name in _STRESS_SCENARIOS:
        try:
            result = run_stress_test(scenario_name)
            try:
                cls = classify_stress_scenario(
                    result, default_warn, default_breach, overrides,
                )
            except MissingStressDataError as md:
                log.warning(f"stress_gate {scenario_name}: missing data: {md}")
                stats["errors"] += 1
                continue
            if cls is None:
                continue
            classified.append(cls)
        except Exception as e:
            log.warning(f"stress_gate: {scenario_name} failed: {e}")
            stats["errors"] += 1
            continue

    # Pre-calcul des breaches pour message coherent
    all_breaches = [c for c in classified if c["status"] == "breach"]

    # 2e pass : detecte transitions + notify + audit
    for cls in classified:
        try:
            stats["checked"] += 1
            stats[cls["status"]] += 1

            new_status = cls["status"]
            prev_status = _prev_status_for_scenario(cls["scenario_name"])
            transition = _classify_transition(prev_status, new_status)

            if transition != "no_change":
                stats["transitions"] += 1

            notified_flag = False
            if transition == "enter_breach" and notify_on_breach:
                try:
                    msg = _format_notify_message(cls, all_breaches)
                    notify.send_text(msg)
                    notified_flag = True
                    stats["notified"] += 1
                except Exception as e:
                    log.warning(
                        f"stress_gate notify {cls['scenario_name']} failed: {e}"
                    )

            storage.insert_stress_gate_alert(
                scenario_name=cls["scenario_name"],
                status=new_status,
                drawdown_pct=cls["drawdown_pct"],
                warn_pct=cls["warn_pct"],
                breach_pct=cls["breach_pct"],
                notified=notified_flag,
                transition=transition,
            )
        except Exception as e:
            log.warning(f"stress_gate audit {cls.get('scenario_name')}: {e}")
            stats["errors"] += 1
            continue

    return stats
