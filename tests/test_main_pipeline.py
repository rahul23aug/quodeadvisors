import argparse
from datetime import datetime, timezone
from pathlib import Path

import pytest

import main as pipeline_main
from collector.models import CollectorResult, CollectorStatus, Tweet


class DummyCollector:
    def __init__(self) -> None:
        self.shutdown_called = False

    def collect_result(self, query: str, limit: int) -> CollectorResult:
        now = datetime.now(timezone.utc)
        return CollectorResult(
            records=[
                Tweet(
                    tweet_id="1",
                    username="dummy",
                    display_name="Dummy",
                    timestamp=now.isoformat(),
                    content="NIFTY bullish #NIFTY",
                    hashtags=["NIFTY"],
                    mentions=[],
                    reply_count=1,
                    retweet_count=1,
                    like_count=1,
                    view_count=10,
                    follower_count=10,
                    following_count=5,
                    url="https://x.com/dummy/status/1",
                )
            ],
            status=CollectorStatus.SUCCESS,
            started_at=now,
            ended_at=now,
            error_message=None,
            source_name="dummy",
        )

    def shutdown(self) -> None:
        self.shutdown_called = True


class FailingOrchestrator:
    def __init__(self, primary, fallback) -> None:
        self.primary = primary
        self.fallback = fallback

    def collect(self, query: str, limit: int) -> CollectorResult:
        raise RuntimeError("boom")


def args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        query="NIFTY",
        limit=1,
        output_dir=str(tmp_path / "out"),
        sample_path="data/input/sample_tweets.jsonl",
        checkpoint_path=str(tmp_path / "checkpoint.json"),
        aggregate_every="1h",
        headless=True,
        chrome_profile_path=None,
        chrome_binary_path=None,
        chrome_driver_path=None,
        collection_timeout_seconds=1.0,
        max_retries=0,
        max_empty_scrolls=1,
    )


def test_run_pipeline_shuts_down_primary_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    primary = DummyCollector()
    monkeypatch.setattr(pipeline_main, "build_primary_collector", lambda parsed: primary)
    monkeypatch.setattr(pipeline_main, "SourceOrchestrator", FailingOrchestrator)

    with pytest.raises(RuntimeError):
        pipeline_main.run_pipeline(args(tmp_path))

    assert primary.shutdown_called is True


def test_run_pipeline_logs_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture):
    primary = DummyCollector()
    monkeypatch.setattr(pipeline_main, "build_primary_collector", lambda parsed: primary)

    with caplog.at_level("INFO"):
        paths = pipeline_main.run_pipeline(args(tmp_path))

    assert primary.shutdown_called is True
    assert set(paths) == {"tweets", "aggregated", "plot"}
    assert "event=pipeline_output name='tweets'" in caplog.text
    assert "elapsed_seconds=" in caplog.text
