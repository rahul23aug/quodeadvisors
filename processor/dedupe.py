"""Hash-based tweet deduplication."""

from __future__ import annotations

import hashlib
import logging

import polars as pl

from collector.models import Tweet
from processor.cleaner import normalize_text

LOGGER = logging.getLogger(__name__)


class TweetDeduper:
    """O(1) hash lookup deduper for streamed Tweet objects."""

    def __init__(self) -> None:
        self.seen_hashes: set[str] = set()

    def dedupe(self, records: list[Tweet]) -> list[Tweet]:
        """Return records not previously observed by stable tweet hash."""
        output: list[Tweet] = []
        for record in records:
            digest = tweet_hash(record)
            if digest in self.seen_hashes:
                continue
            self.seen_hashes.add(digest)
            output.append(record)
        LOGGER.info("event=tweets_deduped input=%s output=%s", len(records), len(output))
        return output


def tweet_hash(tweet: Tweet) -> str:
    """Build a stable hash using tweet ID when available, else normalized content."""
    key = tweet.tweet_id or f"{normalize_text(tweet.username)}:{normalize_text(tweet.content)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def dedupe_tweets(frame: pl.DataFrame) -> pl.DataFrame:
    """Deduplicate a cleaned tweet DataFrame using hash-set semantics."""
    if frame.is_empty():
        return frame
    seen: set[str] = set()
    keep_indices: list[int] = []
    ids = frame.get_column("tweet_id").to_list()
    contents = frame.get_column("content_clean").to_list()
    for idx, (tweet_id, content) in enumerate(zip(ids, contents, strict=True)):
        key = str(tweet_id or content)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        keep_indices.append(idx)
    LOGGER.info("event=tweet_frame_deduped input=%s output=%s", frame.height, len(keep_indices))
    return frame[keep_indices]
