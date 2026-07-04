"""Smoke tests for risk/kill_switch.py (kill-condition disjoncteur grappe AI-compute).

Cf doctrine vault "Kill-condition — disjoncteur de la grappe AI-compute" V3 (26/06).
Cf spec handoff §8.
"""

from __future__ import annotations

import pytest

from risk import kill_switch as ks


def test_module_imports():
    """Ensure all public exports are present."""
    assert hasattr(ks, "check_and_fire")
    assert hasattr(ks, "validate_override")
    assert hasattr(ks, "snapshot_cluster_value")
    assert hasattr(ks, "escalate_unresolved")
    assert hasattr(ks, "cmd_kill_exec")
    assert hasattr(ks, "cmd_kill_override")
    assert hasattr(ks, "cmd_kill_resolve")


def test_stage_thresholds(monkeypatch):
    """Stage detection : 0 normal / 1 vigilance / 2 derisque / 3 hard (si activé)."""
    monkeypatch.setattr(
        ks,
        "_cfg",
        lambda: {
            "drawdown_reduce_pct": 0.25,
            "drawdown_stop_pct": 0.35,
            "drawdown_hard_pct": None,
        },
    )
    assert ks.stage_for_drawdown(-0.10) == 0  # < reduce → normal
    assert ks.stage_for_drawdown(-0.25) == 1  # >= reduce → vigilance
    assert ks.stage_for_drawdown(-0.34) == 1  # < stop, > reduce → vigilance
    assert ks.stage_for_drawdown(-0.35) == 2  # >= stop → derisque
    assert ks.stage_for_drawdown(-0.60) == 2  # hard désactivé → caps à 2


def test_stage_thresholds_hard_enabled(monkeypatch):
    """Si drawdown_hard_pct activé : Stage 3 atteignable."""
    monkeypatch.setattr(
        ks,
        "_cfg",
        lambda: {
            "drawdown_reduce_pct": 0.25,
            "drawdown_stop_pct": 0.35,
            "drawdown_hard_pct": 0.50,
        },
    )
    assert ks.stage_for_drawdown(-0.50) == 3
    assert ks.stage_for_drawdown(-0.49) == 2


def test_override_rejects_no_date(monkeypatch):
    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 10})
    ok, d, _ = ks.validate_override("la thèse va se redresser bientôt promis")
    assert ok is False
    assert d is None


def test_override_rejects_past_date(monkeypatch):
    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 10})
    ok, _d, _ = ks.validate_override(
        "je tiens car capex intact, tort si <1.0 le 2020-01-01"
    )
    assert ok is False


def test_override_accepts_future_dated(monkeypatch):
    from datetime import timedelta

    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 10})
    # Date relative (jamais hardcodée — leçon 15/06) : toujours dans le futur.
    future = (ks._today() + timedelta(days=90)).isoformat()
    ok, d, _ = ks.validate_override(
        f"je tiens: capex hyperscaler intact; tort si book-to-bill ASML <1.0 d'ici {future}"
    )
    assert ok is True
    assert d == future


def test_override_rejects_too_short(monkeypatch):
    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 40})
    ok, _d, _ = ks.validate_override("tort si X 2026-12-01")
    assert ok is False


def test_override_invalid_date_format(monkeypatch):
    """Date type-extractable mais invalide (mois 13)."""
    monkeypatch.setattr(ks, "_cfg", lambda: {"override_min_chars": 10})
    ok, _d, _reason = ks.validate_override(
        "je tiens longuement; ma date est 2026-13-99 absurde"
    )
    assert ok is False


def test_cluster_membership_explicit(monkeypatch):
    """cluster_tickers explicite a priorité sur cluster_narrative."""
    monkeypatch.setattr(
        ks,
        "_cfg",
        lambda: {"cluster_tickers": ["asml.as", "TSM", "000660.KS"]},
    )
    members = ks._cluster_membership()
    assert "ASML.AS" in members  # uppercased
    assert "TSM" in members
    assert "000660.KS" in members
    assert len(members) == 3


def test_cluster_membership_neither_defined_raises(monkeypatch):
    """Ni cluster_tickers ni cluster_narrative → ConfigurationError."""
    monkeypatch.setattr(ks, "_cfg", dict)
    from shared import config

    with pytest.raises(config.ConfigurationError):
        ks._cluster_membership()


