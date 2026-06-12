"""SPEC_THESIS_ALPHA_RESOLVER pièce 6 — E2E pose → resolver → aggregator.

Couvre le maillon critique avec **12 mois de latence** entre pose et résolution :
si quelque chose dérive entre pièces 3 / 4 / 5 (writer, resolver, aggregator),
le bug ne se réveille qu'au moment de la résolution. Cet E2E le tue maintenant.

Trois preds en une passe pour couvrir les DEUX états terminaux du resolver :
- Pred A (REAL_A) : prix valide in-grace, alpha>0, call bull → resolve 'correct'
  → apparaît dans accuracy + Brier pools
- Pred B (REAL_B) : prix valide in-grace, alpha<0, call bull → resolve 'incorrect'
  → apparaît dans accuracy + Brier pools
- Pred C (REAL_C) : prix non-dispo (stub retourne (None, None)), today > due+grace
  → mark_abandoned terminal → tous resolve cols NULL → exclu des deux pools

Le piège qui dérive en silence : un mark_abandoned dont la sémantique change
mais que l'aggregator filtre encore. Cet E2E vérifie qu'abandon ⟹ exclusion
en aval, pas juste qu'abandon est écrit correctement.

Architecture lock préservée par DI + cure packaging #128 (12/06/2026) :
le resolver est appelé avec un stub `fetcher`, le module shared.prices
n'est jamais tiré, et bot/jobs/__init__.py est vidé de ses ré-exports
eager (qui tiraient pandas/yfinance/google/data_sources au package-level).
L'E2E reste runnable sur venv minimal.
"""

from __future__ import annotations

from datetime import date

import pytest

from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
from scripts.aggregator_alpha_track_record import compute_alpha_track_record
from shared.thesis_predictions_writer import insert_thesis_pose


def test_e2e_pose_resolve_abandon_aggregate(migrated_db):
    """E2E complet du chantier alpha sur 3 preds + 2 états terminaux."""

    # ============================================================
    # ÉTAPE 1 : Pose 3 preds réels via writer (insert_thesis_pose)
    # ============================================================
    # Tous dus aujourd'hui 2026-06-10. Currencies distinctes pour avoir
    # n_clusters_brier=2 (REAL_A=USD, REAL_B=EUR ; REAL_C abandonné n'entre
    # pas dans le cluster brier).
    due_day = date(2026, 6, 10)

    id_a = insert_thesis_pose(
        ticker="REAL_A",
        asof=due_day,
        asof_price_native=100.0,
        native_currency="USD",
        pt_consensus_raw=110.0,
        pt_consensus_currency="USD",
        pt_native_asof=110.0,
        fx_at_asof=1.0,
        your_target_native=120.0,
        your_delta_native_pct=+9.09,  # call bull (target > consensus)
        thesis_summary="E2E pose A : call bull qui se réalisera (alpha > 0)",
        resolve_due_date=due_day,
        confidence=0.8,
    )
    assert id_a is not None

    id_b = insert_thesis_pose(
        ticker="REAL_B",
        asof=due_day,
        asof_price_native=50.0,
        native_currency="EUR",
        pt_consensus_raw=55.0,
        pt_consensus_currency="EUR",
        pt_native_asof=55.0,
        fx_at_asof=1.0,
        your_target_native=60.0,
        your_delta_native_pct=+9.09,  # call bull
        thesis_summary="E2E pose B : call bull qui se cassera (alpha < 0)",
        resolve_due_date=due_day,
        confidence=0.7,
    )
    assert id_b is not None

    id_c = insert_thesis_pose(
        ticker="REAL_C",
        asof=due_day,
        asof_price_native=200.0,
        native_currency="JPY",
        pt_consensus_raw=220.0,
        pt_consensus_currency="JPY",
        pt_native_asof=220.0,
        fx_at_asof=1.0,
        your_target_native=240.0,
        your_delta_native_pct=+9.09,
        thesis_summary="E2E pose C : ticker delisté, prix indispo post-grâce",
        resolve_due_date=due_day,
        confidence=0.6,
    )
    assert id_c is not None

    # ============================================================
    # ÉTAPE 2 : Stub fetcher (DI > monkeypatch global, lock storage-only)
    # ============================================================
    # REAL_A : prix observé 115 (5% au-dessus du consensus 110 → alpha~4.5%, bull correct)
    # REAL_B : prix observé 48 (4% en-dessous du consensus 55 → alpha~-12.7%, bull incorrect)
    # REAL_C : (None, None) → resolver traite comme manquant → abandon post-grâce
    actual_str = due_day.isoformat()

    def stub_fetcher(ticker: str, date_str: str) -> tuple[str | None, float | None]:
        if ticker == "REAL_A":
            return (actual_str, 115.0)
        if ticker == "REAL_B":
            return (actual_str, 48.0)
        if ticker == "REAL_C":
            return (None, None)
        raise AssertionError(f"unexpected ticker in stub: {ticker}")

    # ============================================================
    # ÉTAPE 3 : Run resolver avec today > due+grace (force abandon REAL_C)
    # ============================================================
    # today = due + 6j > due + grace_days(5) → REAL_C tombe en abandon terminal
    # REAL_A et REAL_B ont des prix in-grace → resolve normal
    today_post_grace = date(2026, 6, 16)
    counters = resolve_due_thesis_predictions(
        today=today_post_grace,
        grace_days=5,
        fetcher=stub_fetcher,
    )

    # Invariant L27 : attempted == Σ par construction
    assert counters["attempted"] == 3, counters
    total = (
        counters["resolved"] + counters["neutral"] + counters["abandoned"]
        + counters["deferred"] + counters["classify_none_bugs"]
        + counters["write_failed"]
    )
    assert total == counters["attempted"], (
        f"L27 invariant cassé : {total} != {counters['attempted']} | {counters}"
    )

    # Comportement attendu sur les 3 preds
    assert counters["resolved"] == 2, f"REAL_A correct + REAL_B incorrect attendus | {counters}"
    assert counters["abandoned"] == 1, f"REAL_C abandon post-grâce attendu | {counters}"
    assert counters["deferred"] == 0, f"today > grace → pas de defer | {counters}"
    assert counters["classify_none_bugs"] == 0, f"pas de bug logique attendu | {counters}"
    assert counters["write_failed"] == 0, f"pas de race condition attendue | {counters}"

    # ============================================================
    # ÉTAPE 4 : Aggregator voit 2 dans les pools, 1 abandonné exclu
    # ============================================================
    tr = compute_alpha_track_record(cluster_strategy="currency")

    # REAL_A (correct, USD) + REAL_B (incorrect, EUR) → 2 preds, 2 clusters
    # REAL_C (abandon, JPY) DOIT être exclu des deux pools
    assert tr["n_brut_accuracy"] == 2, (
        f"REAL_A+REAL_B attendus, REAL_C abandon exclu. Si on voit 3 ici, "
        f"l'abandon n'est plus exclu — sémantique drift entre pièces 3 et 5. | {tr}"
    )
    assert tr["n_brut_brier"] == 2, (
        f"REAL_A+REAL_B avec confidence → Brier pool. REAL_C exclu. | {tr}"
    )
    assert tr["n_clusters_brier"] == 2, f"USD + EUR distincts | {tr}"

    # Hit rate : 1 correct sur 2 = 0.5
    assert tr["hit_rate"] == pytest.approx(0.5, abs=0.01)

    # Verdict : n_clusters_brier=2 minimum atteint, mais matière trop fine
    # pour trancher → on ne fait pas d'assertion forte sur le verdict ici
    # (les 4 quadrants verdict sont testés ailleurs). On vérifie juste que
    # le verdict n'est PAS 'insufficient_n' — preuve que la chaîne entière
    # produit un verdict statistiquement émis.
    assert tr["verdict"] in {"skill_detected", "no_skill_detected", "anti_skill_detected"}, (
        f"verdict statistique attendu (CI vs baseline tranche), pas insufficient_n. "
        f"Actuel : {tr['verdict']} | {tr['verdict_reason']}"
    )


