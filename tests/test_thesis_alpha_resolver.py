"""Tests pièce 4 — resolver cron thesis_predictions.

Les tests passent un stub `fetcher` (DI > monkeypatch global, cf patch
db97b44 + cure packaging #128 12/06/2026). Le resolver reste storage-only
en transitif → runnable sur venv minimal sans google-auth/yfinance/pandas
installés. Le resolver est pure orchestration : fetch (stubbed) + compute
alpha (helpers thesis_alpha) + write atomique (writers).

Matrice 15 tests :
- happy path + retry-within-grace via fallback yfinance interne
- Garde §4.3 CRITIQUE : prix dispo HORS grâce (fallback +10j yfinance) → REJETÉ
- Defer in-grace sans prix → laisse NULL, re-pickup demain
- Magnitude 4 quadrants : bull-correct/bear-correct/bull-incorrect/bear-incorrect
- Magnitude=NULL sans confidence + neutral
- Neutral resolve : exclude_reason='neutral' + resolution_status='resolved'
- Prix NaN/0/-1 → traité comme manquant
- Classify=None défensif → log error, NULL, JAMAIS abandon
- Invariant counters : attempted == resolved + neutral + abandoned + deferred + classify_none_bugs
"""
from __future__ import annotations

from datetime import date

import pytest


def _pose_pred(**overrides):
    """Helper : insère une pose SK Hynix scenario par défaut, retourne pred_id."""
    from shared.thesis_predictions_writer import insert_thesis_pose
    base = {
        "ticker": "000660.KS",
        "asof": date(2026, 6, 10),
        "asof_price_native": 2_077_000.0,
        "native_currency": "KRW",
        "pt_consensus_raw": 2_300_000.0,
        "pt_consensus_currency": "KRW",
        "pt_native_asof": 2_300_000.0,
        "fx_at_asof": 1.0,
        "your_target_native": 3_800_000.0,
        "your_delta_native_pct": 72.2,
        "thesis_summary": "SK Hynix HBM gen5 bull thesis",
        "resolve_due_date": date(2027, 6, 10),
        "source": "sweep_133",
    }
    base.update(overrides)
    return insert_thesis_pose(**base)


def _stub_fetcher(returns):
    """Stub fetcher pour resolve_due_thesis_predictions(fetcher=...).

    `returns` : soit un tuple (actual_date_str, price), soit un callable
    (ticker, date_str) → tuple. Le stub est passé par injection (DI) au
    resolver, qui ne touche jamais shared.prices → reste storage-only.
    """
    def stub(ticker, d):
        if callable(returns):
            return returns(ticker, d)
        return returns
    return stub


# ============================================================
# Happy path + retry via fallback yfinance interne
# ============================================================


def test_resolve_happy_path_price_at_due_date(migrated_db):
    """Prix dispo pile à due_date → resolve correct, counter resolved+=1."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    from shared import storage
    pid = _pose_pred()
    fetcher = _stub_fetcher(("2027-06-10", 2_500_000.0))
    counters = resolve_due_thesis_predictions(today=date(2027, 6, 10), fetcher=fetcher)
    assert counters["attempted"] == 1
    assert counters["resolved"] == 1
    with storage.db() as cx:
        row = cx.execute(
            "SELECT direction_correct, resolution_status, alpha_realized_pct "
            "FROM thesis_predictions WHERE id=?", (pid,)
        ).fetchone()
    assert row[0] == 1  # correct (alpha > 0, delta > 0)
    assert row[1] == "resolved"


def test_resolve_uses_yfinance_fallback_within_grace(migrated_db):
    """get_price_on_date interne fait fallback +10j. Si actual=due+3 (in grace) → resolve."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    _pose_pred()
    # Mock simule fallback yfinance qui a retourné due+3
    fetcher = _stub_fetcher(("2027-06-13", 2_500_000.0))
    counters = resolve_due_thesis_predictions(today=date(2027, 6, 13), fetcher=fetcher)
    assert counters["resolved"] == 1
    assert counters["deferred"] == 0
    assert counters["abandoned"] == 0