@pytest.mark.live_data  # lit _cluster_membership() = book live (data/bot.db absent en CI)
def test_cluster_membership_taxonomy_ai_capex_held(monkeypatch):
    """Phase 4 — source canonique = taxonomy mapping driver=ai_capex sur held.

    L'assertion held-scopée vs B (config.yaml) doit passer puisque l'alignement
    27/06 (MHI 7011.T déplacé de decorrelators vers compute_ai) a été commité.
    """
    monkeypatch.setattr(ks, "_cfg", lambda: {"cluster_source": "taxonomy_ai_capex_held"})
    members = ks._cluster_membership()
    # Tickers held ai_capex attendus (snapshot 27/06 post-alignement MHI)
    assert "TSM" in members
    assert "AVGO" in members
    assert "AMZN" in members  # hyperscaler driver=ai_capex
    assert "GOOGL" in members
    assert "GEV" in members
    assert "SU.PA" in members
    assert "7011.T" in members  # MHI bias-safe driver=ai_capex (cf MEMORY layer_vs_driver)
    # Tickers held mais NON ai_capex doivent être ABSENTS
    assert "CCJ" not in members
    assert "LNG" not in members
    assert "HO.PA" not in members
    assert "SAF.PA" not in members
    assert "SPCX" not in members
    assert "6324.T" not in members
    assert "MP" not in members
    # Tickers de l'univers étendu (B) non-held NE DOIVENT PAS être dans le set
    # (Phase 4 retourne strict held, pas l'univers)
    assert "NVDA" not in members  # not held
    assert "AMD" not in members   # not held


@pytest.mark.live_data  # assertion sur le book live held (data/bot.db absent en CI)
def test_assert_held_cluster_consistency_passes_after_alignment():
    """L'assertion doit passer sur l'état figé 27/06 — sinon Phase 4 cassée."""
    from shared import taxonomy

    taxonomy.assert_held_cluster_consistency()  # raise sinon


# ---------- honnêteté d'agrégat + staleness (cure 04/07/2026) ----------
# Classe « agrégat partiel ≠ total » : un total de grappe tronqué (prix manquants)
# comparé au pic 90j plein fabrique un faux drawdown → faux Stage 2 prescrit.


def test_cluster_value_reports_missing(monkeypatch):
    """compute_cluster_value_eur retourne (total, missing) — missing consultable."""
    monkeypatch.setattr(ks, "_cluster_membership", lambda: {"AAA", "BBB"})
    monkeypatch.setattr(
        ks.storage,
        "get_open_positions",
        lambda: [
            {"ticker": "AAA", "qty": 10},
            {"ticker": "BBB", "qty": 5},
            {"ticker": "CCC", "qty": 2},  # hors grappe → ignoré
        ],
    )
    monkeypatch.setattr(
        ks.prices, "get_current_price_in_eur", lambda t: 100.0 if t == "AAA" else None
    )
    total, missing = ks.compute_cluster_value_eur()
    assert total == 1000.0
    assert missing == ["BBB"]


def test_snapshot_refused_on_missing_price(monkeypatch):
    """Prix manquant → snapshot REFUSÉ (raise) + notify, RIEN d'écrit. Le test
    critique de la classe : jamais un agrégat partiel enregistré comme total."""
    recorded, notified = [], []
    monkeypatch.setattr(ks, "_cfg", lambda: {"enabled": True, "snapshot_max_age_days": 3})
    monkeypatch.setattr(ks, "compute_cluster_value_eur", lambda: (12345.0, ["TSM"]))
    monkeypatch.setattr(
        ks.storage, "record_cluster_snapshot", lambda d, v: recorded.append((d, v))
    )
    monkeypatch.setattr(ks.notify, "send_text", lambda msg, **kw: notified.append(msg))
    with pytest.raises(RuntimeError, match="REFUSÉ"):
        ks.snapshot_cluster_value()
    assert recorded == []
    assert len(notified) == 1 and "TSM" in notified[0]  # l'aveuglement se DIT


def test_snapshot_empty_cluster_skips_silently(monkeypatch):
    """Grappe vide (post-Stage 3, membership vide) = état légitime : pas de row
    à 0 fabriquée, pas de FAIL permanent pour un non-événement (revue 04/07)."""
    recorded = []
    monkeypatch.setattr(ks, "_cfg", lambda: {"enabled": True})
    monkeypatch.setattr(ks, "compute_cluster_value_eur", lambda: (0.0, []))
    monkeypatch.setattr(
        ks.storage, "record_cluster_snapshot", lambda d, v: recorded.append((d, v))
    )
    ks.snapshot_cluster_value()  # pas de raise
    assert recorded == []


def test_snapshot_disabled_config_noop(monkeypatch):
    """kill_switch.enabled=false → le job snapshot ne fait RIEN (pas de raise
    quotidien sur un disjoncteur volontairement désarmé)."""
    def _boom():
        raise AssertionError("compute ne doit pas être appelé quand disabled")

    monkeypatch.setattr(ks, "_cfg", lambda: {"enabled": False})
    monkeypatch.setattr(ks, "compute_cluster_value_eur", _boom)
    ks.snapshot_cluster_value()  # no-op


def test_snapshot_records_when_complete(monkeypatch):
    recorded = []
    monkeypatch.setattr(ks, "_cfg", lambda: {"enabled": True})
    monkeypatch.setattr(ks, "compute_cluster_value_eur", lambda: (42000.0, []))
    monkeypatch.setattr(
        ks.storage, "record_cluster_snapshot", lambda d, v: recorded.append((d, v))
    )
    ks.snapshot_cluster_value()
    assert len(recorded) == 1 and recorded[0][1] == 42000.0


