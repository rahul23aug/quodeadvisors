"""Data models emitted by collectors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CollectorStatus(str, Enum):
    """Normalized source collection status for pipeline orchestration."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    THROTTLED = "THROTTLED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    FAILED = "FAILED"


@dataclass(slots=True)
class Tweet:
    """Normalized tweet record for downstream ingestion stages."""

    tweet_id: str
    username: str | None
    display_name: str | None
    timestamp: str | None
    content: str
    hashtags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    reply_count: int | None = None
    retweet_count: int | None = None
    like_count: int | None = None
    view_count: int | None = None
    follower_count: int | None = None
    following_count: int | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(slots=True)
class CollectorResult:
    """Pipeline-safe collector output.

    Downstream consumers should inspect ``status`` instead of handling Selenium
    exceptions or source-specific throttling details.
    """

    records: list[Tweet]
    status: CollectorStatus
    started_at: datetime
    ended_at: datetime
    error_message: str | None
    source_name: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "records": [record.to_dict() for record in self.records],
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "error_message": self.error_message,
            "source_name": self.source_name,
        }