# ============================================================
# Garde §4.3 CRITIQUE — fallback yfinance hors grâce
# ============================================================


def test_resolver_rejects_price_beyond_grace_deadline_anti_downtime_drift(migrated_db):
    """SPEC §4.3 catch critique : get_price_on_date scanne +10j en interne.
    Si actual=due+7 > deadline due+5 → REJETÉ, traité comme manquant.

    Scénario : resolver down 10j, today=due+10. Le fallback yfinance retourne
    due+7. SANS le garde, on prendrait ce prix (viol §4.3). AVEC le garde,
    on traite comme manquant → grâce expirée → abandon terminal.
    """
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    from shared import storage
    pid = _pose_pred()
    # Mock : fallback yfinance retourne due+7, hors grâce (deadline due+5)
    fetcher = _stub_fetcher(("2027-06-17", 2_500_000.0))
    # today=due+10 → grâce expirée
    counters = resolve_due_thesis_predictions(today=date(2027, 6, 20), fetcher=fetcher)
    assert counters["abandoned"] == 1
    assert counters["resolved"] == 0
    assert counters["deferred"] == 0
    with storage.db() as cx:
        row = cx.execute(
            "SELECT resolution_status, alpha_realized_pct FROM thesis_predictions WHERE id=?",
            (pid,)
        ).fetchone()
    assert row[0] == "abandoned"
    assert row[1] is None  # PAS de resolve_price_native enregistré


def test_resolver_grace_active_with_no_price_defers(migrated_db):
    """In-grace + pas de prix valide (mock None) → defer (NULL, re-pickup demain)."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    from shared import storage
    pid = _pose_pred()
    fetcher = _stub_fetcher((None, None))
    counters = resolve_due_thesis_predictions(today=date(2027, 6, 12), fetcher=fetcher)  # in-grace
    assert counters["deferred"] == 1
    assert counters["resolved"] == 0
    assert counters["abandoned"] == 0
    with storage.db() as cx:
        row = cx.execute(
            "SELECT resolved_at, resolution_status FROM thesis_predictions WHERE id=?",
            (pid,)
        ).fetchone()
    assert row[0] is None  # resolved_at NULL → re-pickup demain
    assert row[1] is None


def test_resolver_grace_expired_with_no_price_abandons(migrated_db):
    """Grâce expirée + pas de prix valide → mark_abandoned terminal."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    _pose_pred()
    fetcher = _stub_fetcher((None, None))
    counters = resolve_due_thesis_predictions(today=date(2027, 6, 20), fetcher=fetcher)
    assert counters["abandoned"] == 1


# ============================================================
# Prix invalides (NaN, 0, ≤0) → manquant
# ============================================================


def test_resolver_treats_nan_price_as_missing(migrated_db):
    """Prix NaN → manquant (jamais propagé à compute_alpha)."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    _pose_pred()
    fetcher = _stub_fetcher(("2027-06-10", float("nan")))
    counters = resolve_due_thesis_predictions(today=date(2027, 6, 12), fetcher=fetcher)
    assert counters["deferred"] == 1


def test_resolver_treats_zero_price_as_missing(migrated_db):
    """Prix = 0 → manquant."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    _pose_pred()
    fetcher = _stub_fetcher(("2027-06-10", 0.0))
    counters = resolve_due_thesis_predictions(today=date(2027, 6, 12), fetcher=fetcher)
    assert counters["deferred"] == 1


