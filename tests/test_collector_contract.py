from pathlib import Path

import pytest

from collector.base import BaseCollector
from collector.exceptions import ConfigurationError, RateLimited
from collector.models import Tweet
from collector.selenium_collector import SeleniumCollector
from config.settings import CollectorSettings, ThrottlingSettings


def test_tweet_dataclass_contains_required_fields():
    tweet = Tweet(
        tweet_id="123",
        username="trader",
        display_name="Trader",
        timestamp="2026-07-01T10:00:00Z",
        content="NIFTY breakout #NIFTY @market",
        hashtags=["NIFTY"],
        mentions=["market"],
        reply_count=1,
        retweet_count=2,
        like_count=3,
        view_count=4,
        follower_count=100,
        following_count=25,
        url="https://x.com/trader/status/123",
    )

    assert tweet.tweet_id == "123"
    assert tweet.follower_count == 100
    assert tweet.following_count == 25
    assert tweet.to_dict()["hashtags"] == ["NIFTY"]


def test_selenium_collector_implements_base_collector():
    collector = SeleniumCollector(settings=CollectorSettings())

    assert isinstance(collector, BaseCollector)


def test_search_url_encodes_query_and_recent_mode():
    collector = SeleniumCollector(settings=CollectorSettings())

    url = collector.build_search_url("NIFTY breakout")

    assert url.startswith("https://x.com/search?")
    assert "NIFTY%20breakout" in url
    assert "src=typed_query" in url
    assert "f=live" in url


def test_settings_reject_invalid_wait_range():
    with pytest.raises(ConfigurationError):
        CollectorSettings(min_wait_seconds=5.0, max_wait_seconds=1.0)


def test_profile_path_must_exist(tmp_path: Path):
    missing = tmp_path / "missing-profile"

    with pytest.raises(ConfigurationError):
        CollectorSettings(chrome_profile_path=missing)


def test_throttling_detector_flags_empty_scrolls():
    settings = CollectorSettings(
        throttling=ThrottlingSettings(max_consecutive_empty_scrolls=2),
    )
    collector = SeleniumCollector(settings=settings)

    collector.metrics.record_scroll(new_tweets=0, duplicates=0)
    collector.metrics.record_scroll(new_tweets=0, duplicates=0)

    assert collector.should_backoff() is True


def test_throttling_detector_flags_duplicate_heavy_batches():
    settings = CollectorSettings(
        throttling=ThrottlingSettings(max_duplicate_ratio=0.5),
    )
    collector = SeleniumCollector(settings=settings)

    collector.metrics.record_scroll(new_tweets=1, duplicates=4)

    assert collector.should_backoff() is True


def test_extraction_helpers_parse_counts_and_entities():
    collector = SeleniumCollector(settings=CollectorSettings())

    assert collector.parse_count("1.2K") == 1200
    assert collector.parse_count("3M") == 3000000
    assert collector.extract_hashtags("Buy #NIFTY and #BANKNIFTY") == ["NIFTY", "BANKNIFTY"]
    assert collector.extract_mentions("Thanks @alice @bob") == ["alice", "bob"]


def test_checkpoint_writes_partial_state(tmp_path: Path):
    settings = CollectorSettings(checkpoint_path=tmp_path / "checkpoint.json")
    collector = SeleniumCollector(settings=settings)
    collector.collected_tweets["123"] = Tweet(
        tweet_id="123",
        username="trader",
        display_name="Trader",
        timestamp=None,
        content="hello",
        hashtags=[],
        mentions=[],
        reply_count=None,
        retweet_count=None,
        like_count=None,
        view_count=None,
        follower_count=None,
        following_count=None,
        url="https://x.com/trader/status/123",
    )

    path = collector.checkpoint()

    assert path == settings.checkpoint_path
    assert path.exists()
    assert '"tweet_id": "123"' in path.read_text()


def test_rate_limit_raised_when_retries_exhausted():
    settings = CollectorSettings(max_retries=0)
    collector = SeleniumCollector(settings=settings)
    collector.metrics.record_scroll(new_tweets=0, duplicates=0)
    collector.metrics.record_scroll(new_tweets=0, duplicates=0)
    collector.metrics.record_scroll(new_tweets=0, duplicates=0)

    with pytest.raises(RateLimited):
        collector.handle_possible_throttling()


def test_collect_resets_run_state_before_browser_work(tmp_path: Path):
    settings = CollectorSettings(checkpoint_path=tmp_path / "checkpoint.json")
    collector = SeleniumCollector(settings=settings)
    collector.collected_tweets["stale"] = Tweet(
        tweet_id="stale",
        username="old",
        display_name="Old",
        timestamp=None,
        content="old",
        hashtags=[],
        mentions=[],
        url="https://x.com/old/status/stale",
    )
    collector.seen_tweet_ids.add("stale")
    collector.metrics.record_scroll(new_tweets=0, duplicates=3)
    collector.retry_attempts = 2

    def fail_initialize() -> None:
        raise RuntimeError("stop after reset")

    collector.initialize = fail_initialize  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        collector.collect("NIFTY", limit=1)

    assert collector.collected_tweets == {}
    assert collector.seen_tweet_ids == set()
    assert collector.metrics.total_scrolls == 0
    assert collector.retry_attempts == 0


def test_bounded_wait_clamps_invalid_ranges():
    sleeps: list[float] = []
    collector = SeleniumCollector(settings=CollectorSettings(), sleeper=sleeps.append)

    collector._bounded_wait(5.0, 1.0)

    assert len(sleeps) == 1
    assert sleeps[0] >= 5.0


def test_hashtag_extraction_supports_unicode_words():
    collector = SeleniumCollector(settings=CollectorSettings())

    assert collector.extract_hashtags("#NIFTY #निफ्टी #சந்தை") == ["NIFTY", "निफ्टी", "சந்தை"]


class _NoTweetTextArticle:
    text = "username\nnot actual tweet content\n1 like"

    def find_elements(self, by: object, selector: str):
        return []


def test_missing_tweet_text_returns_empty_content():
    collector = SeleniumCollector(settings=CollectorSettings())

    assert collector._extract_content(_NoTweetTextArticle()) == ""
