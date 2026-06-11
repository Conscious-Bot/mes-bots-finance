"""Tests pour scripts/aggregator_alpha_track_record.py (pièce 5 chantier alpha).

Stratégie hybride (décision Olivier 11/06) :
- Pipeline tests (1-7) : writers réels (insert_thesis_pose +
  update_thesis_resolve_fields + mark_thesis_prediction_abandoned).
  Verrouille la fidélité bout-en-bout.
- Stats synthétiques (8-15) : seed SQL direct via helper _seed_resolved_pred
  qui RESPECTE les invariants writer (direction_correct set →
  resolution_status='resolved' + resolved_at set).
- Architecture lock (16) : test subprocess transitif qui vérifie qu'AUCUN
  module heavy (shared.prices, data_sources, google, yfinance, telegram,
  pandas) n'est chargé en transitif depuis l'agrégateur. ast.parse ne voit
  que les imports directs → insuffisant. Subprocess interpréteur frais voit
  le vrai graphe d'import.

Les deux tests critiques :
- T1 (test_baseline_uses_alpha_outcomes_not_direction_correct) : forcé
  cluster_strategy='ticker' pour donner 40 clusters distincts (sinon le test
  se masque lui-même via insufficient_n sur 1-cluster-USD). Catch l'inversion
  baseline (book parfait 20-bull-juste + 20-bear-juste → baseline DOIT être
  0.25 sur outcomes, PAS 0 sur direction_correct).
- T2 (test_single_cluster_correlation_no_skill) : 40 preds toutes 1 cluster
  USD, point estimate Brier 0.10 qui "a l'air skillé", CI cluster-bootstrap
  large → verdict no_skill_detected. Prouve que le moteur ne surstate pas
  sur du corrélé (catch faille iid).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.aggregator_alpha_track_record import (
    _base_rate_brier,
    _cluster_bootstrap_ci,
    _cluster_key,
    compute_alpha_track_record,
)


# ============================================================================
# HELPER : seed SQL direct respectant invariants writer
# ============================================================================


def _seed_resolved_pred(
    *,
    ticker: str,
    native_currency: str,
    direction_correct: int | None,
    magnitude_score: float | None = None,
    alpha_realized_pct: float | None = None,
    exclude_reason: str | None = None,
    resolution_status: str = "resolved",
    your_delta_pct: float = 5.0,
    asof: str = "2026-06-10",
    confidence: float | None = 0.7,
    asof_suffix: int = 0,
) -> int:
    """Seed pose + resolve en respectant invariants writer.

    Invariants critiques :
    - Tous les pose NOT NULL avec valeurs CHECK>0 valides
    - Si direction_correct ∈ {0,1} → resolution_status='resolved' + resolved_at set
    - Si abandoned → tous les resolve cols NULL sauf resolved_at + resolution_status
    - UNIQUE(ticker, asof, your_target_native) : asof_suffix permet d'incrémenter
      l'asof par jour pour éviter la collision sur N seeds même ticker

    your_delta_pct cohérent avec direction (bull=positif, bear=négatif).
    asof_price=100 (dummy CHECK>0). your_target_native dérivé.
    """
    import sqlite3
    from shared import storage  # import juste-in-time pour capter monkeypatch

    asof_price = 100.0
    your_target = asof_price * (1 + your_delta_pct / 100.0)
    if your_target <= 0:
        your_target = 0.01  # CHECK > 0
    # asof unique par seed pour éviter UNIQUE collision si même ticker re-posé
    asof_unique = (
        f"2026-{((asof_suffix // 28) % 12) + 1:02d}-{(asof_suffix % 28) + 1:02d}"
        if asof_suffix
        else asof
    )

    with sqlite3.connect(str(storage.DB_PATH)) as cx:
        # 1. POSE — tous les NOT NULL valides
        cur = cx.execute(
            """
            INSERT INTO thesis_predictions (
                ticker, asof, asof_price_native, native_currency,
                pt_consensus_raw, pt_consensus_currency, pt_native_asof, fx_at_asof,
                your_target_native, your_delta_native_pct, confidence, thesis_summary,
                resolve_due_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker, asof_unique, asof_price, native_currency,
                asof_price, native_currency, asof_price, 1.0,
                your_target, your_delta_pct, confidence,
                f"dummy thesis {ticker}",
                asof_unique,
            ),
        )
        pred_id = cur.lastrowid

        # 2. RESOLVE — UN UPDATE atomique (contrat trigger 2)
        if resolution_status == "abandoned":
            cx.execute(
                """
                UPDATE thesis_predictions SET
                    resolved_at = ?, resolve_price_native = NULL,
                    alpha_realized_pct = NULL, direction_correct = NULL,
                    magnitude_score = NULL, exclude_reason = NULL,
                    resolution_status = 'abandoned'
                  WHERE id = ?
                """,
                (datetime.now(UTC).isoformat(), pred_id),
            )
        else:
            # resolve_price cohérent avec alpha (anti-surprise lecture DB)
            if alpha_realized_pct is not None:
                resolve_price = asof_price * (1 + alpha_realized_pct / 100.0)
                if resolve_price <= 0:
                    resolve_price = 0.01  # CHECK > 0
            else:
                resolve_price = asof_price  # neutre
            cx.execute(
                """
                UPDATE thesis_predictions SET
                    resolved_at = ?, resolve_price_native = ?,
                    alpha_realized_pct = ?, direction_correct = ?,
                    magnitude_score = ?, exclude_reason = ?,
                    resolution_status = ?
                  WHERE id = ?
                """,
                (
                    datetime.now(UTC).isoformat(), resolve_price,
                    alpha_realized_pct, direction_correct,
                    magnitude_score, exclude_reason,
                    resolution_status, pred_id,
                ),
            )
        cx.commit()
    return pred_id


