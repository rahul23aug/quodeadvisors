"""Lightweight text and market-discussion signal features."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from datetime import datetime, timezone

import polars as pl

LOGGER = logging.getLogger(__name__)
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{1,}")


def add_signal_features(frame: pl.DataFrame, now: datetime | None = None, top_k_terms: int = 25) -> pl.DataFrame:
    """Add lightweight TF-IDF, engagement, recency, and composite signal columns."""
    if frame.is_empty():
        return frame
    now = _as_utc(now or datetime.now(timezone.utc))
    frame = frame.with_columns(
        (
            pl.col("reply_count")
            + pl.col("retweet_count") * 2
            + pl.col("like_count")
            + (pl.col("view_count") + 1).log() * 0.25
        ).alias("engagement_score"),
        pl.col("content_clean").map_elements(_sentiment_score, return_dtype=pl.Float64).alias("lexical_sentiment"),
    )
    frame = _add_recency_decay(frame, now)
    frame = _add_tfidf_features(frame, top_k_terms=top_k_terms)
    frame = frame.with_columns(
        (
            pl.col("lexical_sentiment")
            * pl.col("engagement_score").log1p()
            * pl.col("recency_decay")
        ).alias("composite_signal")
    )
    LOGGER.info("event=signal_features_added rows=%s columns=%s", frame.height, len(frame.columns))
    return frame


def _add_recency_decay(frame: pl.DataFrame, now: datetime, half_life_hours: float = 12.0) -> pl.DataFrame:
    age_hours = (pl.lit(now) - pl.col("timestamp")).dt.total_seconds() / 3600.0
    return frame.with_columns(
        pl.when(pl.col("timestamp").is_null())
        .then(0.0)
        .otherwise((-age_hours * math.log(2) / half_life_hours).exp())
        .clip(0.0, 1.0)
        .alias("recency_decay")
    )


def _add_tfidf_features(frame: pl.DataFrame, top_k_terms: int) -> pl.DataFrame:
    docs = frame.get_column("content_clean").fill_null("").to_list()
    tokenized = [_tokens(doc) for doc in docs]
    doc_count = max(len(tokenized), 1)
    document_frequency: Counter[str] = Counter()
    corpus_frequency: Counter[str] = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))
        corpus_frequency.update(tokens)
    terms = [term for term, _ in corpus_frequency.most_common(top_k_terms)]
    columns: list[pl.Series] = []
    for term in terms:
        idf = math.log((1 + doc_count) / (1 + document_frequency[term])) + 1.0
        values = []
        for tokens in tokenized:
            if not tokens:
                values.append(0.0)
                continue
            tf = tokens.count(term) / len(tokens)
            values.append(tf * idf)
        columns.append(pl.Series(f"tfidf_{term}", values, dtype=pl.Float64))
    if not columns:
        return frame
    return frame.hstack(columns)


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    return TOKEN_RE.findall(text.lower())


def _sentiment_score(text: str | None) -> float:
    tokens = set(_tokens(text))
    positive = {
        "bull",
        "bullish",
        "breakout",
        "rally",
        "long",
        "buy",
        "support",
        "upside",
        "bounce",
        "reversal",
        "gapup",
    }
    negative = {
        "bear",
        "bearish",
        "breakdown",
        "sell",
        "short",
        "resistance",
        "crash",
        "downside",
        "gapdown",
        "dump",
    }
    return float(len(tokens & positive) - len(tokens & negative))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