def test_resolver_module_is_storage_only():
    """Lock storage-only sur le resolver — import normal subprocess.

    Post-#128 (12/06/2026) : bot/jobs/__init__.py vidé (ré-exports eager
    supprimés), bot/main.py migré vers imports groupés par sous-module. Le
    package bot.jobs ne tire plus rien lourd. Donc un test « from bot.jobs.X
    import Y » dans un interpréteur frais peut désormais vérifier le contrat
    storage-only par import normal — pas besoin de bypass importlib.

    Symétrique du test T16 sur l'aggregator. Si quelqu'un ré-introduit un
    import lourd dans bot.jobs.__init__ (ou dans un sous-module imported
    par cascade), ce test mord.
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).parent.parent
    # Le test verifie une ARCHITECTURE (heavy modules pas pulled), pas la DB.
    # En CI, la DB peut etre vide / pas migree -> OperationalError sur SELECT.
    # On utilise un script multi-ligne pour wrapper l'appel dans un try/except
    # et faire l'archi-check apres dans tous les cas.
    script = f"""
import sys, datetime
sys.path.insert(0, {str(root)!r})
from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
stub = lambda t, d: (None, None)
try:
    resolve_due_thesis_predictions(today=datetime.date(2026,6,16), fetcher=stub)
except Exception:
    pass  # DB-related errors OK, archi check vise sys.modules
heavy = ('shared.prices', 'data_sources', 'google', 'yfinance', 'telegram', 'pandas')
bad = [m for m in sys.modules if any(m == h or m.startswith(h + '.') for h in heavy)]
assert not bad, ('heavy modules pulled transitively: ' + repr(bad))
"""
    r = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, (
        f"Architecture lock violé — le resolver invoqué avec stub fetcher tire "
        f"shared.prices / chaîne lourde. Vérifier que bot/jobs/__init__.py reste "
        f"vide de ré-exports eager. stderr:\n{r.stderr}\nstdout:\n{r.stdout}"
    )
