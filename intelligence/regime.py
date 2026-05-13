"""Regime detector: synthesize macro/sentiment into actionable labels.

Inputs: shared.macro.get_macro_snapshot()
Output: regime label + sub-regimes + signals + implications.

Archetypes:
- CRYPTO-TOP-ZONE: F&G >=80, DIRECT trigger anti-FOMO BTC/ETH
- CRYPTO-BOTTOM-ZONE: F&G <=20, asymmetric entry
- RISK-OFF: VIX > 30, equity stress
- LATE-CYCLE-WARNING: yield curve inverted ou M2 contracting
- COMPLACENCY: VIX < 13
- NEUTRAL / MIXED
"""

from typing import Any

from shared import macro


def detect_regime(snap: dict[str, Any] | None = None) -> dict[str, Any]:
    if snap is None:
        snap = macro.get_macro_snapshot()

    vix = snap.get("vix")
    fng_obj = snap.get("btc_fng")
    fng = fng_obj.get("value") if fng_obj else None
    yc_obj = snap.get("yield_curve")
    yc = yc_obj.get("spread_pct") if yc_obj else None
    m2_obj = snap.get("m2_yoy")
    m2 = m2_obj.get("yoy_pct") if m2_obj else None

    signals = []

    if vix is not None:
        if vix > 30:
            signals.append(("EQUITY", "risk-off", f"VIX {vix:.1f} > 30 = stress"))
        elif vix > 22:
            signals.append(("EQUITY", "caution", f"VIX {vix:.1f} elevated"))
        elif vix < 13:
            signals.append(("EQUITY", "complacency", f"VIX {vix:.1f} < 13 complacency"))
        else:
            signals.append(("EQUITY", "normal", f"VIX {vix:.1f} normal"))

    if fng is not None:
        if fng >= 80:
            signals.append(
                ("CRYPTO", "extreme-greed", f"F&G {fng} >= 80 - TOP ZONE. FOMO bias trigger. Trim BTC/ETH justifie.")
            )
        elif fng >= 65:
            signals.append(("CRYPTO", "greed", f"F&G {fng} greed building"))
        elif fng <= 20:
            signals.append(("CRYPTO", "extreme-fear", f"F&G {fng} <= 20 - capitulation, entries asymetriques"))
        elif fng <= 35:
            signals.append(("CRYPTO", "fear", f"F&G {fng} fear"))
        else:
            signals.append(("CRYPTO", "neutral", f"F&G {fng} neutral"))

    if yc is not None:
        if yc < 0:
            signals.append(("MACRO", "late-cycle", f"Yield curve inverted {yc:+.2f}% - recession watch"))
        elif yc < 0.3:
            signals.append(("MACRO", "flattening", f"Yield curve flat {yc:+.2f}%"))
        else:
            signals.append(("MACRO", "normal-curve", f"Yield curve {yc:+.2f}% normal"))

    if m2 is not None:
        if m2 < 0:
            signals.append(("MACRO", "tight-money", f"M2 YoY {m2:+.1f}% contracting"))
        elif m2 > 7:
            signals.append(("MACRO", "loose-money", f"M2 YoY {m2:+.1f}% loose"))
        else:
            signals.append(("MACRO", "normal-m2", f"M2 YoY {m2:+.1f}% normal"))

    crypto_sigs = [s for s in signals if s[0] == "CRYPTO"]
    equity_sigs = [s for s in signals if s[0] == "EQUITY"]
    macro_sigs = [s for s in signals if s[0] == "MACRO"]

    crypto_regime = crypto_sigs[0][1] if crypto_sigs else "unknown"
    equity_regime = equity_sigs[0][1] if equity_sigs else "unknown"
    macro_regime = "+".join([s[1] for s in macro_sigs]) if macro_sigs else "unknown"

    if crypto_regime == "extreme-greed":
        overall = "CRYPTO-TOP-ZONE"
    elif crypto_regime == "extreme-fear":
        overall = "CRYPTO-BOTTOM-ZONE"
    elif equity_regime == "risk-off":
        overall = "RISK-OFF"
    elif any("late-cycle" in s[1] or "tight-money" in s[1] for s in macro_sigs):
        overall = "LATE-CYCLE-WARNING"
    elif equity_regime == "complacency":
        overall = "COMPLACENCY"
    elif equity_regime == "normal" and crypto_regime in ("neutral", "greed", "fear"):
        overall = "NEUTRAL"
    else:
        overall = "MIXED"

    return {
        "overall": overall,
        "equity": equity_regime,
        "crypto": crypto_regime,
        "macro": macro_regime,
        "signals": signals,
        "snapshot": snap,
        "implications": _implications(overall),
    }


def _implications(overall):
    table = {
        "CRYPTO-TOP-ZONE": [
            "BTC/ETH: trim partiel mecanique anti-FOMO",
            "MSTR/COIN/RIOT: exposure caution",
        ],
        "CRYPTO-BOTTOM-ZONE": [
            "BTC/ETH: zone accumulation asymetrique",
        ],
        "RISK-OFF": [
            "AI/semis cycliques: reduce, defensives preferred",
            "Crypto: drawdown probable",
        ],
        "LATE-CYCLE-WARNING": [
            "Cyclicals (AI/semis): scale-in conservateur",
            "Hedge: defensives (PG, V), considerer cash",
        ],
        "COMPLACENCY": [
            "Tail risk underpriced - hedges cheap",
            "AI/semis bull thesis tient mais vigilance retournement",
        ],
        "NEUTRAL": [
            "Stick to thesis-driven sizing, regime non-binding",
        ],
        "MIXED": [
            "Signaux conflicting - defer aux fondamentaux signal-specific",
        ],
    }
    return table.get(overall, [])


def format_regime(r: dict[str, Any]) -> str:
    lines = [f"REGIME: {r['overall']}"]
    lines.append(f"  Equity:  {r['equity']}")
    lines.append(f"  Crypto:  {r['crypto']}")
    lines.append(f"  Macro:   {r['macro']}")
    lines.append("")
    lines.append("Signals:")
    for sig in r["signals"]:
        lines.append(f"  [{sig[0]:6}] {sig[2]}")
    if r["implications"]:
        lines.append("")
        lines.append("Implications:")
        for imp in r["implications"]:
            lines.append(f"  - {imp}")
    return "\n".join(lines)


if __name__ == "__main__":
    r = detect_regime()
    print(format_regime(r))
