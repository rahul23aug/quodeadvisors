"""Low-memory signal aggregation helpers."""

from __future__ import annotations

import logging

import polars as pl

LOGGER = logging.getLogger(__name__)


def aggregate_signals(frame: pl.DataFrame, every: str = "1h") -> pl.DataFrame:
    """Aggregate tweet-level signals into time buckets for plotting/storage."""
    if frame.is_empty():
        return pl.DataFrame()
    aggregated = (
        frame.sort("timestamp")
        .group_by_dynamic("timestamp", every=every)
        .agg(
            pl.len().alias("tweet_count"),
            pl.col("engagement_score").mean().alias("engagement_score_mean"),
            pl.col("composite_signal").mean().alias("composite_signal_mean"),
            pl.col("composite_signal").sum().alias("composite_signal_sum"),
            pl.col("lexical_sentiment").mean().alias("lexical_sentiment_mean"),
        )
        .sort("timestamp")
    )
    LOGGER.info("event=signals_aggregated input_rows=%s output_rows=%s every=%s", frame.height, aggregated.height, every)
    return aggregated
