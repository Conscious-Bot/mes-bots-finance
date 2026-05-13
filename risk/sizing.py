"""Position sizing. UNE seule formule. PAS de cascade. Réf: tennis-bot AUDIT.md."""
from shared import config


def position_size(edge_pct: float, variance_estimate: float,
                  capital: float, regime_factor: float = 1.0) -> float:
    """Quarter Kelly + cap dur. UNE modulation régime. 3 étapes max."""
    if edge_pct <= 0 or variance_estimate <= 0:
        return 0.0
    cfg = config.load()
    max_pct = cfg["style"]["position_max_pct"]
    raw_kelly = edge_pct / variance_estimate
    sized = capital * raw_kelly * 0.25 * regime_factor
    capped = min(sized, capital * max_pct)
    return max(0.0, capped)

def test_no_cascade():
    s = position_size(0.30, 0.25, 10000, 1.0)
    assert s <= 10000 * 0.05, f"Sizing {s} viole le cap"
    assert position_size(0.0, 0.25, 10000) == 0.0
    assert position_size(-0.1, 0.25, 10000) == 0.0
    print(f"OK sizing tests passed. Sample size = ${s:.2f}")

if __name__ == "__main__":
    test_no_cascade()
