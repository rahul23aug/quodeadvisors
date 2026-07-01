# ADR-005: Data Cleaning and Normalization Strategy

## Status

Accepted

## Context

The source data is unstructured social-media text from X/Twitter. It may contain emojis, inconsistent whitespace, URLs, mixed casing, hashtags, mentions, punctuation, and Indian-language Unicode text.

Downstream processing requires deterministic, structured records that can be deduplicated, stored, featurized, and aggregated consistently. The cleaning layer must avoid destroying useful market terms while still reducing noisy text variance.

## Decision

The pipeline uses a dedicated cleaning stage in `processor/cleaner.py` before deduplication, storage, or signal generation.

The cleaner performs:

* Unicode normalization using NFKC.
* URL removal.
* whitespace normalization.
* lowercasing for normalized text.
* lightweight symbol filtering while preserving market-relevant symbols such as `#`, `@`, `%`, `$`, `₹`, `+`, and `-`.
* normalized hashtag and mention lists.
* timestamp parsing into UTC-aware datetimes.
* safe integer normalization for engagement counters.
* source metadata propagation from `CollectorResult`.

The raw tweet content is preserved separately from `content_clean` so downstream users can audit transformations.

## Rationale

This approach separates ingestion from normalization and makes the pipeline source-neutral. Whether records come from Selenium or sample JSONL, downstream stages receive the same cleaned schema.

The cleaning logic is intentionally lightweight. It is sufficient for deterministic feature engineering and storage without introducing large NLP dependencies or opaque transformations.

Preserving both raw and cleaned text supports auditability. If a signal appears suspicious, the original tweet text remains available for inspection.

## Consequences

Benefits:

* deterministic text normalization,
* Unicode-aware processing,
* stable downstream schema,
* easier Parquet persistence,
* source-independent processing,
* auditable raw-vs-cleaned text.

Trade-offs:

* this is not a full multilingual NLP pipeline,
* sarcasm and semantic nuance are not modeled,
* language detection is not implemented,
* advanced tokenization can be added later if needed.

## Validation

Tests cover:

* Unicode whitespace and emoji normalization,
* hashtag and mention normalization,
* `CollectorResult` to Polars DataFrame conversion,
* preservation of source metadata,
* Parquet round-trip compatibility.
