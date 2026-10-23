# ADR 0001: ENTSO-E as the day-ahead price source

## Context
Phase 1's design (docs/superpowers/specs/2026-10-20-warehouse-mcp-design.md) named
the ENTSO-E Transparency Platform as the candidate source for French day-ahead spot
prices, explicitly unverified pending real API access.

## Decision
ENTSO-E's Transparency Platform (A44 Publication_MarketDocument) is implemented as
the day-ahead price connector (`src/eaa/ingestion/entsoe.py`), against the publicly
documented schema.

**Real-API verification is done.** The ENTSO-E account's API role was approved and
a `Web API Security Token` generated on 2026-10-23. A full backfill
(`uv run warehouse backfill`, 2024-02-01 through today) ran successfully against the
real API: `day_ahead_prices_hourly` now holds 23,462 rows through 2026-10-23. The
documented A44 schema and `parse_day_ahead_prices`'s XPath expressions matched the
real response as-is, with one real gap found and fixed along the way — ENTSO-E
switched French day-ahead prices from hourly (PT60M) to 15-minute (PT15M)
resolution on 2025-10-01, which the original parser didn't handle. See
[ADR 0006](0006-entsoe-15-minute-resolution.md).

## Alternatives considered
- RTE's own data portal: no equivalent free day-ahead price dataset found via ODRÉ.
- Scraping the EPEX Spot public results page: rejected — fragile, no stable API.

## Consequences
`day_ahead_prices_hourly` is now populated for the full study window, closing the
data gap that `lookup-4`, `aggregation-3` and (indirectly, as one of several tools)
the `multi_tool` benchmark questions depend on (see
[ADR 0005](0005-first-benchmark-run-fixes.md)). A fair benchmark re-run still needs
project 1's forecasting API running and Gemini's free-tier quota addressed.