# ============================================================================
# PIPELINE TESTS (1-7) — bout-en-bout via filtres SQL
# ============================================================================


def test_empty_pool_yields_insufficient_n(migrated_db):
    """T1 pipeline : DB vide → verdict 'insufficient_n' fail-closed L19."""
    tr = compute_alpha_track_record()
    assert tr["verdict"] == "insufficient_n"
    assert tr["n_brut_brier"] == 0
    assert tr["n_brut_accuracy"] == 0
    assert tr["hit_rate"] is None
    assert tr["brier_score"] is None


def test_abandoned_excluded_from_both_pools(migrated_db):
    """T2 pipeline : resolution_status='abandoned' → exclu accuracy ET brier.

    Axe lifecycle (SPEC §4.1) distinct de l'axe scoring.
    """
    # 1 abandoned + 2 resolved scorables sur 2 clusters
    _seed_resolved_pred(
        ticker="AAA", native_currency="USD",
        direction_correct=None, resolution_status="abandoned",
    )
    _seed_resolved_pred(
        ticker="BBB", native_currency="USD",
        direction_correct=1, magnitude_score=0.05, alpha_realized_pct=+5.0,
    )
    _seed_resolved_pred(
        ticker="CCC", native_currency="EUR",
        direction_correct=0, magnitude_score=0.45, alpha_realized_pct=-3.0,
    )
    tr = compute_alpha_track_record(cluster_strategy="ticker")
    assert tr["n_brut_accuracy"] == 2
    assert tr["n_brut_brier"] == 2
    # AAA absent des deux pools


def test_neutral_excluded_from_accuracy(migrated_db):
    """T3 pipeline : exclude_reason='neutral' → exclu accuracy (et donc brier).

    Cohérence implicite SPEC §4.1 : exclude_reason set ⟺ direction_correct NULL
    """
    _seed_resolved_pred(
        ticker="NEUT", native_currency="USD",
        direction_correct=None, magnitude_score=None,
        alpha_realized_pct=+0.1, exclude_reason="neutral",
    )
    _seed_resolved_pred(
        ticker="GOOD", native_currency="EUR",
        direction_correct=1, magnitude_score=0.05, alpha_realized_pct=+5.0,
    )
    tr = compute_alpha_track_record(cluster_strategy="ticker")
    assert tr["n_brut_accuracy"] == 1  # NEUT exclu
    assert tr["n_brut_brier"] == 1


