"""Data models emitted by collectors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
