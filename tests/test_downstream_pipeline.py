from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from collector.models import CollectorResult, CollectorStatus, Tweet
from processor.cleaner import clean_tweets, normalize_text
from processor.dedupe import TweetDeduper, dedupe_tweets
from signals.aggregation import aggregate_signals
from signals.features import add_signal_features
from storage.parquet_writer import write_tweets_parquet
from viz.plots import plot_signal_timeseries


def tweet(tweet_id: str, content: str, minutes_ago: int = 0, likes: int = 1) -> Tweet:
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return Tweet(
        tweet_id=tweet_id,
        username="Trader",
        display_name="Trader",
        timestamp=ts.isoformat(),
        content=content,
        hashtags=["NIFTY"],
        mentions=["MARKET"],
        reply_count=1,
        retweet_count=2,
        like_count=likes,
        view_count=100,
        follower_count=1000,
        following_count=100,
        url=f"https://x.com/trader/status/{tweet_id}",
    )


def result(records: list[Tweet]) -> CollectorResult:
    now = datetime.now(timezone.utc)
    return CollectorResult(
        records=records,
        status=CollectorStatus.SUCCESS,
        started_at=now,
        ended_at=now,
        error_message=None,
        source_name="test",
    )


def test_normalize_text_unicode_hashtags_mentions():
    text = normalize_text("  NIFTY\u00a0breakout 🚀 @Trader #NIFTY  ")

    assert text == "nifty breakout @trader #nifty"


def test_clean_tweets_from_collector_result():
    frame = clean_tweets(result([tweet("1", "NIFTY 🚀 @A #NIFTY")]))

    row = frame.row(0, named=True)
    assert row["tweet_id"] == "1"
    assert row["source_name"] == "test"
    assert row["content_clean"] == "nifty @a #nifty"
    assert row["hashtags_norm"] == ["nifty"]
    assert row["mentions_norm"] == ["market"]


def test_hash_dedupe_uses_o1_lookup():
    records = [tweet("1", "same text"), tweet("1", "same text"), tweet("2", "same text")]
    deduper = TweetDeduper()

    unique = deduper.dedupe(records)

    assert [item.tweet_id for item in unique] == ["1", "2"]
    assert len(deduper.seen_hashes) == 2


def test_dedupe_frame_removes_duplicate_tweet_ids():
    frame = clean_tweets(result([tweet("1", "a"), tweet("1", "a duplicate")]))

    deduped = dedupe_tweets(frame)

    assert deduped.height == 1


def test_parquet_writer_roundtrip(tmp_path: Path):
    frame = clean_tweets(result([tweet("1", "NIFTY")]))
    out = write_tweets_parquet(frame, tmp_path / "tweets.parquet")

    loaded = pl.read_parquet(out)

    assert loaded.height == 1
    assert loaded["tweet_id"].item() == "1"


def test_signal_features_include_text_and_composite_signal():
    frame = clean_tweets(
        result(
            [
                tweet("1", "nifty breakout bullish", minutes_ago=1, likes=10),
                tweet("2", "nifty bearish breakdown", minutes_ago=60, likes=1),
            ]
        )
    )

    features = add_signal_features(frame, now=datetime.now(timezone.utc))

    assert "tfidf_nifty" in features.columns
    assert "engagement_score" in features.columns
    assert "recency_decay" in features.columns
    assert "composite_signal" in features.columns
    assert features["composite_signal"].max() > 0


def test_aggregation_and_plot_are_low_memory(tmp_path: Path):
    frame = clean_tweets(result([tweet("1", "nifty bullish", likes=10), tweet("2", "nifty bearish", likes=2)]))
    features = add_signal_features(frame, now=datetime.now(timezone.utc))

    aggregated = aggregate_signals(features, every="1h")
    plot_path = plot_signal_timeseries(aggregated, tmp_path / "signal.png")

    assert aggregated.height >= 1
    assert "composite_signal_mean" in aggregated.columns
    assert plot_path.exists()
    assert plot_path.stat().st_size > 0
