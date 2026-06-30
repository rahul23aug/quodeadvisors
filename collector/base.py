"""Collector abstraction used by downstream ingestion code."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from collector.models import Tweet


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

    @abstractmethod
    def checkpoint(self) -> Path:
        """Persist partial collection state and return the checkpoint path."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release external resources gracefully."""
