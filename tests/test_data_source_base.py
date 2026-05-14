"""Tests for shared/data_source_base.py — Sprint 1.2 deliverable."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from shared.data_source_base import (
    BaseDataSource,
    IngestionResult,
    Provenance,
    RateLimiter,
    retry_with_backoff,
)


# === RateLimiter ===


def test_rate_limiter_invalid_rate():
    with pytest.raises(ValueError, match="must be > 0"):
        RateLimiter(requests_per_minute=0)
    with pytest.raises(ValueError, match="must be > 0"):
        RateLimiter(requests_per_minute=-5)


def test_rate_limiter_basic_acquire():
    rl = RateLimiter(requests_per_minute=600)
    # Should not block — plenty of tokens
    rl.acquire(1)
    rl.acquire(5)


def test_rate_limiter_blocks_when_exhausted(monkeypatch):
    """When tokens are exhausted, acquire() sleeps."""
    rl = RateLimiter(requests_per_minute=60)  # 1 token/sec
    # Drain all tokens
    rl.tokens = 0.0
    rl.last_refill = 0.0  # force big elapsed but bounded by capacity

    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))

    rl.last_refill = 0.0  # reset
    rl.tokens = 0.0
    import time as _t
    monkeypatch.setattr(_t, "monotonic", lambda: 0.0)  # freeze time

    rl.acquire(1)
    # Should have slept some positive amount
    assert len(slept) == 1
    assert slept[0] > 0


# === retry_with_backoff ===


def test_retry_succeeds_first_try():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert retry_with_backoff(fn) == "ok"
    assert len(calls) == 1


def test_retry_succeeds_after_transient_failure(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("temp")
        return "ok"

    assert retry_with_backoff(fn, max_attempts=3, base_delay=0.001) == "ok"
    assert len(calls) == 3


def test_retry_raises_after_max_attempts(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    def fn():
        raise ValueError("always fails")

    with pytest.raises(ValueError, match="always fails"):
        retry_with_backoff(fn, max_attempts=2, base_delay=0.001)


def test_retry_only_catches_specified_exceptions(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    def fn():
        raise KeyError("not in catch list")

    with pytest.raises(KeyError):
        # Only catches ValueError, so KeyError propagates immediately
        retry_with_backoff(fn, max_attempts=3, base_delay=0.001, exceptions=(ValueError,))


# === BaseDataSource ===


class StubSource(BaseDataSource):
    """Test stub: configurable failure modes."""

    source_name = "stub"
    rate_limit_rpm = 6000  # fast for tests

    def __init__(
        self,
        raws: list[Any] | None = None,
        fail_fetch: bool = False,
        fail_validate: bool = False,
        fail_persist: bool = False,
    ):
        super().__init__()
        self.raws = raws if raws is not None else []
        self.fail_fetch = fail_fetch
        self.fail_validate = fail_validate
        self.fail_persist = fail_persist
        self.persisted_records: list[Any] = []

    def fetch(self, since=None):
        if self.fail_fetch:
            raise ConnectionError("simulated fetch failure")
        return self.raws

    def validate(self, raw):
        if self.fail_validate:
            raise ValueError("simulated validate failure")
        if raw == "skip":
            return None
        return {"validated": raw}

    def persist(self, validated, provenance):
        if self.fail_persist:
            raise RuntimeError("simulated persist failure")
        self.persisted_records.append(validated)
        return len(self.persisted_records)


def test_basesource_requires_source_name():
    class Bad(BaseDataSource):
        def fetch(self, since=None):
            return []

        def validate(self, raw):
            return None

        def persist(self, v, p):
            return None

    with pytest.raises(ValueError, match="source_name"):
        Bad()


def test_basesource_ingest_full_happy_path():
    src = StubSource(raws=["a", "b", "skip", "c"])
    result = src.ingest()
    assert result.source == "stub"
    assert result.fetched == 4
    assert result.validated == 3  # "skip" returns None
    assert result.persisted == 3
    assert result.skipped == 1
    assert result.errors == []
    assert result.duration_seconds >= 0


def test_basesource_validate_error(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    src = StubSource(raws=["a", "b"], fail_validate=True)
    result = src.ingest()
    assert result.fetched == 2
    assert result.validated == 0
    assert result.persisted == 0
    assert len(result.errors) == 2
    assert all("validate" in e for e in result.errors)


def test_basesource_persist_error(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    src = StubSource(raws=["a"], fail_persist=True)
    result = src.ingest()
    assert result.fetched == 1
    assert result.validated == 1
    assert result.persisted == 0
    assert len(result.errors) == 1
    assert "persist" in result.errors[0]


def test_basesource_fetch_error_short_circuits(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    src = StubSource(raws=["a"], fail_fetch=True)
    result = src.ingest()
    assert result.fetched == 0
    assert result.validated == 0
    assert result.persisted == 0
    assert len(result.errors) == 1
    assert "fetch" in result.errors[0]


def test_basesource_shadow_mode():
    class ShadowStub(StubSource):
        shadow_mode = True

    src = ShadowStub(raws=["a", "b"])
    result = src.ingest()
    assert result.fetched == 2
    assert result.validated == 2
    assert result.persisted == 0  # shadow mode: validated but not persisted
    assert len(src.persisted_records) == 0


def test_basesource_feature_flag_disabled():
    class FlaggedStub(StubSource):
        feature_flag_key = "nonexistent.flag.path"

    src = FlaggedStub(raws=["a", "b"])
    result = src.ingest()
    # Disabled: nothing happens
    assert result.fetched == 0
    assert result.validated == 0
    assert result.persisted == 0
    assert result.errors == []


def test_provenance_dataclass():
    now = datetime.now(timezone.utc)
    p = Provenance(source="test", as_of=now, vintage="v1")
    assert p.source == "test"
    assert p.as_of == now
    assert p.vintage == "v1"


def test_ingestion_result_summary():
    r = IngestionResult(
        source="src", fetched=10, validated=8, persisted=7, skipped=1, errors=["e1"], duration_seconds=1.5
    )
    s = r.summary()
    assert "src" in s
    assert "fetched=10" in s
    assert "validated=8" in s
    assert "persisted=7" in s
    assert "skipped=1" in s
    assert "errors=1" in s
    assert "1.50" in s