def test_compute_drawdown_stale_snapshot_returns_none(monkeypatch):
    """Snapshot plus vieux que snapshot_max_age_days → None (« je ne sais pas »),
    pas une éval de marché sur du fossile."""
    from datetime import timedelta

    old = (ks._today() - timedelta(days=10)).isoformat()
    monkeypatch.setattr(
        ks, "_cfg", lambda: {"snapshot_max_age_days": 3, "peak_window_days": 90}
    )
    monkeypatch.setattr(
        ks.storage,
        "get_latest_cluster_snapshot",
        lambda: {"snapshot_date": old, "value_eur": 40000.0},
    )
    monkeypatch.setattr(ks.storage, "get_cluster_peak", lambda w: 50000.0)
    assert ks.compute_drawdown() is None


def test_compute_drawdown_age_boundary_ok(monkeypatch):
    """Boundary : âge == snapshot_max_age_days passe encore (stale strict au-delà).
    Horloge FIGÉE (monkeypatch _today) pour tuer la fenêtre de flake minuit-UTC."""
    from datetime import timedelta

    frozen_today = ks._today()
    monkeypatch.setattr(ks, "_today", lambda: frozen_today)
    at_limit = (frozen_today - timedelta(days=3)).isoformat()
    monkeypatch.setattr(
        ks, "_cfg", lambda: {"snapshot_max_age_days": 3, "peak_window_days": 90}
    )
    monkeypatch.setattr(
        ks.storage,
        "get_latest_cluster_snapshot",
        lambda: {"snapshot_date": at_limit, "value_eur": 40000.0},
    )
    monkeypatch.setattr(ks.storage, "get_cluster_peak", lambda w: 50000.0)
    dd = ks.compute_drawdown()
    assert dd is not None
    cur, peak, dd_pct = dd
    assert cur == 40000.0 and peak == 50000.0
    assert round(dd_pct, 2) == -0.2


def test_kill_jobs_wired_through_observed_wrappers():
    """Verrouille le câblage (revue 04/07) : les 3 jobs kill passent par les
    wrappers @scheduler_run_logged de bot/main.py, jamais par les fonctions nues
    — et _stress_gate_check_job ne ré-introduit pas le try/except qui masquait
    les fails au décorateur. Test source (pattern test_smoke_observation)."""
    from pathlib import Path

    src = Path("bot/main.py").read_text()
    for wrapper in ("_kill_snapshot_job", "_kill_check_job", "_kill_escalate_job"):
        assert f"sched.add_job({wrapper}," in src, f"{wrapper} pas câblé au scheduler"
        decorated = f'@scheduler_run_logged("{wrapper.lstrip("_")}")\ndef {wrapper}'
        assert decorated in src, f"{wrapper} sans décorateur scheduler_run_logged"
    assert "sched.add_job(kill_switch." not in src, (
        "un job kill est câblé sur la fonction NUE (bypass observabilité)"
    )
    # _stress_gate_check_job : le try interne masquait le fail au décorateur (M3).
    stress = src.split("def _stress_gate_check_job")[1].split("\n\n\n")[0]
    assert "except Exception" not in stress, (
        "_stress_gate_check_job a ré-introduit le try/except qui masque les fails"
    )


def test_check_and_fire_skips_when_dd_unavailable(monkeypatch):
    """dd None → aucune évaluation d'épisode (pas de stage décidé sur donnée absente)."""
    touched = []
    monkeypatch.setattr(ks, "_cfg", lambda: {"enabled": True})
    monkeypatch.setattr(ks, "compute_drawdown", lambda: None)
    monkeypatch.setattr(
        ks.storage,
        "get_kill_episode_state",
        lambda: touched.append(1) or {"open": False, "worst_stage": 0, "episode_id": 0},
    )
    ks.check_and_fire()
    assert touched == []


def test_escalate_no_fabricated_zeros(monkeypatch):
    """Rappel d'escalade avec dd live indisponible : le message le DIT au lieu
    d'afficher « 0€ vs pic 0€ » (contenu inventé, L3)."""
    sent = []
    monkeypatch.setattr(ks, "_cfg", lambda: {"enabled": True})
    monkeypatch.setattr(ks, "compute_drawdown", lambda: None)
    monkeypatch.setattr(
        ks.storage,
        "get_kill_triggers_by_status",
        lambda s: [{"id": 7, "stage": 2, "level_measured": -0.38}]
        if s == "unresolved"
        else [],
    )
    monkeypatch.setattr(ks.notify, "send_text", lambda msg, **kw: sent.append(msg))
    ks.escalate_unresolved()
    assert len(sent) == 1
    assert "vs pic" not in sent[0]
    assert "indisponible" in sent[0]
    assert "-38.0%" in sent[0]  # dernier niveau mesuré au trigger, pas 0
