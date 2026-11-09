Deterministic financial headline matcher
=======================================

Run `python3 demo.py` with Python 3.10 or later. The demo uses synthetic aliases and runs eight checks. The matcher uses only the Python standard library.

Supply an alias index scoped to the article's publication time and relevant market. Each alias has an evidence ID. The matcher prefers the longest token span, preserves collisions and keeps offsets into the original text. Single-token aliases require explicit opt-in. The optional masking function replaces spans with `[ISSUER]`, `[BROKER]` or `[AMBIGUOUS]`, leaving the sentence structure available for inspection.

The rules identify sell-side initiations, upgrades, downgrades and price target changes, including multiple affected issuers. They also cover earnings previews, reported results, comparisons with consensus, guidance, dividends and buybacks, and acquisitions. A short body lead can supply additional name and exchange-qualified ticker hints, wire datelines and issuer announcement candidates.

Treat the output as evidence candidates. Resolve collisions against dated name and listing histories, keep brokers separate from the affected issuers, and retain publication and first-observed clocks independently. A wire dateline supplies day precision. The event expressions focus on English. The included matcher is a standalone extraction of the factory's rules with a masking helper and a coverage-initiation adjustment.
