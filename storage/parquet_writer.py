"""Parquet persistence helpers."""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

LOGGER = logging.getLogger(__name__)


def write_tweets_parquet(frame: pl.DataFrame, path: str | Path) -> Path:
    """Write tweets/signals to Parquet and return the output path."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(output)
    LOGGER.info("event=parquet_written path=%s rows=%s columns=%s", output, frame.height, len(frame.columns))
    return output
