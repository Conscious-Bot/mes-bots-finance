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

Architecture lock préservée par DI : le resolver est appelé avec un stub
`fetcher`, le module shared.prices n'est jamais tiré, l'E2E reste runnable
sur venv minimal.
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


def test_resolver_module_isolated_is_storage_only():
    """Lock storage-only sur le MODULE resolver (pas le package bot.jobs).

    KNOWN-GAP : `bot.jobs.__init__` ré-exporte tous les jobs daily/intervals/
    periodic au package-level → `from bot.jobs import thesis_alpha_resolver`
    exécute __init__ qui tire pandas/yfinance/google/data_sources. C'est un
    bug de packaging (chantier découplage imports d'infra), pas du module
    resolver. Ce test vérifie que le MODULE lui-même reste storage-only :
    quand le packaging sera refactor lazy, le module passera direct.

    Méthode : importlib.util charge le fichier .py SANS exécuter le package
    parent — équivalent à ce qu'un `bot.jobs.__init__` lazy (PEP 562
    __getattr__) ferait. Si quoi que ce soit dans le module RESOLVER (pas
    le package) tire la chaîne lourde, le lock saute.

    Symétrique du test T16 pièce 5 sur l'aggregator (lui n'a pas de package
    parent lourd → import direct OK). Quand l'infra sera nettoyée, on
    pourra remplacer ce test par un import normal subprocess comme T16.
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).parent.parent
    resolver_path = root / "bot" / "jobs" / "thesis_alpha_resolver.py"
    script = (
        "import sys, importlib.util, datetime; "
        "sys.path.insert(0, %r); "
        "spec = importlib.util.spec_from_file_location('_resolver_iso', %r); "
        "m = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(m); "
        "stub = lambda t, d: (None, None); "
        "m.resolve_due_thesis_predictions("
        "today=datetime.date(2026,6,16), fetcher=stub); "
        "heavy = ('shared.prices', 'data_sources', 'google', "
        "'yfinance', 'telegram', 'pandas'); "
        "bad = [m for m in sys.modules if any(m == h or m.startswith(h + '.') "
        "for h in heavy)]; "
        "assert not bad, ('heavy modules pulled transitively: ' + repr(bad))"
    ) % (str(root), str(resolver_path))
    r = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, (
        f"Architecture lock violé sur le MODULE resolver (isolé du packaging) "
        f"— le code de la pièce 4 tire shared.prices / chaîne lourde même avec "
        f"fetcher stub injecté. stderr:\n{r.stderr}\nstdout:\n{r.stdout}"
    )
