# ADR-004: Unicode-Aware Hashtag Normalization

## Status

Accepted

## Context

The project processes Indian stock-market discussions from X/Twitter. These discussions may include hashtags written in English as well as Indian-language scripts.

A common hashtag extraction pattern is:

```python
r"(?<!\w)#([\w]+)"
```

This works for ASCII hashtags such as `#NIFTY` and `#banknifty`, but Python's `\w` handling can split Indian-language words when combining marks are present. For example, hashtags such as `#निफ्टी` may be partially extracted instead of preserved as a complete token.

A broader whitespace-delimited hashtag extraction pattern preserves these Unicode hashtags, but it may also capture trailing punctuation:

```text
#nifty50,
#banknifty.
#निफ्टी,
```

## Decision

The collector will use Unicode-preserving hashtag extraction and then strip trailing edge punctuation.

The implementation intentionally avoids relying only on `\w` for hashtag token boundaries. Instead, it captures the hashtag token up to whitespace or another entity marker, then removes punctuation such as commas and periods from the token edge.

This preserves Indian-language hashtags while still normalizing common punctuation cases.

Examples:

```text
#nifty50,   -> nifty50
#banknifty. -> banknifty
#निफ्टी,    -> निफ्टी
```

## Rationale

The assignment explicitly includes Indian-language content. Correctly preserving Unicode market terms is more important than using a narrower ASCII-oriented regex.

The chosen approach balances:

* Unicode support
* simple implementation
* deterministic normalization
* no dependency on heavy NLP libraries
* predictable handling of punctuation from normal social-media writing

## Consequences

Benefits:

* Indian-language hashtags are preserved.
* ASCII hashtags with punctuation are normalized correctly.
* The logic remains lightweight and testable.

Trade-offs:

* The extractor is still a lightweight tokenizer, not a full multilingual NLP parser.
* Some unusual punctuation or zero-width Unicode edge cases may require additional normalization later.

## Validation

Regression tests cover:

* ASCII hashtags
* Indian-language Unicode hashtags
* trailing punctuation on both ASCII and Unicode hashtags
