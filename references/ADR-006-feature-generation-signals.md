# ADR-006: Feature Generation and Composite Signal Design

## Status

Accepted

## Context

The project needs to transform unstructured market discussions into structured research signals. The goal is not to produce trading recommendations, but to demonstrate a scalable feature-generation layer that can later be validated against market returns.

The feature layer must work on small sample data for deterministic testing while remaining suitable for larger collected datasets.

## Decision

The pipeline implements lightweight feature generation in `signals/features.py` and aggregation in `signals/aggregation.py`.

Tweet-level features include:

* lightweight TF-IDF term features derived from normalized text,
* engagement score using replies, retweets, likes, and log-scaled views,
* recency decay using a configurable half-life style decay,
* lexical sentiment proxy based on small market-specific positive and negative term sets,
* directional composite signal combining lexical sentiment, log-scaled engagement, and recency.

Aggregated features include time-bucket summaries of:

* tweet count,
* mean engagement score,
* mean composite signal,
* summed composite signal,
* composite signal standard deviation,
* mean recency decay,
* mean lexical sentiment.

The output is written to Parquet and visualized only after aggregation to keep plotting memory usage low.

## Rationale

TF-IDF is simple, explainable, and deterministic. It avoids introducing heavy model dependencies while still creating useful text-derived features.

Engagement weighting reflects that market discussions with replies, retweets, likes, and views may carry more attention than isolated posts. Log-scaling views prevents high-view posts from dominating excessively.

Recency decay reflects that market discussions lose relevance over time. The composite signal preserves direction: positive values indicate bullish lexical pressure, negative values indicate bearish lexical pressure, and values near zero indicate neutral or weak directional pressure.

Aggregation before visualization supports large datasets because charts use compact time-bucketed data instead of raw tweet-level records.

## Consequences

Benefits:

* explainable feature generation,
* deterministic behavior,
* no heavyweight ML dependency,
* low-memory visualization path,
* ready for future validation against market returns.

Trade-offs:

* TF-IDF is lexical, not semantic,
* sentiment proxy is intentionally simple,
* composite signal is a directional research feature, not a prediction,
* predictive performance is not claimed in this assignment scope.

## Validation

Tests cover:

* TF-IDF feature creation,
* engagement score creation,
* recency decay creation,
* composite signal creation,
* time-bucket aggregation,
* low-memory plot generation from aggregated data.