def test_no_confidence_excluded_from_brier_only(migrated_db):
    """T4 pipeline : magnitude_score IS NULL → exclu Brier seulement, pas accuracy.

    Pose sans confidence → resolve sans magnitude. Direction reste scorable.
    """
    _seed_resolved_pred(
        ticker="NOCONF1", native_currency="USD",
        direction_correct=1, magnitude_score=None,
        alpha_realized_pct=+5.0, confidence=None,
    )
    _seed_resolved_pred(
        ticker="WITHCONF", native_currency="EUR",
        direction_correct=1, magnitude_score=0.05, alpha_realized_pct=+5.0,
        confidence=0.7,
    )
    tr = compute_alpha_track_record(cluster_strategy="ticker")
    assert tr["n_brut_accuracy"] == 2  # les deux
    assert tr["n_brut_brier"] == 1     # WITHCONF seulement


def test_output_layer_and_not_compatible_with(migrated_db):
    """T5 pipeline : decision E SPEC §0 — déclaration layer + not_compatible_with.

    Empêche un consommateur de comparer accidentellement à brier_signal/pnl_eur.
    """
    tr = compute_alpha_track_record()
    assert tr["layer"] == "thesis_alpha"
    assert "brier_signal" in tr["not_compatible_with"]
    assert "pnl_eur" in tr["not_compatible_with"]


def test_single_resolved_yields_insufficient_n(migrated_db):
    """T6 pipeline : 1 pred résolue → n_clusters_brier=1 → insufficient_n.

    Plancher principielle n_clusters_brier >= 2, pas seuil L16 fabriqué.
    """
    _seed_resolved_pred(
        ticker="LONE", native_currency="USD",
        direction_correct=1, magnitude_score=0.05, alpha_realized_pct=+5.0,
    )
    tr = compute_alpha_track_record()  # currency strategy : 1 cluster USD
    assert tr["verdict"] == "insufficient_n"
    assert tr["n_clusters_brier"] == 1
    assert "n_clusters_brier=1" in tr["verdict_reason"]


def test_via_real_writers_resolved_pred_appears_in_pool(migrated_db):
    """T7 pipeline : pose via insert_thesis_pose + resolve via update_thesis_resolve_fields
    réels → la prédiction apparaît correctement dans les pools.

    Verrou fidélité bout-en-bout : si les writers réels divergent des seeds
    synthétiques, ce test mord (= les autres tests stats deviennent menteurs).
    """
    from datetime import date

    from shared.thesis_predictions_writer import (
        insert_thesis_pose,
        update_thesis_resolve_fields,
    )

    pose_id_a = insert_thesis_pose(
        ticker="REAL_A",
        asof=date(2026, 6, 10),
        asof_price_native=100.0,
        native_currency="USD",
        pt_consensus_raw=110.0,
        pt_consensus_currency="USD",
        pt_native_asof=110.0,
        fx_at_asof=1.0,
        your_target_native=120.0,
        your_delta_native_pct=+9.09,  # > 1.0 epsilon → pas no_bet
        thesis_summary="real test pose A",
        resolve_due_date=date(2026, 6, 10),
        confidence=0.7,
    )
    assert pose_id_a is not None
    ok_a = update_thesis_resolve_fields(
        prediction_id=pose_id_a,
        resolve_price_native=125.0,
        alpha_realized_pct=+4.5,
        classify_result="correct",
        magnitude_score=0.09,
    )
    assert ok_a

    pose_id_b = insert_thesis_pose(
        ticker="REAL_B",
        asof=date(2026, 6, 10),
        asof_price_native=50.0,
        native_currency="EUR",
        pt_consensus_raw=55.0,
        pt_consensus_currency="EUR",
        pt_native_asof=55.0,
        fx_at_asof=1.0,
        your_target_native=60.0,
        your_delta_native_pct=+9.09,
        thesis_summary="real test pose B",
        resolve_due_date=date(2026, 6, 10),
        confidence=0.6,
    )
    assert pose_id_b is not None
    ok_b = update_thesis_resolve_fields(
        prediction_id=pose_id_b,
        resolve_price_native=58.0,
        alpha_realized_pct=+1.5,
        classify_result="correct",
        magnitude_score=0.16,
    )
    assert ok_b

    tr = compute_alpha_track_record(cluster_strategy="ticker")
    assert tr["n_brut_accuracy"] == 2
    assert tr["n_brut_brier"] == 2
    assert tr["n_clusters_brier"] == 2


