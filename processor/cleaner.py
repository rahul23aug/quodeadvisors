"""Tweet cleaning and normalization utilities."""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable

import polars as pl

from collector.models import CollectorResult, Tweet

LOGGER = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")
_KEEP_RE = re.compile(r"[^\w\s#@%$₹.,:+\-]")


def normalize_text(text: str | None) -> str:
    """Normalize unicode, whitespace, case, and noisy symbols in tweet text."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _URL_RE.sub(" ", normalized)
    normalized = _KEEP_RE.sub(" ", normalized)
    normalized = _WS_RE.sub(" ", normalized).strip().lower()
    return normalized


def normalize_entities(values: Iterable[str] | None) -> list[str]:
    """Normalize hashtags or mentions to lowercase strings without leading symbols."""
    if not values:
        return []
    output: list[str] = []
    for value in values:
        cleaned = normalize_text(value).lstrip("#@").strip()
        if cleaned:
            output.append(cleaned)
    return output


def clean_tweets(result: CollectorResult) -> pl.DataFrame:
    """Convert a CollectorResult into a normalized Polars DataFrame."""
    rows = [_tweet_to_row(tweet, result) for tweet in result.records]
    LOGGER.info("event=tweets_cleaned count=%s source=%s", len(rows), result.source_name)
    return pl.DataFrame(rows, schema=_schema(), orient="row")


def _tweet_to_row(tweet: Tweet, result: CollectorResult) -> dict[str, object]:
    content_clean = normalize_text(tweet.content)
    hashtags = normalize_entities(tweet.hashtags)
    mentions = normalize_entities(tweet.mentions)
    timestamp = _parse_timestamp(tweet.timestamp)
    return {
        "tweet_id": tweet.tweet_id,
        "username": normalize_text(tweet.username),
        "display_name": tweet.display_name,
        "timestamp": timestamp,
        "content": tweet.content,
        "content_clean": content_clean,
        "hashtags_norm": hashtags,
        "mentions_norm": mentions,
        "reply_count": _safe_int(tweet.reply_count),
        "retweet_count": _safe_int(tweet.retweet_count),
        "like_count": _safe_int(tweet.like_count),
        "view_count": _safe_int(tweet.view_count),
        "follower_count": _safe_int(tweet.follower_count),
        "following_count": _safe_int(tweet.following_count),
        "url": tweet.url,
        "source_name": result.source_name,
        "collector_status": result.status.value,
        "collected_started_at": result.started_at,
        "collected_ended_at": result.ended_at,
    }


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        LOGGER.warning("event=timestamp_parse_failed value=%r", value)
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_int(value: int | None) -> int:
    return int(value or 0)


def _schema() -> dict[str, Any]:
    return {
        "tweet_id": pl.String,
        "username": pl.String,
        "display_name": pl.String,
        "timestamp": pl.Datetime(time_zone="UTC"),
        "content": pl.String,
        "content_clean": pl.String,
        "hashtags_norm": pl.List(pl.String),
        "mentions_norm": pl.List(pl.String),
        "reply_count": pl.Int64,
        "retweet_count": pl.Int64,
        "like_count": pl.Int64,
        "view_count": pl.Int64,
        "follower_count": pl.Int64,
        "following_count": pl.Int64,
        "url": pl.String,
        "source_name": pl.String,
        "collector_status": pl.String,
        "collected_started_at": pl.Datetime(time_zone="UTC"),
        "collected_ended_at": pl.Datetime(time_zone="UTC"),
    }
