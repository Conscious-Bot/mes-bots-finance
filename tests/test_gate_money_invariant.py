"""Test-violation pour la gate ratchet SPEC_MONEY_INVARIANT.

Wire la gate `scripts/check_money_invariant.sh` dans pytest pour qu'elle
soit exécutée automatiquement à chaque test run. Sans ce câblage, la gate
est un script qu'on doit penser à lancer = vigilance déguisée (mode
d'échec exact de L1 que L27 corrige).

3 tests :
  1. Gate verte sur l'état courant — sanity (compteur == baseline)
  2. Test-violation gate-1 : injection × fx ad-hoc → gate doit fail
  3. Test-violation gate-2 : injection arithmétique baseline → gate doit fail

Le test-violation crée un fichier temporaire avec la violation, run la
gate, capture le code retour, supprime le fichier. Si la gate ne retourne
PAS un code non-zero, la gate est inefficace = vigilance déguisée détectée.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPT = REPO_ROOT / "scripts" / "check_money_invariant.sh"
VIOLATION_PATH = REPO_ROOT / "intelligence" / "_gate_violation_test.py"


def _run_gate() -> tuple[int, str]:
    """Lance la gate, retourne (exit_code, output)."""
    result = subprocess.run(
        [str(GATE_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout + result.stderr


def test_gate_baseline_clean():
    """Sanity : l'état courant respecte la baseline (compteur == fichier)."""
    code, out = _run_gate()
    assert code == 0, f"Gate fail sur état courant — counter dérivé du baseline.\n{out}"
    assert "OK money_invariant" in out or "RATCHET" in out


def test_gate_detects_fx_violation_injection():
    """Inject une violation × fx, gate doit DÉTECTER + FAIL (exit non-zero).

    Si ce test passe, c'est que la gate est inefficace = vigilance déguisée.
    Verdict B (Olivier) : "gate qui est un script qu'on doit penser à lancer
    = vigilance déguisée — exactement le mode d'échec de L1 que L27 corrige".
    """
    VIOLATION_PATH.write_text(
        "# Violation test injectée pour gate test — supprimée après assert\n"
        "from shared.book import BookLine\n"
        "def fake(line: BookLine) -> float:\n"
        "    # Violation : × line.fx_rate_to_eur hors shared/money.py\n"
        "    return line.qty * line.last_price_native * line.fx_rate_to_eur\n"
    )
    try:
        code, out = _run_gate()
        assert code != 0, (
            f"GATE INEFFECTIVE : violation × fx injectée mais gate retourne 0.\n"
            f"Output :\n{out}\n"
            "C'est exactement le 'théâtre de gate' qu'Olivier interdit."
        )
        assert "VIOLATION" in out or "increased" in out
    finally:
        VIOLATION_PATH.unlink(missing_ok=True)


def test_gate_detects_baseline_arithmetic_violation():
    """Inject une violation arithmétique baseline (entry_price × const), fail attendu."""
    VIOLATION_PATH.write_text(
        "# Violation test : arithmétique baseline ad-hoc\n"
        "def fake_pnl(p: dict) -> float:\n"
        "    # Violation : (p['entry_price'] - x) * 100 / p['entry_price']\n"
        "    return (1.0 - p['entry_price']) * 100 / p['entry_price']\n"
    )
    try:
        code, out = _run_gate()
        assert code != 0, (
            f"GATE INEFFECTIVE : violation entry_price ad-hoc injectée mais "
            f"gate retourne 0.\nOutput :\n{out}"
        )
    finally:
        VIOLATION_PATH.unlink(missing_ok=True)


def test_stop_value_is_mutable_not_writeonce():
    """Substrat CANONICAL_MAP §2 : stop/target = décisions VIVANTES (trailing
    stop, re-target), pas faits immuables. Si quelqu'un re-pose un write-once
    sur stop/target, ce test casse — garde anti-régression doctrine.

    Sans ce test : un futur commit pourrait re-introduire write-once sur stop
    « par symétrie avec entry », ce qui ramène la friction §3 sur chaque
    ajustement de gestion. Le test verrouille la doctrine mutable.
    """
    import sqlite3
    from shared import storage

    with storage.db() as cx:
        cx.row_factory = None
        row = cx.execute(
            "SELECT id, stop_value FROM theses "
            "WHERE status='active' AND stop_value IS NOT NULL LIMIT 1"
        ).fetchone()
    if row is None:
        pytest.skip("No active thesis with stop_value to test mutability")
    thesis_id, current_stop = row
    new_stop = current_stop * 1.05  # +5% trailing stop simulation

    # UPDATE doit PASSER (pas de RAISE) -- stop est mutable
    try:
        with storage.db() as cx:
            cx.execute(
                "UPDATE theses SET stop_value = ? WHERE id = ?",
                (new_stop, thesis_id),
            )
        # Restore valeur originale (pour ne pas polluer prod)
        with storage.db() as cx:
            cx.execute(
                "UPDATE theses SET stop_value = ? WHERE id = ?",
                (current_stop, thesis_id),
            )
    except sqlite3.IntegrityError as e:
        pytest.fail(
            f"stop_value n'est PAS mutable (UPDATE rejeté : {e}). "
            "Doctrine : stop = décision vivante (trailing stop, re-target), "
            "jamais write-once. Cf CANONICAL_MAP §2 état-mutable."
        )


def test_writeonce_trigger_rejects_entry_value_update():
    """Serrure D (Olivier) : write-once trigger sur entry_value doit RAISE
    quand un UPDATE post-INSERT tente de changer la valeur.

    Sans ce test, le trigger est un 'espoir, pas une serrure'.
    """
    import sqlite3
    from shared import storage

    with storage.db() as cx:
        cx.row_factory = None
        row = cx.execute(
            "SELECT id, entry_value FROM theses "
            "WHERE status='active' AND entry_value IS NOT NULL LIMIT 1"
        ).fetchone()
    if row is None:
        pytest.skip("No active thesis with entry_value to test trigger")
    thesis_id, current = row

    with pytest.raises(sqlite3.IntegrityError, match="write-once"):
        with storage.db() as cx:
            cx.execute(
                "UPDATE theses SET entry_value = ? WHERE id = ?",
                (current * 2, thesis_id),
            )


def test_pct_change_cross_currency_raises():
    """Serrure structurelle : pct_change(KRW, EUR) doit lever AssertionError.

    Verrouille le bug fondateur +176056% : on ne peut PLUS calculer un
    ratio entre prix natifs incompatibles silencieusement.
    """
    from shared.money import monetary, pct_change

    entry_eur = monetary(800.0, "EUR", "2026-05-16T00:00:00Z", "test")
    price_krw = monetary(1_900_000.0, "KRW", "2026-06-08T00:00:00Z", "test")

    with pytest.raises(AssertionError, match="cross-devise"):
        pct_change(entry_eur, price_krw)