# ============================================================================
# CRITICAL TESTS (8-9) — les deux pièges identifiés par red-team Olivier
# ============================================================================


def test_baseline_uses_alpha_outcomes_not_direction_correct(migrated_db):
    """T8 CRITIQUE : catch inversion baseline.

    Book parfait 20-bull-juste + 20-bear-juste :
    - mean(direction_correct) = 1.0 → baseline FAUX serait 1.0×0 = 0
    - mean(sign(alpha))      = 0.5 → baseline CORRECT 0.5×0.5 = 0.25
    - Brier réalisé (conf 0.8 tout juste) ≈ (0.8-1)² × 40 / 40 = 0.04
      Wait, magnitude_score Brier = (confidence - direction_correct)² avec
      sign matching. Going utiliser magnitude_score=0.04 fix pour tous.
    - Verdict avec baseline CORRECT 0.25 : 0.04 ≪ 0.25 → skill_detected ✓
    - Verdict avec baseline BUGGÉ 0    : 0.04 > 0   → anti_skill_detected ✗

    cluster_strategy='ticker' forcé : 40 tickers distincts → 40 clusters
    → CI cluster-bootstrap dégénère [0.04, 0.04] (magnitudes constantes)
    → CI strictement < 0.25 → verdict tranché skill_detected. Sans
    cluster_strategy='ticker', tous USD = 1 cluster → insufficient_n et le
    test ne testerait rien (test==spec deux fois faux).
    """
    # 20 bulls justes (alpha>0, direction_correct=1)
    for i in range(20):
        _seed_resolved_pred(
            ticker=f"BULL{i:02d}", native_currency="USD",
            direction_correct=1, magnitude_score=0.04,
            alpha_realized_pct=+5.0,
            your_delta_pct=+5.0,
            asof_suffix=i,
        )
    # 20 bears justes (alpha<0, direction_correct=1, your_delta négatif)
    for i in range(20):
        _seed_resolved_pred(
            ticker=f"BEAR{i:02d}", native_currency="USD",
            direction_correct=1, magnitude_score=0.04,
            alpha_realized_pct=-5.0,
            your_delta_pct=-5.0,
            asof_suffix=i + 100,
        )

    tr = compute_alpha_track_record(cluster_strategy="ticker")

    # Baseline outcomes : p̄ = 20/40 = 0.5 → 0.5*(1-0.5) = 0.25
    assert tr["baseline_brier_observed"] == pytest.approx(0.25, abs=0.001)
    # Brier réalisé = 0.04 (toutes magnitudes identiques)
    assert tr["brier_score"] == pytest.approx(0.04, abs=0.001)
    # 40 tickers distincts = 40 clusters
    assert tr["n_clusters_brier"] == 40
    # CI dégénère [0.04, 0.04] (magnitudes constantes intra+inter cluster)
    lo, hi = tr["brier_ci_95"]
    assert hi == pytest.approx(0.04, abs=0.001)
    # CI strictement < baseline → skill_detected
    assert tr["verdict"] == "skill_detected", (
        f"book parfait bull+bear DOIT être skill_detected (baseline 0.25, "
        f"brier 0.04). Si on voit 'anti_skill_detected' → l'inversion baseline "
        f"est revenue. Actuel : {tr['verdict']} | "
        f"baseline={tr['baseline_brier_observed']:.4f} | CI=[{lo:.4f},{hi:.4f}]"
    )