def test_resolver_treats_negative_price_as_missing(migrated_db):
    """Prix négatif → manquant."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    _pose_pred()
    fetcher = _stub_fetcher(("2027-06-10", -1.0))
    counters = resolve_due_thesis_predictions(today=date(2027, 6, 12), fetcher=fetcher)
    assert counters["deferred"] == 1


# ============================================================
# Magnitude 4 quadrants (catch red-team outcome=sign(alpha))
# ============================================================


def test_magnitude_bull_correct(migrated_db):
    """δ>0, α>0, conf=0.8 → prob=0.9, outcome=1 → 0.01."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    from shared import storage
    pid = _pose_pred(confidence=0.8, your_delta_native_pct=10.0)
    fetcher = _stub_fetcher(("2027-06-10", 2_300_000.0))  # alpha = 0/asof*100 ... mais going voir
    # alpha = (2_300_000 - 2_300_000) / 2_077_000 * 100 = 0 = neutral
    # Going utiliser une autre valeur pour bull-correct net :
    fetcher = _stub_fetcher(("2027-06-10", 2_500_000.0))
    # alpha = (2_500_000 - 2_300_000) / 2_077_000 * 100 = +9.63% (bull correct)
    resolve_due_thesis_predictions(today=date(2027, 6, 10), fetcher=fetcher)
    with storage.db() as cx:
        score = cx.execute(
            "SELECT magnitude_score FROM thesis_predictions WHERE id=?", (pid,)
        ).fetchone()[0]
    # prob = 0.5 + 0.8 * 0.5 * (+1) = 0.9, outcome = 1 → (0.9-1)² = 0.01
    assert score == pytest.approx(0.01)


def test_magnitude_bear_correct(migrated_db):
    """δ<0, α<0, conf=0.8 → prob=0.1, outcome=0 → 0.01 (PAS 0.81).

    Catch red-team Olivier : si on codait outcome=direction_correct=1,
    le score serait (0.1-1)² = 0.81 = catastrophe sur un pari JUSTE.
    """
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    from shared import storage
    pid = _pose_pred(
        confidence=0.8,
        your_delta_native_pct=-10.0,  # bear thesis
        your_target_native=1_600_000.0,  # cible bear < pt_native
    )
    # alpha < 0 → bear correct
    fetcher = _stub_fetcher(("2027-06-10", 2_000_000.0))
    # alpha = (2_000_000 - 2_300_000) / 2_077_000 * 100 = -14.4% (bear correct, |α|>ε)
    resolve_due_thesis_predictions(today=date(2027, 6, 10), fetcher=fetcher)
    with storage.db() as cx:
        score = cx.execute(
            "SELECT magnitude_score FROM thesis_predictions WHERE id=?", (pid,)
        ).fetchone()[0]
    # prob = 0.5 + 0.8 * 0.5 * (-1) = 0.1, outcome = 0 → (0.1-0)² = 0.01
    assert score == pytest.approx(0.01)


def test_magnitude_bull_incorrect(migrated_db):
    """δ>0, α<0, conf=0.8 → prob=0.9, outcome=0 → 0.81."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    from shared import storage
    pid = _pose_pred(confidence=0.8, your_delta_native_pct=+10.0)
    fetcher = _stub_fetcher(("2027-06-10", 2_000_000.0))
    # alpha = -14.4% (bull incorrect)
    resolve_due_thesis_predictions(today=date(2027, 6, 10), fetcher=fetcher)
    with storage.db() as cx:
        score = cx.execute(
            "SELECT magnitude_score FROM thesis_predictions WHERE id=?", (pid,)
        ).fetchone()[0]
    # prob = 0.9, outcome = 0 → (0.9-0)² = 0.81
    assert score == pytest.approx(0.81)


def test_magnitude_bear_incorrect(migrated_db):
    """δ<0, α>0, conf=0.8 → prob=0.1, outcome=1 → 0.81."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    from shared import storage
    pid = _pose_pred(
        confidence=0.8, your_delta_native_pct=-10.0, your_target_native=1_600_000.0,
    )
    fetcher = _stub_fetcher(("2027-06-10", 2_500_000.0))  # alpha positif
    resolve_due_thesis_predictions(today=date(2027, 6, 10), fetcher=fetcher)
    with storage.db() as cx:
        score = cx.execute(
            "SELECT magnitude_score FROM thesis_predictions WHERE id=?", (pid,)
        ).fetchone()[0]
    # prob = 0.1, outcome = 1 → (0.1-1)² = 0.81
    assert score == pytest.approx(0.81)


