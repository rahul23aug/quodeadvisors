import json
from datetime import datetime, timezone
from pathlib import Path

from collector.base import BaseCollector
from collector.fallback_sample_collector import FallbackSampleCollector
from collector.models import CollectorResult, CollectorStatus, Tweet
from collector.orchestrator import SourceOrchestrator
from collector.selenium_collector import SeleniumCollector
from config.settings import CollectorSettings, ThrottlingSettings


class StaticResultCollector(BaseCollector):
    def __init__(self, result: CollectorResult):
        self.result = result

    def initialize(self) -> None:
        return None

    def collect(self, query: str, limit: int) -> list[Tweet]:
        return self.result.records[:limit]

    def collect_result(self, query: str, limit: int) -> CollectorResult:
        return self.result

    def checkpoint(self) -> Path:
        return Path('/tmp/static-result-checkpoint.json')

    def shutdown(self) -> None:
        return None


def make_tweet(tweet_id: str = '1') -> Tweet:
    return Tweet(
        tweet_id=tweet_id,
        username='sample',
        display_name='Sample',
        timestamp='2026-07-01T00:00:00Z',
        content='NIFTY sample tweet',
        hashtags=['NIFTY'],
        mentions=[],
        reply_count=0,
        retweet_count=0,
        like_count=0,
        view_count=0,
        follower_count=10,
        following_count=5,
        url=f'https://x.com/sample/status/{tweet_id}',
    )


def test_collector_result_dataclass_roundtrip():
    started = datetime.now(timezone.utc)
    ended = datetime.now(timezone.utc)
    result = CollectorResult(
        records=[make_tweet('10')],
        status=CollectorStatus.SUCCESS,
        started_at=started,
        ended_at=ended,
        error_message=None,
        source_name='test',
    )

    payload = result.to_dict()

    assert payload['status'] == 'SUCCESS'
    assert payload['source_name'] == 'test'
    assert payload['records'][0]['tweet_id'] == '10'


def test_selenium_collect_result_returns_throttled_without_raising(tmp_path: Path):
    settings = CollectorSettings(
        checkpoint_path=tmp_path / 'checkpoint.json',
        max_retries=0,
        throttling=ThrottlingSettings(max_consecutive_empty_scrolls=2),
    )
    collector = SeleniumCollector(settings=settings)
    collector.metrics.record_scroll(new_tweets=0, duplicates=0)
    collector.metrics.record_scroll(new_tweets=0, duplicates=0)

    result = collector.collect_result('NIFTY', limit=1)

    assert result.status == CollectorStatus.THROTTLED
    assert result.records == []
    assert result.source_name == 'selenium_x'
    assert settings.checkpoint_path.exists()


def test_fallback_sample_collector_reads_jsonl(tmp_path: Path):
    sample_path = tmp_path / 'sample_tweets.jsonl'
    sample_path.write_text(json.dumps(make_tweet('1').to_dict()) + '\n', encoding='utf-8')
    collector = FallbackSampleCollector(sample_path=sample_path)

    result = collector.collect_result('ignored', limit=10)

    assert result.status == CollectorStatus.SUCCESS
    assert result.source_name == 'sample_jsonl'
    assert len(result.records) == 1
    assert result.records[0].tweet_id == '1'


def test_source_orchestrator_falls_back_on_throttled(tmp_path: Path):
    sample_path = tmp_path / 'sample_tweets.jsonl'
    sample_path.write_text(json.dumps(make_tweet('sample-1').to_dict()) + '\n', encoding='utf-8')
    primary = StaticResultCollector(
        CollectorResult(
            records=[],
            status=CollectorStatus.THROTTLED,
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            error_message='empty scrolls',
            source_name='selenium_x',
        )
    )
    fallback = FallbackSampleCollector(sample_path=sample_path)
    orchestrator = SourceOrchestrator(primary=primary, fallback=fallback)

    result = orchestrator.collect('NIFTY', limit=5)

    assert result.status == CollectorStatus.SUCCESS
    assert result.source_name == 'sample_jsonl'
    assert result.records[0].tweet_id == 'sample-1'


def test_source_orchestrator_falls_back_on_zero_record_throttled_result(tmp_path: Path):
    sample_path = tmp_path / 'sample_tweets.jsonl'
    sample_path.write_text(json.dumps(make_tweet('fallback-zero').to_dict()) + '\n', encoding='utf-8')
    primary = StaticResultCollector(
        CollectorResult(
            records=[],
            status=CollectorStatus.THROTTLED,
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            error_message='source returned no records',
            source_name='selenium_x',
        )
    )

    result = SourceOrchestrator(primary=primary, fallback=FallbackSampleCollector(sample_path)).collect('NIFTY', 5)

    assert result.source_name == 'sample_jsonl'
    assert result.records[0].tweet_id == 'fallback-zero'
