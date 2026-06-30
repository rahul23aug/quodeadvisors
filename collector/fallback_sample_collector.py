"""Fallback collector backed by local JSONL sample data."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collector.base import BaseCollector
from collector.models import CollectorResult, CollectorStatus, Tweet


class FallbackSampleCollector(BaseCollector):
    """Read normalized tweets from a JSONL file using the shared Tweet model."""

    source_name = "sample_jsonl"

    def __init__(self, sample_path: str | Path = Path("data/input/sample_tweets.jsonl")) -> None:
        self.sample_path = Path(sample_path)
        self.records: list[Tweet] = []

    def initialize(self) -> None:
        """Load sample records from disk."""
        self.records = self._read_records()

    def collect(self, query: str, limit: int) -> list[Tweet]:
        """Backward-compatible raw record collection."""
        return self.collect_result(query=query, limit=limit).records

    def collect_result(self, query: str, limit: int) -> CollectorResult:
        """Return sample records in the same envelope as live collectors."""
        started = datetime.now(timezone.utc)
        try:
            self.initialize()
            records = self.records[:limit]
            status = CollectorStatus.SUCCESS if records else CollectorStatus.FAILED
            error = None if records else f"sample file has no records: {self.sample_path}"
        except Exception as exc:  # noqa: BLE001 - source failure must not leak implementation details.
            records = []
            status = CollectorStatus.FAILED
            error = str(exc)
        return CollectorResult(
            records=records,
            status=status,
            started_at=started,
            ended_at=datetime.now(timezone.utc),
            error_message=error,
            source_name=self.source_name,
        )

    def checkpoint(self) -> Path:
        """Sample collector is read-only; return the configured source path."""
        return self.sample_path

    def shutdown(self) -> None:
        """No external resources to release."""

    def _read_records(self) -> list[Tweet]:
        if not self.sample_path.exists():
            raise FileNotFoundError(f"sample tweet file not found: {self.sample_path}")

        allowed = {field.name for field in fields(Tweet)}
        records: list[Tweet] = []
        for line_number, line in enumerate(self.sample_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            payload: dict[str, Any] = json.loads(line)
            filtered = {key: value for key, value in payload.items() if key in allowed}
            try:
                records.append(Tweet(**filtered))
            except TypeError as exc:
                raise ValueError(f"invalid tweet payload at {self.sample_path}:{line_number}: {exc}") from exc
        return records