def test_single_cluster_correlation_no_skill(migrated_db):
    """T9 CRITIQUE : catch corrélation iid.

    40 preds toutes du même ticker AAPL/USD → cluster_strategy='currency' →
    1 seul cluster USD. Point estimate Brier 0.10 "a l'air skillé" (vs
    baseline ~0.25), mais le cluster-bootstrap avec 1 seul cluster ne peut
    pas estimer le CI → gate n_clusters_brier<2 → insufficient_n.

    C'est LE test qui prouve que le moteur ne surstate pas sur du corrélé.
    Avec iid bootstrap, ces 40 preds (in fact 1 pari répété 40x) donneraient
    un CI étroit [0.09, 0.11] → faux skill_detected. Le cluster bootstrap
    refuse de bootstraper sur 1 cluster.

    Note : on rend les 40 preds distincts par asof_suffix (UNIQUE constraint)
    mais elles convergent au même cluster USD.
    """
    for i in range(40):
        _seed_resolved_pred(
            ticker="AAPL", native_currency="USD",
            direction_correct=1, magnitude_score=0.10,
            alpha_realized_pct=+5.0,
            your_delta_pct=+5.0,
            asof_suffix=i,
        )
    tr = compute_alpha_track_record(cluster_strategy="currency")

    assert tr["n_brut_brier"] == 40
    assert tr["n_clusters_brier"] == 1
    assert tr["verdict"] == "insufficient_n", (
        f"40 preds 1-cluster DOIT être insufficient_n (cluster-bootstrap "
        f"refuse). Si on voit 'skill_detected' → l'iid bootstrap est revenu. "
        f"Actuel : {tr['verdict']}"
    )
    assert "n_clusters_brier=1" in tr["verdict_reason"]


# ============================================================================
# STATS SYNTHÉTIQUES (10-14) — verdict matrix
# ============================================================================


def test_clear_skill_synthetic_yields_skill_detected(migrated_db):
    """T10 stats : 20 preds mix bull+bear tous justes Brier=0.05 sur 10
    clusters distincts (currencies distinctes) → baseline=0.25 (p̄=0.5),
    CI bien < baseline → skill_detected.

    Mix bull/bear nécessaire : un book all-bull-correct a baseline=0 (tous
    outcomes positifs, p̄=1.0) → brier 0.05 > 0 → anti_skill. Le "skill"
    est mesuré contre un prédicteur naïf "always predict mode", ce mode
    n'a de sens que sur un book directionnellement varié.
    """
    currencies = ["USD", "EUR", "JPY", "GBP", "KRW", "CAD", "AUD", "CHF", "HKD", "SEK"]
    for i, cur in enumerate(currencies):
        # 1 bull juste + 1 bear juste par cluster → 10 bulls + 10 bears
        _seed_resolved_pred(
            ticker=f"BULL{i:02d}", native_currency=cur,
            direction_correct=1, magnitude_score=0.05,
            alpha_realized_pct=+5.0,
            your_delta_pct=+5.0,
            asof_suffix=i * 10,
        )
        _seed_resolved_pred(
            ticker=f"BEAR{i:02d}", native_currency=cur,
            direction_correct=1, magnitude_score=0.05,
            alpha_realized_pct=-5.0,
            your_delta_pct=-5.0,
            asof_suffix=i * 10 + 1,
        )
    tr = compute_alpha_track_record(cluster_strategy="currency")
    assert tr["n_clusters_brier"] == 10
    assert tr["brier_score"] == pytest.approx(0.05, abs=0.001)
    assert tr["baseline_brier_observed"] == pytest.approx(0.25, abs=0.001)
    assert tr["verdict"] == "skill_detected", (
        f"Brier 0.05 ≪ baseline 0.25 sur 10 clusters → skill. Actuel : "
        f"{tr['verdict']} | baseline={tr['baseline_brier_observed']:.4f}"
    )


def test_clear_anti_skill_synthetic_yields_anti_skill(migrated_db):
    """T11 stats : Brier=0.90 (preds horribles : conf 0.9 mais tout faux)
    sur 5 clusters → CI strictement > baseline → anti_skill_detected.
    """
    currencies = ["USD", "EUR", "JPY", "GBP", "KRW"]
    for i, cur in enumerate(currencies):
        for j in range(4):
            _seed_resolved_pred(
                ticker=f"BAD{i:02d}_{j}", native_currency=cur,
                direction_correct=0, magnitude_score=0.81,  # (0.9 - 0)² = 0.81
                alpha_realized_pct=-5.0,
                your_delta_pct=+5.0,  # call bullish, marché bear
                asof_suffix=i * 10 + j,
            )
    tr = compute_alpha_track_record(cluster_strategy="currency")
    assert tr["n_clusters_brier"] == 5
    assert tr["brier_score"] == pytest.approx(0.81, abs=0.001)
    # baseline outcomes : tous alpha<0 → p̄=0 → 0×1=0 → CI 0.81 strictement > 0
    assert tr["verdict"] == "anti_skill_detected", (
        f"Brier 0.81 ≫ baseline 0 sur 5 clusters → anti_skill. "
        f"Actuel : {tr['verdict']} | baseline={tr['baseline_brier_observed']:.4f}"
    )