def test_magnitude_null_when_no_confidence(migrated_db):
    """confidence=None → magnitude=NULL (pas de Brier sans calibration)."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    from shared import storage
    pid = _pose_pred(confidence=None)
    fetcher = _stub_fetcher(("2027-06-10", 2_500_000.0))
    resolve_due_thesis_predictions(today=date(2027, 6, 10), fetcher=fetcher)
    with storage.db() as cx:
        score = cx.execute(
            "SELECT magnitude_score FROM thesis_predictions WHERE id=?", (pid,)
        ).fetchone()[0]
    assert score is None


def test_magnitude_null_when_neutral_alpha(migrated_db):
    """|alpha|<ε_neutre → magnitude=NULL (zone neutre, pas de Brier outcome)."""
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    from shared import storage
    pid = _pose_pred(confidence=0.8)
    # alpha=0.2% < ε_neutre=1.0% → neutral
    # asof=2_077_000, pt=2_300_000. Pour alpha=0.2%, price = pt + 0.2/100 * asof = 2_300_000 + 4_154 = 2_304_154
    fetcher = _stub_fetcher(("2027-06-10", 2_304_154.0))
    resolve_due_thesis_predictions(today=date(2027, 6, 10), fetcher=fetcher)
    with storage.db() as cx:
        row = cx.execute(
            "SELECT magnitude_score, exclude_reason, resolution_status "
            "FROM thesis_predictions WHERE id=?", (pid,)
        ).fetchone()
    assert row[0] is None  # magnitude NULL
    assert row[1] == "neutral"  # exclude_reason
    assert row[2] == "resolved"  # lifecycle


# ============================================================
# Garde classify=None défensif (fail-loud, jamais abandon)
# ============================================================


def test_classify_none_defensive_logs_and_defers(migrated_db, monkeypatch):
    """classify=None malgré prix valide = bug logique (inatteignable normalement).
    Resolver : log error + log_event + counter classify_none_bugs+=1 + defer
    (resolved_at reste NULL). JAMAIS abandon silencieux."""
    from bot.jobs import thesis_alpha_resolver as resolver_module
    from shared import storage
    pid = _pose_pred()
    fetcher = _stub_fetcher(("2027-06-10", 2_500_000.0))
    # Force classify_direction à retourner None (mock le helper dans le module resolver)
    monkeypatch.setattr(
        resolver_module, "classify_direction",
        lambda **kwargs: None,
    )
    counters = resolver_module.resolve_due_thesis_predictions(today=date(2027, 6, 10), fetcher=fetcher)
    assert counters["classify_none_bugs"] == 1
    assert counters["abandoned"] == 0  # PAS abandon
    assert counters["resolved"] == 0
    # resolved_at reste NULL → re-pickup demain par get_due
    with storage.db() as cx:
        row = cx.execute(
            "SELECT resolved_at, resolution_status FROM thesis_predictions WHERE id=?",
            (pid,)
        ).fetchone()
    assert row[0] is None
    assert row[1] is None
    # log_event 'thesis_resolve_classify_none_bug' émis
    with storage.db() as cx:
        events = cx.execute(
            "SELECT event_type FROM bot_events "
            "WHERE event_type='thesis_resolve_classify_none_bug'"
        ).fetchall()
    assert len(events) == 1


# ============================================================
# Invariant counters
# ============================================================


def test_write_failed_increments_on_update_resolve_returning_false(migrated_db, monkeypatch):
    """Cure L27 : si update_thesis_resolve_fields retourne False (race,
    trigger 2 mord), counter write_failed+=1. Sans ça, attempted == Σ
    casserait silencieusement → invariant L27 violé.
    """
    from bot.jobs import thesis_alpha_resolver as resolver_module
    _pose_pred()
    fetcher = _stub_fetcher(("2027-06-10", 2_500_000.0))
    # Mock update_thesis_resolve_fields à False (simule trigger 2 mord ou race)
    monkeypatch.setattr(
        resolver_module, "update_thesis_resolve_fields",
        lambda **kw: False,
    )
    counters = resolver_module.resolve_due_thesis_predictions(today=date(2027, 6, 10), fetcher=fetcher)
    assert counters["attempted"] == 1
    assert counters["write_failed"] == 1
    assert counters["resolved"] == 0
    # Invariant tient malgré l'échec writer
    total = sum(counters[k] for k in (
        "resolved", "neutral", "abandoned", "deferred", "classify_none_bugs", "write_failed"
    ))
    assert total == counters["attempted"]


def test_write_failed_increments_on_mark_abandoned_returning_false(migrated_db, monkeypatch):
    """Cure L27 : si mark_thesis_prediction_abandoned retourne False,
    counter write_failed+=1. Invariant L27 préservé."""
    from bot.jobs import thesis_alpha_resolver as resolver_module
    _pose_pred()
    fetcher = _stub_fetcher((None, None))  # pas de prix
    monkeypatch.setattr(
        resolver_module, "mark_thesis_prediction_abandoned",
        lambda **kw: False,
    )
    # today=due+10 → grâce expirée → tente mark_abandoned (qui rend False)
    counters = resolver_module.resolve_due_thesis_predictions(today=date(2027, 6, 20), fetcher=fetcher)
    assert counters["attempted"] == 1
    assert counters["write_failed"] == 1
    assert counters["abandoned"] == 0
    total = sum(counters[k] for k in (
        "resolved", "neutral", "abandoned", "deferred", "classify_none_bugs", "write_failed"
    ))
    assert total == counters["attempted"]


def test_counters_invariant_attempted_equals_sum(migrated_db):
    """attempted == resolved + neutral + abandoned + deferred + classify_none_bugs + write_failed.

    Bat un batch hétérogène : 1 resolved + 1 deferred + 1 abandoned.
    """
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions
    # Pose 3 predictions toutes due aujourd'hui
    _pose_pred(ticker="000660.KS", resolve_due_date=date(2027, 6, 10))
    _pose_pred(
        ticker="CCJ", asof=date(2026, 6, 10),
        native_currency="USD", pt_consensus_currency="USD",
        pt_consensus_raw=138.0, pt_native_asof=138.0,
        asof_price_native=105.0, your_target_native=155.0, your_delta_native_pct=16.0,
        thesis_summary="CCJ supercycle",
        resolve_due_date=date(2027, 6, 10),
    )
    _pose_pred(
        ticker="MU", asof=date(2026, 6, 10),
        native_currency="USD", pt_consensus_currency="USD",
        pt_consensus_raw=520.0, pt_native_asof=520.0,
        asof_price_native=500.0, your_target_native=700.0, your_delta_native_pct=40.0,
        thesis_summary="MU memory cycle",
        resolve_due_date=date(2027, 6, 10),
    )

    # Stub fetcher : resolved pour SK, defer pour CCJ, abandoned pour MU
    def mock_fetch(ticker, due_date):
        if ticker == "000660.KS":
            return ("2027-06-10", 2_500_000.0)  # resolved
        if ticker == "CCJ":
            return (None, None)  # in-grace, defer
        if ticker == "MU":
            return ("2027-06-25", 800.0)  # actual hors grâce → traité manquant
        return (None, None)
    fetcher = _stub_fetcher(mock_fetch)

    counters = resolve_due_thesis_predictions(today=date(2027, 6, 20), fetcher=fetcher)
    # today=2027-06-20 → grâce=2027-06-15 expirée pour due=2027-06-10
    # SK : prix valide à due (in grace) → resolved
    # CCJ : (None, None) ET today > deadline → abandoned (pas defer)
    # MU : prix dispo hors grâce ET today > deadline → abandoned
    total = sum(counters[k] for k in (
        "resolved", "neutral", "abandoned", "deferred", "classify_none_bugs", "write_failed"
    ))
    assert counters["attempted"] == 3
    assert total == 3  # invariant L27 garanti par construction
