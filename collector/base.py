"""Collector abstraction used by downstream ingestion code."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from collector.models import CollectorResult, CollectorStatus, Tweet


class BaseCollector(ABC):
    """Interface for source collectors.

    Downstream code should depend on this interface, not Selenium or browser
    automation details.
    """

    @abstractmethod
    def initialize(self) -> None:
        """Initialize external resources required for collection."""

    @abstractmethod
    def collect(self, query: str, limit: int) -> list[Tweet]:
        """Collect up to ``limit`` tweets for ``query``."""

    def collect_result(self, query: str, limit: int) -> CollectorResult:
        """Collect records in a pipeline-safe result envelope."""
        from datetime import datetime, timezone

        started = datetime.now(timezone.utc)
        try:
            records = self.collect(query=query, limit=limit)
            status = CollectorStatus.SUCCESS
            error = None
        except Exception as exc:  # noqa: BLE001 - compatibility wrapper.
            records = []
            status = CollectorStatus.FAILED
            error = str(exc)
        return CollectorResult(
            records=records,
            status=status,
            started_at=started,
            ended_at=datetime.now(timezone.utc),
            error_message=error,
            source_name=self.__class__.__name__,
        )

    @abstractmethod
    def checkpoint(self) -> Path:
        """Persist partial collection state and return the checkpoint path."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release external resources gracefully."""