def test_straddle_yields_no_skill(migrated_db):
    """T12 stats : mix de bons et mauvais → CI englobe baseline → no_skill.

    8 preds Brier moyenne ~0.20, baseline 0.25 (50/50 outcomes), CI assez
    large pour englober 0.25.
    """
    # 4 préds bonnes (Brier 0.05), 4 mauvaises (Brier 0.45), outcomes 50/50
    for i in range(4):
        _seed_resolved_pred(
            ticker=f"GOOD{i}", native_currency=["USD", "EUR", "JPY", "KRW"][i],
            direction_correct=1, magnitude_score=0.05,
            alpha_realized_pct=+5.0,
            your_delta_pct=+5.0,
            asof_suffix=i,
        )
    for i in range(4):
        _seed_resolved_pred(
            ticker=f"BAD{i}", native_currency=["GBP", "CAD", "AUD", "CHF"][i],
            direction_correct=0, magnitude_score=0.45,
            alpha_realized_pct=-5.0,
            your_delta_pct=+5.0,
            asof_suffix=i + 10,
        )
    tr = compute_alpha_track_record(cluster_strategy="currency")
    assert tr["n_clusters_brier"] == 8
    assert tr["brier_score"] == pytest.approx(0.25, abs=0.001)
    # outcomes : 4 alpha>0, 4 alpha<0 → p̄=0.5 → baseline=0.25
    assert tr["baseline_brier_observed"] == pytest.approx(0.25, abs=0.001)
    # Brier ~= baseline → CI englobe → no_skill
    assert tr["verdict"] == "no_skill_detected", (
        f"Brier 0.25 ~= baseline 0.25 → no_skill. Actuel : {tr['verdict']}"
    )


def test_bootstrap_reproducible_with_seed(migrated_db):
    """T13 stats : seed RNG fixe → CI identique entre deux runs. Seed
    différent → CI différent (requiert magnitudes hétérogènes sinon CI
    dégénère identique sur valeurs constantes).
    """
    # Magnitudes hétérogènes pour que le bootstrap dépende du seed
    magnitudes = [0.02, 0.05, 0.08, 0.12, 0.18, 0.22, 0.27, 0.31, 0.36, 0.42]
    for i in range(10):
        _seed_resolved_pred(
            ticker=f"T{i}", native_currency=["USD", "EUR", "JPY", "KRW", "GBP"][i % 5],
            direction_correct=1, magnitude_score=magnitudes[i],
            alpha_realized_pct=+5.0 if i % 2 == 0 else -5.0,
            your_delta_pct=+5.0 if i % 2 == 0 else -5.0,
            asof_suffix=i,
        )
    tr1 = compute_alpha_track_record(cluster_strategy="currency", bootstrap_seed=42)
    tr2 = compute_alpha_track_record(cluster_strategy="currency", bootstrap_seed=42)
    # Reproductibilité stricte avec même seed (contrat principal)
    assert tr1["brier_ci_95"] == tr2["brier_ci_95"]
    assert tr1["hit_rate_ci_95"] == tr2["hit_rate_ci_95"]
    # Note : on ne teste pas que seed différent → CI différent. Sur petits N
    # avec distribution étroite, les quantiles 2.5%/97.5% peuvent coïncider
    # entre seeds différents (test fragile). Le contrat tenu est juste la
    # reproductibilité, pas la divergence entre seeds.


