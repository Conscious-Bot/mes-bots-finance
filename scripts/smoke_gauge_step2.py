"""Smoke gate post-bascule étape 2 SPEC_GAUGE.

Vérifie 3 invariants par construction sur le HTML rendu :
1. ∀ tk ∈ Beyond ⇒ dot_v ≥ 90.0  (cur ≥ full natif ⇒ dot en lane droite)
2. ∀ tk ∈ Closest ⇒ dot_v < 90.0
3. ∀ tk affiché ⇒ _pr.has_band == True (aucun degraded en bucket split)

Si les 3 passent, le fork split/visuel est mort par construction (identité
littérale via _axis[tk]["_pr"] partagé).
"""
from __future__ import annotations
import re
import sys

sys.path.insert(0, '/Users/olivierlegendre/mes-bots-finance')

from dashboard import render as R

# Patch _axisrow pour capturer dot_v rendu (parsing HTML direct)
DOT_RE = re.compile(r'class="tbar-dot[^"]*"\s+style="left:([0-9.]+)%')


def main() -> int:
    # Importer les helpers nécessaires
    from shared import book as bk
    from shared.position_view import get_all_positions_views

    views = get_all_positions_views()
    book_idx = bk.get_book_index()

    # Reconstruire _axis localement EXACTEMENT comme render() (single-source pr)
    axis: dict[str, dict] = {}
    for tk, view in views.items():
        pr = R._gauge_prices_native(book_idx.get(tk))
        if not pr or not pr.get("has_band"):
            continue
        up, dn = view.upside_pct, view.downside_pct
        if up is None or dn is None:
            continue
        st, tg, c = pr["stop_native"], pr["full_native"], pr["cur_native"]
        axis[tk] = {"_stop": st, "_tgt": tg, "_cur": c, "_pr": pr}

    beyond = sorted([tk for tk in axis if axis[tk]["_cur"] >= axis[tk]["_tgt"]],
                    key=lambda tk: -(axis[tk]["_cur"] / axis[tk]["_tgt"]))[:6]
    targets = sorted([tk for tk in axis if axis[tk]["_cur"] < axis[tk]["_tgt"]],
                     key=lambda tk: -(axis[tk]["_cur"] / axis[tk]["_tgt"]))[:6]

    fails: list[str] = []

    # Assert 1 : Beyond → dot_v ≥ 90
    for tk in beyond:
        html = R._position_axis_price(axis[tk]["_pr"])
        m = DOT_RE.search(html)
        if not m:
            fails.append(f"{tk} (Beyond): no dot in HTML")
            continue
        dot_v = float(m.group(1))
        if dot_v < 90.0:
            fails.append(f"{tk} ∈ Beyond mais dot_v={dot_v:.1f} (< 90)")

    # Assert 2 : Closest → dot_v < 90
    for tk in targets:
        html = R._position_axis_price(axis[tk]["_pr"])
        m = DOT_RE.search(html)
        if not m:
            fails.append(f"{tk} (Closest): no dot in HTML")
            continue
        dot_v = float(m.group(1))
        if dot_v >= 90.0:
            fails.append(f"{tk} ∈ Closest mais dot_v={dot_v:.1f} (>= 90)")

    # Assert 3 : aucun degraded en bucket split
    for tk in beyond + targets:
        if not axis[tk]["_pr"].get("has_band"):
            fails.append(f"{tk}: degraded en bucket split (has_band=False)")

    print(f"Tickers in axis: {len(axis)}")
    print(f"Beyond: {beyond}")
    print(f"Closest: {targets}")

    if fails:
        print(f"\nFAILS ({len(fails)}):")
        for f in fails:
            print(f"  - {f}")
        return 1

    print(f"\nSMOKE OK ✓ ({len(beyond)} Beyond + {len(targets)} Closest, has_band all True)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
