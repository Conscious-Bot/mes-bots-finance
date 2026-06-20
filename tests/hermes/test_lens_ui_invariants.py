"""Smoke tests pour `hermes.inspector.lens_ui_invariants`.

Garde-fous minimaux : skip silent si serveur down ou Playwright absent.
Aucun test live contre `http://127.0.0.1:8000` (CI = pas de dashboard.serve).
"""
from __future__ import annotations

from hermes.inspector import lens_ui_invariants


def test_scan_skips_when_server_unreachable() -> None:
    """Port 65535 libre -> scan retourne status 'skipped' sans raise."""
    out = lens_ui_invariants.scan(url="http://127.0.0.1:65535/dashboard.html")
    assert out["status"] == "skipped"
    assert "unreachable" in out["reason"].lower()
    assert out["candidates_raw"] == []


def test_scan_returns_expected_shape() -> None:
    """Contract : scan() retourne toujours dict avec candidates_raw + status + url."""
    out = lens_ui_invariants.scan(url="http://127.0.0.1:65535/")
    assert isinstance(out, dict)
    assert "candidates_raw" in out
    assert "status" in out
    assert "url" in out
    assert isinstance(out["candidates_raw"], list)


def test_server_reachable_helper_rejects_dead_port() -> None:
    assert lens_ui_invariants._server_reachable(
        "http://127.0.0.1:65535/anything", timeout=0.5,
    ) is False


def test_findings_dataclass_shape() -> None:
    """UIInvariantFinding instanciable avec tous les champs requis."""
    f = lens_ui_invariants.UIInvariantFinding(
        invariant_id="test_invariant",
        description="rule text",
        evidence="evidence text",
        page="vigie",
        confidence=85,
    )
    assert f.invariant_id == "test_invariant"
    assert f.confidence == 85
