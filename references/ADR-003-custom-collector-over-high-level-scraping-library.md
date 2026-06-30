ADR-003: Custom Collector over High-Level Scraping Library

Status

Accepted

Context

The assignment evaluates not only the ability to collect data, but also software engineering practices, system design, scalability, and problem-solving under real-world constraints. The data collection component is therefore considered part of the engineering solution rather than an implementation detail.  

Several third-party libraries, such as Scweet, provide high-level wrappers around browser automation and expose tweet collection through a minimal API.

Decision

A custom collector will be implemented using Selenium instead of relying on a high-level scraping library.

Browser automation will be abstracted behind a collector interface so that the scraping implementation can be replaced without affecting downstream processing.

Rationale

Using a custom collector provides explicit control over:

* extraction logic
* retry behaviour
* checkpointing
* logging
* rate limiting
* throttling detection
* data validation
* metrics collection
* future extensibility

It also makes these implementation details visible for review rather than encapsulating them inside a third-party dependency.

The objective is not to reproduce the functionality of existing libraries, but to demonstrate engineering decisions that are directly relevant to production data collection systems.

Consequences

Benefits

* Full visibility into collection behaviour.
* Easier debugging and observability.
* Better separation of concerns.
* Collector implementation can evolve independently.
* Demonstrates engineering decisions rather than library usage.

Trade-offs

* Increased implementation effort.
* Additional maintenance responsibility.
* Browser automation changes may require updates to the collector.

Mitigation

The collector is isolated behind a well-defined interface, allowing alternative implementations or libraries to be substituted with minimal changes to the remainder of the pipeline.
