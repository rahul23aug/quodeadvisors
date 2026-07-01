# Architecture

The system is organized as a source-neutral market intelligence pipeline. Collectors produce a common `CollectorResult`, and all downstream stages operate only on normalized records.

```mermaid
flowchart TD
    A[CLI / main.py] --> B[SourceOrchestrator]
    B --> C[SeleniumCollector<br/>Best-effort live X source]
    B --> D[FallbackSampleCollector<br/>Local JSONL sample source]
    C --> E{CollectorStatus}
    E -->|SUCCESS / PARTIAL| F[CollectorResult]
    E -->|THROTTLED / LOGIN_REQUIRED / FAILED| D
    D --> F
    F --> G[Clean + normalize]
    G --> H[Hash dedupe]
    H --> I[Feature generation]
    I --> J[Aggregation]
    I --> K[tweets_features.parquet]
    J --> L[signals_aggregated.parquet]
    J --> M[composite_signal.png]
```

## Key Design Boundary

`SourceOrchestrator` is the main resilience boundary. It turns live-source failures into normal pipeline states, allowing downstream cleaning, storage, feature generation, and visualization code to remain independent of Selenium and X/Twitter behavior.
