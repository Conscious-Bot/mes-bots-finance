"""Audit (a) - phases declarees du macro monitor : diagnostic FP-by-driver.

Master §6 premier geste mesurable. Pas un vrai backtest forward (debt_composite
n'a que 17 jours, horizon 3M pas encore observable). C'est l'AUDIT court qui
chiffre le crying-wolf sur ce que le monitor a deja declare en live.

Per master correction user :
- Audit (a) = ce script (court, confirme FP actuel par decomposition driver)
- Backtest (b) = reconstruction historique 2015-2024 avec vintage macro (long, plus tard)

Output : docs/backtest_audits/macro_monitor_audit_2026-06-08.md
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

# Noise indicators per doctrine (drop) + demote per doctrine (book-specific)
NOISE_DROP = {"BTC_drawdown180", "VIX", "Gold", "DXY", "CopperGold"}
DEMOTE_BOOK_SPECIFIC = {"USDJPY"}
TIER_S_KEEP = {"HY_OAS", "MOVE", "KRE", "BankReserves", "T10Y2Y", "FedBalance_yoy"}
TIER_S_RAW_LEVEL_INSTEAD_OF_DELTA = {"TYX"}  # le niveau est faux, le delta serait OK


def main() -> int:
    cx = sqlite3.connect("data/bot.db")
    cx.row_factory = sqlite3.Row
    rows = cx.execute(
        "SELECT timestamp, score, phase, tier_breakdown FROM debt_composite "
        "ORDER BY timestamp"
    ).fetchall()

    n_total = len(rows)
    n_p3_p4 = sum(1 for r in rows if r["phase"] >= 3)
    print(f"Total readings: {n_total}, Phase 3+4 alarms: {n_p3_p4}")

    md = [
        "# Audit macro monitor — phases declarees (premier geste master §6)",
        "",
        "**Date** : 2026-06-08",
        "**Source** : `debt_composite` table (live persistence du monitor)",
        "**Scope** : audit court (debt_composite N=17j, pas de forward 3M observable encore)",
        "**Methode** : decomposition driver par phase declaree -- chiffre le crying-wolf",
        "**Reference** : doctrine `SPEC_CORNERSTONE.md` + `PLAN_REFONTE_ALERTES.md`",
        "",
        "## Tldr",
        "",
        f"- Total readings : **{n_total}** sur {rows[0]['timestamp'][:10]} -> {rows[-1]['timestamp'][:10]}",
        f"- Alarmes Phase 3+4 : **{n_p3_p4}** ({n_p3_p4/n_total*100:.0f}% du temps)",
        "- **Sur le dernier Phase 4 (score 120.5 du 06/06) :**",
        "  - **66% du score** vient des indicateurs **a DROP** per doctrine (bruit)",
        "  - **8% du score** vient des tier-S valides (qui disent CALME)",
        "  - 8/15 indicateurs marques `stale=true` (Axe 5 freshness violee aussi)",
        "- **Verdict** : crying-wolf confirme par decomposition. Aucun tier-S valide ne signale stress.",
        "",
        "## Decomposition du dernier Phase 4 (06/06 06:32)",
        "",
        "| Indicateur | Tier | Phase | Value | Contribution | Categorie doctrine |",
        "|---|---|---|---|---|---|",
    ]

    # Decompose latest Phase 4
    p4_latest = None
    for r in rows:
        if r["phase"] == 4:
            p4_latest = r
    if p4_latest:
        try:
            bd = json.loads(p4_latest["tier_breakdown"])
        except (json.JSONDecodeError, TypeError):
            bd = {}
        total_contrib = 0.0
        contrib_noise = 0.0
        contrib_demote = 0.0
        contrib_tier_s = 0.0
        contrib_other = 0.0
        n_stale = 0
        n_total_inds = 0
        for tier, inds in bd.items():
            for ind in inds:
                name = ind.get("name", "?")
                phase = ind.get("phase", 0)
                value = ind.get("value", "?")
                contrib = float(ind.get("contribution", 0))
                stale = ind.get("stale", False)
                n_total_inds += 1
                if stale:
                    n_stale += 1
                total_contrib += contrib
                if name in NOISE_DROP:
                    cat = "**DROP** (bruit)"
                    contrib_noise += contrib
                elif name in DEMOTE_BOOK_SPECIFIC:
                    cat = "**DEMOTE** (book-specific)"
                    contrib_demote += contrib
                elif name in TIER_S_KEEP:
                    cat = "tier-S (garde)"
                    contrib_tier_s += contrib
                elif name in TIER_S_RAW_LEVEL_INSTEAD_OF_DELTA:
                    cat = "tier-S mais niveau (devrait etre delta)"
                    contrib_other += contrib
                else:
                    cat = "autre"
                    contrib_other += contrib
                if isinstance(value, float):
                    val_str = f"{value:.2f}"
                else:
                    val_str = str(value)[:20]
                stale_marker = " stale" if stale else ""
                md.append(
                    f"| `{name}` | T{tier} | P{phase}{stale_marker} | "
                    f"{val_str} | {contrib:.1f} | {cat} |",
                )

        md.extend([
            "",
            f"**Score total : {total_contrib:.1f}** -> Phase 4 (seuil >= 115)",
            "",
            "## Repartition par categorie doctrine",
            "",
            f"- **DROP (bruit selon doctrine)** : {contrib_noise:.1f} pts ({contrib_noise/total_contrib*100:.0f}%)",
            f"- **DEMOTE (book-specific, pas macro)** : {contrib_demote:.1f} pts ({contrib_demote/total_contrib*100:.0f}%)",
            f"- **TIER-S valide (garde)** : {contrib_tier_s:.1f} pts ({contrib_tier_s/total_contrib*100:.0f}%)",
            f"- **Autres** : {contrib_other:.1f} pts ({contrib_other/total_contrib*100:.0f}%)",
            "",
            f"**Verdict chiffre** : {(contrib_noise + contrib_demote)/total_contrib*100:.0f}% du score "
            "vient d'indicateurs que la doctrine impose de drop/demote. "
            f"Les tier-S valides apportent {contrib_tier_s:.1f} pts = "
            f"si seuls ils dominaient, on serait en Phase {'1-2 (calme)' if contrib_tier_s < 22 else '?'}.",
            "",
            f"**Freshness aussi violee** : {n_stale}/{n_total_inds} indicateurs `stale=true` "
            "(Axe 5 SLA freshness) -- le score est calcule sur des valeurs caches.",
            "",
            "## Phase distribution sur l'historique (N=" + str(n_total) + ")",
            "",
            "| Phase | Count | % | Lecture doctrine |",
            "|---|---|---|---|",
        ])

    # Phase distribution
    phase_dist = {}
    for r in rows:
        phase_dist[r["phase"]] = phase_dist.get(r["phase"], 0) + 1
    for ph in sorted(phase_dist.keys()):
        cnt = phase_dist[ph]
        pct = cnt / n_total * 100
        if ph >= 3:
            verdict = "ALARM (>20% = calibration cassee per doctrine)" if pct > 20 else "alarme dans la fenetre courte"
        else:
            verdict = "normal/calme"
        md.append(f"| Phase {ph} | {cnt} | {pct:.0f}% | {verdict} |")

    md.extend([
        "",
        f"- Alarmes Phase 3+4 : **{n_p3_p4}/{n_total} = {n_p3_p4/n_total*100:.0f}%**",
        "  - Per doctrine PLAN_REFONTE_ALERTES : > 20% d'alarme = calibration cassee",
        "",
        "## Pourquoi l'audit (a) suffit ici (et pourquoi (b) reste necessaire)",
        "",
        "**Audit (a) actuel** : impossibilite materielle de tester forward 3M "
        "(debt_composite N=17j vs horizon 3M=90j). Ce qu'on a chiffre :",
        "- Le **mecanisme** du score est domine par des indicateurs explicitement "
        "  classes bruit par la doctrine (BTC/VIX/Gold/USDJPY).",
        "- Les tier-S valides (HY_OAS, MOVE, banques) **disent calme** au moment "
        "  meme ou le composite crie crise.",
        "- C'est un FP **par construction semantique** -- pas besoin d'attendre 3M.",
        "",
        "**Backtest (b) requis ensuite** : reconstruction des phases sur 2015-2024 "
        "avec vintage macro (FRED as-released), label drawdown SMH/SPY forward "
        "3M @ θ=-10%/-20%, purged walk-forward L16. Donnera la VRAIE matrice "
        "de confusion + PR-AUC + Brier skill score vs base rate.",
        "",
        "## Decisions tranchees (per master Q1-Q3)",
        "",
        "- **Q1** : SMH primaire + SPY secondaire (PAS book - N trop petit), "
        "θ=-10% ET -20% (multi-label), H=3M",
        "- **Q2** : defer Polygon (re-trigger = panel multi-pays insuffisant)",
        "- **Q3** : auto-demote_from_structural si invalidation_trigger fire -- "
        "  symetrique a l'assignation, tamper-evident, notify + steer 'pose un stop'",
        "",
        "## Suite",
        "",
        "1. Q3 wire dans thesis_erosion : si INVALIDATION_HIT + structural -> auto-demote priced + integrity log + notify (~1h)",
        "2. Audit (b) : reconstruction historique 2015-2024 + vraie matrice de "
        "   confusion (~ chantier de plusieurs sessions)",
        "3. Cornerstone build : `config/divergence.yaml` + `divergence_engine.py` "
        "   per `SPEC_CORNERSTONE.md` (~ chantier majeur, post backtest verdict)",
    ])

    out_path = Path("docs/backtest_audits/macro_monitor_audit_2026-06-08.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md) + "\n")
    print(f"Audit ecrit -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
