"""Command-line entrypoint for the downstream tweet processing pipeline."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from collector.fallback_sample_collector import FallbackSampleCollector
from collector.orchestrator import SourceOrchestrator
from collector.selenium_collector import SeleniumCollector
from config.settings import CollectorSettings, ThrottlingSettings
from processor.cleaner import clean_tweets
from processor.dedupe import dedupe_tweets
from signals.aggregation import aggregate_signals
from signals.features import add_signal_features
from storage.parquet_writer import write_tweets_parquet
from viz.plots import plot_signal_timeseries

LOGGER = logging.getLogger(__name__)


def run_pipeline(args: argparse.Namespace) -> dict[str, Path]:
    """Collect, clean, dedupe, featurize, aggregate, persist, and plot tweets."""
    primary = SeleniumCollector(
        settings=CollectorSettings(
            headless=args.headless,
            chrome_profile_path=args.chrome_profile_path,
            chrome_binary_path=args.chrome_binary_path,
            chrome_driver_path=args.chrome_driver_path,
            checkpoint_path=args.checkpoint_path,
            collection_timeout_seconds=args.collection_timeout_seconds,
            max_retries=args.max_retries,
            throttling=ThrottlingSettings(max_consecutive_empty_scrolls=args.max_empty_scrolls),
        )
    )
    fallback = FallbackSampleCollector(sample_path=args.sample_path)
    result = SourceOrchestrator(primary=primary, fallback=fallback).collect(query=args.query, limit=args.limit)

    cleaned = clean_tweets(result)
    deduped = dedupe_tweets(cleaned)
    features = add_signal_features(deduped)
    aggregated = aggregate_signals(features, every=args.aggregate_every)

    output_dir = Path(args.output_dir)
    paths = {
        "tweets": write_tweets_parquet(features, output_dir / "tweets_features.parquet"),
        "aggregated": write_tweets_parquet(aggregated, output_dir / "signals_aggregated.parquet"),
        "plot": plot_signal_timeseries(aggregated, output_dir / "composite_signal.png"),
    }
    LOGGER.info("event=pipeline_completed source=%s status=%s records=%s", result.source_name, result.status.value, len(result.records))
    return paths


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Run the quodeadvisors downstream tweet pipeline")
    parser.add_argument("--query", default="NIFTY", help="X/Twitter search query")
    parser.add_argument("--limit", type=int, default=100, help="Maximum tweets to collect")
    parser.add_argument("--output-dir", default="data/output", help="Output directory")
    parser.add_argument("--sample-path", default="data/input/sample_tweets.jsonl", help="Fallback sample JSONL path")
    parser.add_argument("--checkpoint-path", default="data/checkpoints/x_collector_checkpoint.json", help="Collector checkpoint path")
    parser.add_argument("--aggregate-every", default="1h", help="Polars dynamic aggregation interval")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True, help="Run Chrome headless")
    parser.add_argument("--chrome-profile-path", default=None, help="Optional local Chrome profile path")
    parser.add_argument("--chrome-binary-path", default=None, help="Optional Chrome/Chromium binary path")
    parser.add_argument("--chrome-driver-path", default=None, help="Optional chromedriver path")
    parser.add_argument("--collection-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--max-empty-scrolls", type=int, default=2)
    return parser


def main() -> None:
    """Run CLI pipeline."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()