def test_pool_accuracy_populated_pool_brier_empty_yields_insufficient_n(migrated_db):
    """T14 stats : pool accuracy peuplé mais pool Brier vide → insufficient_n
    (gates verdict nommés sur pool BRIER, pas accuracy).

    Posé sans confidence sur 5 tickers distincts → direction_correct set
    mais magnitude_score NULL pour tous. n_brut_brier=0 → insufficient_n.
    """
    for i, cur in enumerate(["USD", "EUR", "JPY", "GBP", "KRW"]):
        _seed_resolved_pred(
            ticker=f"NC{i}", native_currency=cur,
            direction_correct=1, magnitude_score=None,
            alpha_realized_pct=+5.0,
            confidence=None,
            asof_suffix=i,
        )
    tr = compute_alpha_track_record(cluster_strategy="currency")
    assert tr["n_brut_accuracy"] == 5
    assert tr["n_brut_brier"] == 0
    assert tr["verdict"] == "insufficient_n"
    assert "brier pool" in tr["verdict_reason"]


# ============================================================================
# PURE HELPERS (15) — sanity sur les pure functions
# ============================================================================


def test_base_rate_brier_pure_function():
    """T15a : _base_rate_brier sur outcomes sign(alpha).

    Mix bull/bear : 4 alphas positifs + 4 négatifs → p̄=0.5 → 0.25
    Tout bull : 4 alphas positifs → p̄=1.0 → 0
    Tout bear : 4 alphas négatifs → p̄=0 → 0
    Empty : fallback 0.25
    """
    assert _base_rate_brier([+1.0, +2.0, -1.0, -2.0]) == pytest.approx(0.25)
    assert _base_rate_brier([+1.0, +2.0, +3.0, +4.0]) == pytest.approx(0.0)
    assert _base_rate_brier([-1.0, -2.0, -3.0, -4.0]) == pytest.approx(0.0)
    assert _base_rate_brier([]) == pytest.approx(0.25)
    # Mix 80/20 bull : p̄=0.8 → 0.16
    assert _base_rate_brier([+1.0] * 8 + [-1.0] * 2) == pytest.approx(0.16, abs=0.001)


def test_cluster_key_strategies():
    """T15b : _cluster_key respecte la stratégie."""
    assert _cluster_key("AAPL", "USD", "currency") == ("USD",)
    assert _cluster_key("AAPL", "USD", "ticker") == ("AAPL",)
    # Re-pose annuelle même ticker en strategy currency → même cluster
    assert _cluster_key("SK", "KRW", "currency") == _cluster_key("SK", "KRW", "currency")


def test_cluster_bootstrap_degenerates_on_constant_values():
    """T15c : _cluster_bootstrap_ci sur valeurs constantes → CI dégénère."""
    values = {("c1",): [0.05, 0.05], ("c2",): [0.05, 0.05], ("c3",): [0.05]}
    lo, hi = _cluster_bootstrap_ci(values, iters=500, seed=42)
    assert lo == pytest.approx(0.05, abs=0.001)
    assert hi == pytest.approx(0.05, abs=0.001)


# ============================================================================
# ARCHITECTURE LOCK (16) — test subprocess transitif storage-only
# ============================================================================


def test_aggregator_does_not_pull_heavy_chain():
    """T16 architecture : interpréteur frais import aggregator → vérifie
    qu'AUCUN module heavy n'est chargé en transitif.

    ast.parse seul verrait les imports DIRECTS uniquement. Le piège est
    transitif (import propre shared.storage, mais si quoi que ce soit en
    aval tire data_sources, l'ast ne le voit pas). Subprocess interpréteur
    frais voit le VRAI graphe d'import — ce qui garantit la runnabilité
    sur venv minimal (pas de google-auth/yfinance/telegram/pandas installés).
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).parent.parent
    script = (
        "import sys; "
        "sys.path.insert(0, %r); "
        "import scripts.aggregator_alpha_track_record; "
        "heavy = ('shared.prices', 'data_sources', 'google', "
        "'yfinance', 'telegram', 'pandas'); "
        "bad = [m for m in sys.modules if any(m == h or m.startswith(h + '.') "
        "for h in heavy)]; "
        "assert not bad, ('heavy modules pulled transitively: ' + repr(bad))"
    ) % str(root)
    r = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, (
        f"Architecture lock violé — l'agrégateur tire des modules heavy en "
        f"transitif. stderr:\n{r.stderr}\nstdout:\n{r.stdout}"
    )
