"""SPEC_THESIS_ALPHA_RESOLVER pièce 5 — aggregator track-record fail-closed L19.

Lit thesis_predictions résolus → calcule hit_rate + Brier + CI cluster-bootstrap
vs baseline taux-de-base p̄(1−p̄) → verdict {insufficient_n, no_skill_detected,
skill_detected, anti_skill_detected}.

Doctrine :
- L17 : passerelle DB unique via shared.storage.db()
- L19 : fail-closed verdict ("insufficient_n" jusqu'à CI strictement hors baseline)
- L22 : N_effective via cluster (block) bootstrap — ré-échantillonne les clusters
        pas les preds individuelles, pour refléter la corrélation honnêtement
- L27 : invariants par construction (gates verdict nommés sur pool BRIER)

Architecture lock storage-only : imports = shared.storage + stdlib uniquement.
Aucun module qui tire la chaîne lourde (shared.prices → data_sources.gmail_ →
google.auth → ...). Vérifié par test subprocess transitif (interpréteur frais).

Cluster strategy (défaut "currency") : table thesis_predictions n'a pas de
colonne sector. Le cluster (currency,) est conservateur (sur-cluster KRW/semis
et KRW/finance ensemble) — CI plus large = fail-closed plus fort. Raffinement
(currency, sector) possible via JOIN watchlist.sector future si on veut plus
de granularité ; pour l'instant on tient le défaut honnête.

Fail-closed cas-bord clés :
- p̄ outcomes (PAS direction_correct) : un book parfait 20-bull-juste +
  20-bear-juste a p_direction=1.0 mais p_outcome=0.5. Confondre les deux
  donne baseline=0 → book parfait classé anti_skill = inversion catastrophique.
  Le baseline est calculé sur sign(alpha_realized_pct), JAMAIS sur direction_correct.
- Gates verdict (règles 1-2) nommés sur n_brut_brier / n_clusters_brier :
  le verdict est une claim de skill confidence-weighté → seul le pool Brier
  le gate. Pool accuracy peuplé mais pool Brier vide → insufficient_n.
- n_clusters_brier < 2 : impossible de bootstrap-cluster → insufficient_n
  (plancher principielle, pas seuil L16 fabriqué).
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal

from shared.storage import db

Verdict = Literal[
    "insufficient_n",
    "no_skill_detected",
    "skill_detected",
    "anti_skill_detected",
]

ClusterStrategy = Literal["currency", "ticker"]


def _cluster_key(
    ticker: str,
    native_currency: str,
    strategy: ClusterStrategy,
) -> tuple[str, ...]:
    """Clé de cluster pour une prediction.

    - 'currency' (défaut prod) : (currency,) — corrélation FX/régime. Conservateur
      (sur-cluster industrie). Re-pose annuelle même ticker = même cluster
      → collapsée (pas un pari indépendant).
    - 'ticker' : (ticker,) — chaque ticker un cluster. Usage tests synthétiques
      qui veulent désactiver le clustering corrélation pour isoler un autre
      mécanisme (ex T1 isolement du fix baseline-outcomes).
    """
    if strategy == "ticker":
        return (ticker,)
    return (native_currency,)


def _base_rate_brier(alpha_values: list[float]) -> float:
    """Baseline taux-de-base = p̄(1−p̄) où p̄ = P(alpha>0) observé.

    PAS p̄ = P(call juste) — ils coïncident sur book 100% bull et s'INVERSENT
    sur book mixte (20-bull-juste + 20-bear-juste : p_direction=1.0 →
    baseline=0 → book parfait classé anti_skill = inversion catastrophique).
    """
    if not alpha_values:
        return 0.25
    outcomes = [1 if a > 0 else 0 for a in alpha_values]
    p_bar = sum(outcomes) / len(outcomes)
    return p_bar * (1.0 - p_bar)


def _cluster_bootstrap_ci(
    values_by_cluster: dict[tuple, list[float]],
    *,
    iters: int = 2000,
    seed: int = 42,
) -> tuple[float, float]:
    """Block bootstrap : ré-échantillonne les CLUSTERS, pas les preds.

    Capture la corrélation intra-cluster honnêtement. Sur 1 cluster (impossible
    par le caller — gate n_clusters>=2 en amont), ou cluster dominant, le CI
    dégénère/élargit → verdict 'no_skill' honnête, pas un faux 'skill' iid.

    Requires : len(values_by_cluster) >= 2 et au moins un cluster non-vide.
    """
    rng = random.Random(seed)
    keys = list(values_by_cluster)
    boot_means: list[float] = []
    for _ in range(iters):
        sampled = [rng.choice(keys) for _ in keys]
        pooled = [v for k in sampled for v in values_by_cluster[k]]
        if not pooled:
            continue
        boot_means.append(sum(pooled) / len(pooled))
    boot_means.sort()
    n = len(boot_means)
    lo_idx = int(0.025 * n)
    hi_idx = min(int(0.975 * n), n - 1)
    return boot_means[lo_idx], boot_means[hi_idx]


def compute_alpha_track_record(
    *,
    cluster_strategy: ClusterStrategy = "currency",
    bootstrap_iters: int = 2000,
    bootstrap_seed: int = 42,
) -> dict[str, Any]:
    """Agrège track-record alpha sur thesis_predictions résolus.

    Lit pool résolus scorables (SPEC §4.1 axes orthogonaux : resolution_status
    = 'resolved' ET exclude_reason IS NULL → exclut 'abandoned', 'neutral',
    'no_bet'). Partitionne en pool accuracy (direction_correct IS NOT NULL)
    et pool Brier (magnitude_score IS NOT NULL AND alpha_realized_pct IS NOT NULL).

    Layer = 'thesis_alpha' (perception variante stock-picking, fx-stripped,
    regime-stripped). PAS comparable avec brier_signal ni pnl_eur (cf SPEC §0
    decision E : déclaré explicitement dans output).

    Args:
        cluster_strategy : 'currency' (défaut prod) ou 'ticker' (tests).
        bootstrap_iters : itérations bootstrap (défaut 2000, suffisant pour
            CI 95% stables).
        bootstrap_seed : seed RNG (défaut 42, reproducible).

    Returns:
        dict avec layer, asof, n_brut_*, n_clusters_*, hit_rate(+CI),
        brier_score(+CI), baseline_brier_observed, baseline_brier_fixed_ref,
        verdict, verdict_reason, low_power_flag.
    """
    # 1. Lecture pool résolus (axes orthogonaux SPEC §4.1 : la partition
    # par colonnes d'outcome (étape 2) gate déjà tous les exclusions
    # — abandoned a direction_correct=NULL + magnitude=NULL, neutral idem.
    # Pas de gate redondant sur resolution_status/exclude_reason ici : §4.1
    # a explicitement dému ces diagnostics du scoring.
    with db() as cx:
        rows = cx.execute(
            """
            SELECT direction_correct, magnitude_score, alpha_realized_pct,
                   ticker, native_currency
              FROM thesis_predictions
             WHERE resolved_at IS NOT NULL
            """
        ).fetchall()

    # 2. Partition pool accuracy vs pool Brier (orthogonaux par décision SPEC)
    # Pool accuracy : direction_correct in {0,1}, indépendant de magnitude
    # Pool Brier : magnitude_score IS NOT NULL ET alpha IS NOT NULL (besoin
    #              de l'outcome sign(alpha) pour baseline taux-de-base)
    accuracy_pool: list[tuple[int, tuple[str, ...]]] = []
    brier_pool: list[tuple[float, float, tuple[str, ...]]] = []
    for row in rows:
        direction_correct = row["direction_correct"]
        magnitude_score = row["magnitude_score"]
        alpha_realized_pct = row["alpha_realized_pct"]
        ticker = row["ticker"]
        native_currency = row["native_currency"]
        ckey = _cluster_key(ticker, native_currency, cluster_strategy)
        if direction_correct is not None:
            accuracy_pool.append((int(direction_correct), ckey))
        if magnitude_score is not None and alpha_realized_pct is not None:
            brier_pool.append((float(magnitude_score), float(alpha_realized_pct), ckey))

    n_brut_accuracy = len(accuracy_pool)
    n_brut_brier = len(brier_pool)
    n_clusters_accuracy = len({c for _, c in accuracy_pool})
    n_clusters_brier = len({c for _, _, c in brier_pool})

    # 3. Hit rate + CI cluster-bootstrap
    if n_brut_accuracy == 0:
        hit_rate: float | None = None
        hit_rate_ci_95: tuple[float, float] | None = None
    else:
        hit_rate = sum(d for d, _ in accuracy_pool) / n_brut_accuracy
        if n_clusters_accuracy >= 2:
            buckets: dict[tuple, list[float]] = defaultdict(list)
            for d, c in accuracy_pool:
                buckets[c].append(float(d))
            hit_rate_ci_95 = _cluster_bootstrap_ci(
                dict(buckets), iters=bootstrap_iters, seed=bootstrap_seed,
            )
        else:
            hit_rate_ci_95 = None

    # 4. Brier + CI + baseline taux-de-base (sur OUTCOMES sign(alpha))
    if n_brut_brier == 0:
        brier_score: float | None = None
        brier_ci_95: tuple[float, float] | None = None
        baseline_brier_observed = 0.25  # fallback principielle pool vide
    else:
        brier_score = sum(m for m, _, _ in brier_pool) / n_brut_brier
        baseline_brier_observed = _base_rate_brier(
            [a for _, a, _ in brier_pool]
        )
        if n_clusters_brier >= 2:
            buckets_b: dict[tuple, list[float]] = defaultdict(list)
            for m, _, c in brier_pool:
                buckets_b[c].append(float(m))
            brier_ci_95 = _cluster_bootstrap_ci(
                dict(buckets_b), iters=bootstrap_iters, seed=bootstrap_seed,
            )
        else:
            brier_ci_95 = None

    # 5. Verdict fail-closed L19 — gates nommés sur pool BRIER
    # Le verdict est une claim de skill confidence-weighté → seul le pool
    # Brier le gate. Pool accuracy peuplé mais pool Brier vide → insufficient_n.
    if n_brut_brier == 0:
        verdict: Verdict = "insufficient_n"
        verdict_reason = "no resolved scorable predictions in brier pool"
    elif n_clusters_brier < 2:
        verdict = "insufficient_n"
        verdict_reason = (
            f"cannot cluster-bootstrap with n_clusters_brier={n_clusters_brier} "
            f"(need >= 2 for honest correlation-adjusted CI)"
        )
    else:
        assert brier_ci_95 is not None  # garanti par n_clusters_brier >= 2
        lo, hi = brier_ci_95
        if hi < baseline_brier_observed:
            verdict = "skill_detected"
            verdict_reason = (
                f"brier CI [{lo:.4f}, {hi:.4f}] strictly below "
                f"baseline {baseline_brier_observed:.4f}"
            )
        elif lo > baseline_brier_observed:
            verdict = "anti_skill_detected"
            verdict_reason = (
                f"brier CI [{lo:.4f}, {hi:.4f}] strictly above "
                f"baseline {baseline_brier_observed:.4f}"
            )
        else:
            verdict = "no_skill_detected"
            verdict_reason = (
                f"brier CI [{lo:.4f}, {hi:.4f}] straddles "
                f"baseline {baseline_brier_observed:.4f}"
            )

    # 6. Low power flag (diagnostic, pas gate)
    low_power_flag = n_clusters_brier < 5

    return {
        "layer": "thesis_alpha",
        "not_compatible_with": ["brier_signal", "pnl_eur"],
        "asof": datetime.now(UTC).isoformat(),
        "n_brut_accuracy": n_brut_accuracy,
        "n_brut_brier": n_brut_brier,
        "n_clusters_accuracy": n_clusters_accuracy,
        "n_clusters_brier": n_clusters_brier,
        "hit_rate": hit_rate,
        "hit_rate_ci_95": hit_rate_ci_95,
        "brier_score": brier_score,
        "brier_ci_95": brier_ci_95,
        "baseline_brier_observed": baseline_brier_observed,
        "baseline_brier_fixed_ref": 0.25,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "low_power_flag": low_power_flag,
    }


if __name__ == "__main__":
    import json

    result = compute_alpha_track_record()
    print(json.dumps(result, indent=2, default=str))
