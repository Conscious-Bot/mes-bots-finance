"""Abstract base class for data ingestion sources.

Sprint 1.2 deliverable. Provides common pattern reused across all data sources:
- Feature flag check (config.yaml gating)
- Rate limiting (token bucket per source)
- Retry with exponential backoff
- Provenance metadata attached to every record (source/as_of/vintage)
- Shadow mode (validate without persist, for new sources under evaluation)
- IngestionResult telemetry (fetched/validated/persisted/skipped/errors/duration)

Subclasses implement: fetch(since), validate(raw), persist(validated, provenance).

Usage pattern (subclass):
    class MySource(BaseDataSource):
        source_name = "my_source"
        rate_limit_rpm = 30
        feature_flag_key = "sources.my_source.enabled"  # optional

        def fetch(self, since=None):
            # pull raw records from external API
            return [...]

        def validate(self, raw):
            # convert raw to dict or Pydantic model
            # return None to skip silently
            return MyValidatedModel.model_validate(raw)

        def persist(self, validated, provenance):
            # write to DB with provenance attached
            return storage.insert_my_thing(validated, provenance)

    result = MySource().ingest(since=yesterday)
    log.info(result.summary())
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Provenance:
    """Metadata attached to every ingested record for traceability + PIT bitemporality."""

    source: str
    as_of: datetime  # when we ingested
    vintage: str = ""  # snapshot of source-side metadata (immutable per ingestion batch)


@dataclass
class IngestionResult:
    """Summary of one ingest() run."""

    source: str
    fetched: int = 0
    validated: int = 0
    persisted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"{self.source}: fetched={self.fetched} validated={self.validated} "
            f"persisted={self.persisted} skipped={self.skipped} "
            f"errors={len(self.errors)} duration={self.duration_seconds:.2f}s"
        )


class RateLimiter:
    """Simple token bucket. acquire() blocks until tokens available."""

    def __init__(self, requests_per_minute: int):
        if requests_per_minute <= 0:
            raise ValueError(f"requests_per_minute must be > 0, got {requests_per_minute}")
        self.rate_per_sec = requests_per_minute / 60.0
        self.capacity = float(requests_per_minute)
        self.tokens = float(requests_per_minute)
        self.last_refill = time.monotonic()

    def acquire(self, n: int = 1) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
        self.last_refill = now
        if self.tokens < n:
            wait_s = (n - self.tokens) / self.rate_per_sec
            time.sleep(wait_s)
            self.tokens = 0.0
        else:
            self.tokens -= n


def retry_with_backoff(
    fn: Callable[[], Any],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Any:
    """Run `fn()` with exponential backoff. Returns fn() or raises last exception."""
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except exceptions as e:
            last_exc = e
            if attempt + 1 < max_attempts:
                delay = base_delay * (2**attempt)
                log.warning(
                    f"retry_with_backoff: attempt {attempt + 1}/{max_attempts} failed "
                    f"({type(e).__name__}: {e}), waiting {delay}s"
                )
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


class BaseDataSource(ABC):
    """Abstract data source. Subclass to implement specific external API integration.

    Required class attribute:
        source_name: identifier (e.g. "gmail", "edgar", "fmp")

    Optional class attributes (defaults shown):
        rate_limit_rpm = 60: requests per minute
        feature_flag_key = None: config key (dotted path), if set the
            source is disabled unless config[that.key] is truthy
        shadow_mode = False: if True, validate but skip persist

    Required methods:
        fetch(since) -> list of raw records
        validate(raw) -> validated record or None (silent skip)
        persist(validated, provenance) -> inserted ID or None (dedup)
    """

    source_name: str = ""
    rate_limit_rpm: int = 60
    feature_flag_key: str | None = None
    shadow_mode: bool = False

    def __init__(self) -> None:
        if not self.source_name:
            raise ValueError(f"{type(self).__name__}: source_name class attribute must be set")
        self._rate_limiter = RateLimiter(self.rate_limit_rpm)

    @abstractmethod
    def fetch(self, since: datetime | None = None) -> list[Any]:
        """Pull raw records from the external source."""

    @abstractmethod
    def validate(self, raw: Any) -> Any | None:
        """Validate one raw record. Return validated record or None to skip silently."""

    @abstractmethod
    def persist(self, validated: Any, provenance: Provenance) -> int | None:
        """Persist one validated record. Return inserted ID or None on dedup/skip."""

    def is_enabled(self) -> bool:
        """Check feature flag in config.yaml. Default: enabled."""
        if not self.feature_flag_key:
            return True
        from shared import config as cfg_mod

        cfg = cfg_mod.load()
        node: Any = cfg
        for key in self.feature_flag_key.split("."):
            if not isinstance(node, dict) or key not in node:
                return False
            node = node[key]
        return bool(node)

    def ingest(self, since: datetime | None = None) -> IngestionResult:
        """Run the full pipeline: fetch -> validate -> persist with provenance + telemetry."""
        result = IngestionResult(source=self.source_name)
        started = time.monotonic()

        if not self.is_enabled():
            log.info(f"{self.source_name}: feature flag '{self.feature_flag_key}' off, skipping")
            result.duration_seconds = time.monotonic() - started
            return result

        # Fetch with retry + rate limiting
        self._rate_limiter.acquire()
        try:
            raws = retry_with_backoff(lambda: self.fetch(since=since))
        except Exception as e:
            log.exception(f"{self.source_name}: fetch failed after retries")
            result.errors.append(f"fetch: {type(e).__name__}: {e}")
            result.duration_seconds = time.monotonic() - started
            return result

        result.fetched = len(raws)

        # Build provenance for this batch (immutable, shared by all rows)
        as_of = datetime.now(UTC)
        provenance = Provenance(
            source=self.source_name,
            as_of=as_of,
            vintage=f"{self.source_name}@{as_of.isoformat()}",
        )

        # Validate + persist each record
        for raw in raws:
            try:
                validated = self.validate(raw)
            except Exception as e:
                result.errors.append(f"validate: {type(e).__name__}: {e}")
                continue

            if validated is None:
                result.skipped += 1
                continue

            result.validated += 1

            if self.shadow_mode:
                log.debug(f"{self.source_name}: shadow mode, skipping persist")
                continue

            try:
                inserted = self.persist(validated, provenance)
                if inserted is not None:
                    result.persisted += 1
                else:
                    result.skipped += 1
            except Exception as e:
                log.exception(f"{self.source_name}: persist failed")
                result.errors.append(f"persist: {type(e).__name__}: {e}")

        result.duration_seconds = time.monotonic() - started
        log.info(result.summary())
        return result
