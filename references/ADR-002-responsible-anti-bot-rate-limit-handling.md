ADR-002: Responsible Handling of Anti-Bot and Rate-Limit Constraints

Status

Accepted

Context

The assignment requires collecting recent Indian stock-market discussions from X/Twitter without using paid APIs or the official Twitter API. It also asks the system to handle rate limiting and anti-bot constraints creatively while producing a robust, production-shaped data pipeline.  

Modern public platforms may restrict automated access through login walls, throttling, dynamic rendering, delayed loading, empty responses, or temporary blocks. A naïve scraper that repeatedly refreshes pages or scrolls aggressively is likely to fail and may create unnecessary load.

Decision

The system will implement defensive and respectful scraping controls, not stealth-based evasion.

The scraper will use browser automation only for publicly accessible pages and will include:

* configurable request pacing
* randomized but bounded wait times
* exponential backoff on failures
* checkpointing and resumability
* duplicate detection
* ingestion-rate monitoring
* graceful shutdown when throttling is suspected
* partial-result persistence to Parquet

The system will not implement fingerprint spoofing, credential abuse, CAPTCHA bypassing, proxy rotation, or techniques intended to defeat platform security controls.

The collector may optionally use a locally authenticated browser profile to access content available to the authenticated user. The implementation does not manipulate authentication tokens, extract credentials, or attempt to bypass authentication mechanisms.

Authentication through a legitimate user browser session is supported, but credential extraction, token injection, and other authentication manipulation techniques are intentionally excluded.

Rationale

The objective is to demonstrate resilient data engineering under real-world constraints, not to bypass a platform’s protections.

A production-quality data collector should recognize when source access is degraded and respond safely by slowing down, checkpointing, logging the issue, and exiting or retrying later.

This approach demonstrates:

* operational maturity
* respect for external systems
* fault tolerance
* recoverability
* realistic production behavior

Anti-Bot Handling Strategy

The scraper will treat the following as throttling or degraded-source signals:

* repeated empty result batches
* no new tweets after several scroll attempts
* sudden drop in tweets collected per minute
* login wall or unavailable-content detection
* repeated navigation timeouts
* duplicate-heavy feed responses

When detected, the collector will:

1. persist all collected records,
2. write a structured warning log,
3. update checkpoint state,
4. pause with exponential backoff,
5. stop safely if the configured retry limit is exceeded.

Consequences

Benefits

* Avoids brittle evasion logic.
* Produces a safer and more professional implementation.
* Makes failure modes observable.
* Preserves partial progress under constraints.
* Demonstrates production judgment.

Trade-offs

* The scraper may collect fewer tweets if the platform restricts access.
* Collection speed is intentionally limited.
* Some manual setup may be required if public search access is unavailable.

Mitigation

The pipeline is designed so that collection, processing, storage, and analysis are decoupled. If live scraping is limited, previously collected sample data can still be processed through the cleaning, deduplication, signal generation, storage, and visualization layers
