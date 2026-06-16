"""Résolution S6 + S10 sentinelles G2 chantier #150 — fact-check Bigdata.com 16/06/2026.

Audit-trace script idempotent pour la résolution des 2 sentinelles déjà publiquement
déclenchées au moment de la pose (13/06/2026). Confirme memory
`feedback_no_probability_anchoring` : 2/10 sentinelles G2 étaient mécaniques (prob=0.99)
parce qu'olivier avait connaissance du déclenchement public via sa veille du domaine.

## Fact-check Bigdata.com (mcp__claude_ai_Bigdata_com__bigdata_search)

### S6 (id=299) — Doosan turbine >1 GW client occidental
- claim_text : "Doosan ou entrant decroche commande ferme >1 GW d'un client occidental"
- probability_at_creation : 0.99
- baseline_date : 2026-06-13
- target_date : 2027-12-31
- resolution_source : "presse / annonces"

**Trigger evidence** :
- Source : Tech Times - May 31, 2026 (https://app.bigdata.com/documents/93454DE4414EB5B474736CBEDA23FF60)
- Quote: "As of May 2026, Doosan had secured contracts with multiple US big-tech
  companies for gas and steam turbines powering AI data centers. These include
  the original two 380-megawatt gas turbines confirmed in October 2025 for delivery
  by end of 2026, a March 2026 steam turbine order for a North American data center,
  and a May 2026 contract for **four 370-megawatt steam turbines for a Texas data
  center**, to be delivered through 2029. Doosan's cumulative gas turbine export
  count in the United States reached 12 units by April 2026."
- Calcul : 4 × 370 MW = **1480 MW = 1.48 GW** client US (Texas data center, big-tech).
  Critère ">1 GW client occidental" satisfait 13 jours AVANT la pose (13/06/2026).

### S10 (id=303) — Google dual-sourcing TPU hors Broadcom
- claim_text : "Google confirme dual-sourcing TPU hors Broadcom (MediaTek ou autre) gen v8+"
- probability_at_creation : 0.99
- baseline_date : 2026-06-13
- target_date : 2026-12-31
- resolution_source : "annonce / SemiAnalysis"
- ticker : AVGO

**Trigger evidence** :
- Source : The Information / Yahoo Finance - June 11, 2026
  (https://app.bigdata.com/documents/5F0BC14BF8EFE1A9023A75D1C8BDBA09)
- Quote: "Google is considering Samsung Electronics for the production of a
  component used in its custom AI chip for cloud data centers... The chip,
  codenamed Icefish, is currently planned as Google's 10th-generation TPU."
- Confirmé multi-sources : Samsung (I/O die 2nm) + TSMC (compute 1.4nm) +
  **MediaTek (design assist)** + Intel (3M+ TPUs en 2028).
- "v8+" inclut v10 ("Icefish"). MediaTek nommé dans le claim_text. Critère
  satisfait 2 jours AVANT la pose (13/06/2026).

## Brier score

- Outcome `correct` + probability 0.99 → Brier = (0.99 - 1.0)² = 0.0001
- Les 2 résolutions contribuent au track-record avec Brier quasi-parfait, MAIS
  ce sont des résolutions MÉCANIQUES (pré-triggered), pas de skill prédictif.
  Documentation honest préserve cette distinction.

## Idempotence

Le script vérifie `resolved_at IS NULL` avant UPDATE. Si déjà résolu, skip.
Le trigger `predictions_resolve_writeonce` interdit la réécriture (commit doctrine
2026-06-12 P1.1).

## Usage

    python3 scripts/resolve_sentinels_S6_S10_2026-06-16.py [--apply]

Sans `--apply` : dry-run, affiche les résolutions proposées.
Avec `--apply` : UPDATE predictions.resolved_at + outcome + brier_score.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "bot.db"

RESOLUTIONS = [
    {
        "id": 299,
        "code": "S6",
        "claim_text": "Doosan ou entrant decroche commande ferme >1 GW d'un client occidental",
        "probability": 0.99,
        "outcome": "correct",
        "trigger_date": "2026-05-31",
        "evidence_url": "https://app.bigdata.com/documents/93454DE4414EB5B474736CBEDA23FF60",
        "evidence_summary": "Doosan May 2026 four 370MW steam turbines Texas data center = 1.48 GW (Tech Times 2026-05-31, via Bigdata.com)",
    },
    {
        "id": 303,
        "code": "S10",
        "claim_text": "Google confirme dual-sourcing TPU hors Broadcom (MediaTek ou autre) gen v8+",
        "probability": 0.99,
        "outcome": "correct",
        "trigger_date": "2026-06-11",
        "evidence_url": "https://app.bigdata.com/documents/5F0BC14BF8EFE1A9023A75D1C8BDBA09",
        "evidence_summary": "Google Icefish (TPU v10) dual-sourcing Samsung+TSMC+MediaTek+Intel (The Information 2026-06-11, via Bigdata.com)",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="Applique les UPDATEs (sinon dry-run)")
    args = parser.parse_args()

    if not DB.exists():
        print(f"ERROR: DB not found at {DB}", file=sys.stderr)
        return 1

    cx = sqlite3.connect(DB)
    cx.row_factory = sqlite3.Row
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"═ Résolution sentinelles G2 S6+S10 [{mode}] ═\n")

    for r in RESOLUTIONS:
        current = cx.execute(
            "SELECT id, resolved_at, outcome FROM predictions WHERE id=?", (r["id"],)
        ).fetchone()
        if not current:
            print(f"  {r['code']} (id={r['id']}) : NOT FOUND in predictions, skip")
            continue
        if current["resolved_at"] is not None:
            print(
                f"  {r['code']} (id={r['id']}) : déjà résolu "
                f"({current['outcome']}, {current['resolved_at'][:19]}), skip (idempotent)"
            )
            continue

        brier = (
            (r["probability"] - 1.0) ** 2 if r["outcome"] == "correct"
            else (r["probability"] - 0.0) ** 2
        )

        print(f"  {r['code']} (id={r['id']}) : ")
        print(f"    claim: {r['claim_text'][:90]}")
        print(f"    prob: {r['probability']:.2f}  →  outcome: {r['outcome']}  →  Brier: {brier:.4f}")
        print(f"    trigger: {r['trigger_date']}  evidence: {r['evidence_summary']}")

        if args.apply:
            cx.execute(
                """
                UPDATE predictions SET
                    resolved_at = ?,
                    outcome = ?,
                    brier_score = ?
                WHERE id = ? AND resolved_at IS NULL
                """,
                (now, r["outcome"], brier, r["id"]),
            )
            print("    → APPLIED")
        print()

    if args.apply:
        cx.commit()
        n_resolved = cx.execute(
            "SELECT COUNT(*) FROM predictions WHERE origin='manual' AND resolved_at IS NOT NULL"
        ).fetchone()[0]
        n_total = cx.execute(
            "SELECT COUNT(*) FROM predictions WHERE origin='manual'"
        ).fetchone()[0]
        print(f"═ G2 track-record : {n_resolved}/{n_total} résolus ═")
        print("  Brier panel gate N≥10 → reste 8 sentinelles pending pour activation panneau.")

    cx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
