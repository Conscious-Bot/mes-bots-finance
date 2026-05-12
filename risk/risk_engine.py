"""Validation avant tout output décisionnel."""
from dataclasses import dataclass
from shared import storage, config

@dataclass
class ValidationResult:
    ok: bool
    reasons: list
    severity: str

def validate(decision: dict) -> ValidationResult:
    """decision: {ticker, action, size_pct, conviction, sector, narrative}"""
    reasons = []
    cfg = config.load()
    state = storage.load_state()

    dd = state["drawdown_pct"]
    if dd >= cfg["risk"]["drawdown_stop_pct"]:
        return ValidationResult(False, [f"Drawdown STOP ({dd:.1%})"], "block")
    if dd >= cfg["risk"]["drawdown_reduce_pct"]:
        if decision.get("size_pct", 0) > cfg["style"]["position_max_pct"] * 0.5:
            reasons.append(f"Drawdown reduce: size halved (current {dd:.1%})")
            decision["size_pct"] *= 0.5

    if decision.get("size_pct", 0) > cfg["style"]["position_max_pct"]:
        reasons.append(f"Size > max_pct {cfg['style']['position_max_pct']}")
        return ValidationResult(False, reasons, "block")

    if decision.get("conviction", 0) < cfg["style"]["conviction_min"]:
        reasons.append(f"Conviction < min {cfg['style']['conviction_min']}")
        return ValidationResult(False, reasons, "block")

    if state.get("paper_only", True) and decision.get("execute_real", False):
        return ValidationResult(False, ["paper_only mode active"], "block")

    severity = "info" if not reasons else "warn"
    return ValidationResult(True, reasons, severity)
