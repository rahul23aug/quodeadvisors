# Architecture

The system is organized as a source-neutral market intelligence pipeline. Collectors produce a common `CollectorResult`, and all downstream stages operate only on normalized records.

```mermaid
flowchart TD
    A[CLI / main.py] --> B[SourceOrchestrator]

    B --> C[SeleniumCollector\nBest-effort live X source]
    B --> D[FallbackSampleCollector\nLocal JSONL sample source]

    C --> E[CollectorResult\nstatus + records + metadata]
    D --> E

    E --> F[processor.cleaner\nUnicode normalization\nentity normalization]
    F --> G[processor.dedupe\nhash-based O(1) dedupe]
    G --> H[signals.features\nTF-IDF terms\nengagement score\nrecency decay\ncomposite signal]
    H --> I[signals.aggregation\ntime-bucket aggregation]

    H --> J[storage.parquet_writer\ntweets_features.parquet]
    I --> K[storage.parquet_writer\nsignals_aggregated.parquet]
    I --> L[viz.plots\ncomposite_signal.png]

    C -. degraded source .-> M[THROTTLED / LOGIN_REQUIRED / FAILED]
    M -. fallback .-> D
```

## Key Design Boundary

`SourceOrchestrator` is the main resilience boundary. It turns live-source failures into normal pipeline states, allowing downstream cleaning, storage, feature generation, and visualization code to remain independent of Selenium and X/Twitter behavior.
