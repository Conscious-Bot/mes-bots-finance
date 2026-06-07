"""Tests Phase 1.4 absorption_roadmap — verrouille L16 LESSONS.

Doctrine : tout fichier de tuning (`config/calibration.yaml` notamment) doit
porter un bloc `audit_metadata.temporal_splits` lisible AVANT toute decision
de re-tune. Sinon : in-sample tuning silencieux possible.

4 gates :
1. Le bloc existe + a les 5 cles requises
2. Les dates sont parsables (format `YYYY-MM-DD .. YYYY-MM-DD`)
3. oos_window <= next_oos_window (chronologie coherente)
4. next_oos_window debute >= last_audit (la fenetre frozen demarre apres l'audit)

Si un de ces 4 regresse, c'est une violation L16. Le test bloque la build.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

_DATE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s*\.\.\s*(\d{4}-\d{2}-\d{2})$"
)


def _parse_window(s: str) -> tuple[date, date]:
    """Parse 'YYYY-MM-DD .. YYYY-MM-DD' -> (start, end) dates."""
    m = _DATE_RE.match(s.strip())
    assert m, f"Window format invalide : {s!r}. Attendu 'YYYY-MM-DD .. YYYY-MM-DD'."
    start = date.fromisoformat(m.group(1))
    end = date.fromisoformat(m.group(2))
    assert start <= end, f"Window {s!r} : start > end"
    return start, end


def test_temporal_splits_block_present():
    """Gate #1 : bloc temporal_splits existe + 5 cles requises."""
    from shared.calibration import get_temporal_splits

    splits = get_temporal_splits()
    assert splits, (
        "audit_metadata.temporal_splits ABSENT de config/calibration.yaml. "
        "Violation L16 : tout tuning de threshold doit dater train/val/oos. "
        "Cf docs/LESSONS.md L16."
    )
    required = {
        "train_window",
        "val_window",
        "oos_window",
        "next_oos_window",
        "rule",
    }
    missing = required - set(splits.keys())
    assert not missing, (
        f"Cles manquantes dans temporal_splits : {missing}. "
        f"Cf docs/LESSONS.md L16 'La regle' points 1-3."
    )


def test_window_dates_parsable():
    """Gate #2 : les 4 fenetres parsent en (start, end) dates ISO."""
    from shared.calibration import get_temporal_splits

    splits = get_temporal_splits()
    for key in ("train_window", "val_window", "oos_window", "next_oos_window"):
        _parse_window(splits[key])  # raise = test fail


def test_oos_chronology_coherent():
    """Gate #3 : oos_window end <= next_oos_window start.

    Sinon les deux fenetres se chevauchent, ce qui veut dire que des
    predictions resolved dans next_oos seraient deja dans oos -> in-sample
    deguise.
    """
    from shared.calibration import get_temporal_splits

    splits = get_temporal_splits()
    _, oos_end = _parse_window(splits["oos_window"])
    next_start, _ = _parse_window(splits["next_oos_window"])
    assert next_start > oos_end, (
        f"next_oos_window doit demarrer STRICTEMENT apres oos_window. "
        f"oos_end={oos_end} next_start={next_start}. Sinon les fenetres "
        f"se chevauchent -> in-sample deguise. Violation L16."
    )


def test_next_oos_starts_after_last_audit():
    """Gate #4 : next_oos_window start >= last_audit date.

    La fenetre frozen doit demarrer APRES la date d'audit. Sinon l'audit
    a deja peeked dans la fenetre 'forward-only'.
    """
    from shared.calibration import get_audit_metadata, get_temporal_splits

    splits = get_temporal_splits()
    meta = get_audit_metadata()
    last_audit_str = meta.get("last_audit")
    assert last_audit_str, "audit_metadata.last_audit manquant"
    last_audit = date.fromisoformat(str(last_audit_str))
    next_start, _ = _parse_window(splits["next_oos_window"])
    assert next_start >= last_audit, (
        f"next_oos_window doit demarrer >= last_audit. "
        f"last_audit={last_audit} next_start={next_start}. "
        f"Si next_start < last_audit, l'audit a peeked dans la fenetre "
        f"frozen forward-only. Violation L16."
    )


def test_rule_is_non_empty_string():
    """Gate complementaire : la cle `rule` doit etre une string substantielle
    (>= 50 chars) decrivant les conditions de re-tune. Vide ou trop court =
    rituel cargo, pas une vraie regle."""
    from shared.calibration import get_temporal_splits

    splits = get_temporal_splits()
    rule = splits.get("rule", "")
    assert isinstance(rule, str), "rule doit etre une string"
    assert len(rule.strip()) >= 50, (
        f"rule trop courte ({len(rule.strip())} chars). "
        "Doit decrire conditions de re-tune + freeze policy."
    )


@pytest.mark.parametrize("key", ["train_window", "val_window", "oos_window"])
def test_past_windows_have_passed(key):
    """Sanity : les fenetres `train` / `val` / `oos` doivent etre dans le
    passe (end <= aujourd'hui). Sinon on a documente une fenetre future
    comme deja utilisee = incoherence narrative."""
    from shared.calibration import get_temporal_splits

    splits = get_temporal_splits()
    _, end = _parse_window(splits[key])
    today = date.today()
    assert end <= today, (
        f"{key} se termine {end} > today {today}. "
        f"Une fenetre passee ne peut pas finir dans le futur."
    )
