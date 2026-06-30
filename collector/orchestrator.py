"""Source orchestration for live collection with graceful fallback."""

from __future__ import annotations

import logging

from collector.base import BaseCollector
from collector.fallback_sample_collector import FallbackSampleCollector
from collector.models import CollectorResult, CollectorStatus
from collector.selenium_collector import SeleniumCollector

LOGGER = logging.getLogger(__name__)


class SourceOrchestrator:
    """Try a primary collector, then fallback when source access is degraded."""

    fallback_statuses = {
        CollectorStatus.THROTTLED,
        CollectorStatus.LOGIN_REQUIRED,
        CollectorStatus.FAILED,
    }

    def __init__(self, primary: BaseCollector, fallback: BaseCollector | None = None) -> None:
        self.primary = primary
        self.fallback = fallback or FallbackSampleCollector()

    def collect(self, query: str, limit: int) -> CollectorResult:
        """Collect records without exposing source-specific implementation details."""
        primary_result = self._collect_result(self.primary, query, limit)
        if primary_result.status not in self.fallback_statuses:
            return primary_result

        LOGGER.warning(
            "event=source_fallback_triggered primary_source=%r primary_status=%r error=%r",
            primary_result.source_name,
            primary_result.status.value,
            primary_result.error_message,
        )
        fallback_result = self._collect_result(self.fallback, query, limit)
        return fallback_result

    def _collect_result(self, collector: BaseCollector, query: str, limit: int) -> CollectorResult:
        if hasattr(collector, "collect_result"):
            return collector.collect_result(query=query, limit=limit)  # type: ignore[attr-defined]

        # Compatibility path for older BaseCollector implementations.
        import datetime as _dt

        started = _dt.datetime.now(_dt.timezone.utc)
        try:
            records = collector.collect(query=query, limit=limit)
            status = CollectorStatus.SUCCESS
            error = None
        except Exception as exc:  # noqa: BLE001
            records = []
            status = CollectorStatus.FAILED
            error = str(exc)
        return CollectorResult(
            records=records,
            status=status,
            started_at=started,
            ended_at=_dt.datetime.now(_dt.timezone.utc),
            error_message=error,
            source_name=collector.__class__.__name__,
        )
