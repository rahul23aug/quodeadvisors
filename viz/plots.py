"""Low-memory visualization utilities for aggregated signals."""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

LOGGER = logging.getLogger(__name__)


def plot_signal_timeseries(aggregated: pl.DataFrame, path: str | Path) -> Path:
    """Plot aggregated composite signal over time without loading raw tweet text."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 4))
    if aggregated.is_empty():
        ax.set_title("Composite Signal: no data")
    else:
        x = aggregated.get_column("timestamp").to_list()
        y = aggregated.get_column("composite_signal_mean").to_list()
        ax.plot(x, y, linewidth=1.5)
        ax.set_title("Engagement-Weighted Recency-Decayed Signal")
        ax.set_xlabel("Time")
        ax.set_ylabel("Composite Signal Mean")
        fig.autofmt_xdate()
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=120)
    plt.close(fig)
    LOGGER.info("event=plot_written path=%s rows=%s", output, aggregated.height)
    return output
