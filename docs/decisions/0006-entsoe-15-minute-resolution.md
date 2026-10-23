# ADR 0006: Handling ENTSO-E's PT15M day-ahead price resolution

## Context
With the ENTSO-E API token finally obtained (see
[ADR 0001](0001-entsoe-day-ahead-prices.md)), running `uv run warehouse backfill`
against the real API for the first time raised
`EntsoeError: No hourly (PT60M) price points found in ENTSO-E response`.
`parse_day_ahead_prices` only accepted `<resolution>PT60M</resolution>` periods;
every other period was silently skipped.

Probing the real API directly (raw XML, no parsing) showed why: French day-ahead
prices are `PT60M` through 2025-09-30 and `PT15M` from 2025-10-01 onward — ENTSO-E's
EU-wide rollout of the 15-minute Market Time Unit. Since the backfill window
(2024-02-01 through today) spans the cutover, every chunk touching the recent period
returned only `PT15M` points, so the hourly-only parser found zero usable rows in
those chunks and raised instead of upserting anything.

## Decision
`parse_day_ahead_prices` now accepts both `PT60M` and `PT15M` periods. Each point's
timestamp is floored to the clock hour it falls in, and all points landing in the
same hour are averaged (`groupby("datetime").mean()`) before being upserted. For
`PT60M` periods this is a no-op (one point per hour, mean of one value). For
`PT15M` periods it collapses four 15-minute prices into one hourly mean, keeping
`day_ahead_prices_hourly`'s schema and grain unchanged. This mirrors
`eco2mix.py`'s existing pattern of resampling finer-grained source data to hourly
means, so the warehouse stays hourly-only and consistent across both connectors.

## Alternatives considered
- **Store prices at native (mixed PT60M/PT15M) resolution and add a resolution
  column.** Rejected: no current consumer needs sub-hourly prices, it would make
  `day_ahead_prices_hourly` the only non-hourly table in the warehouse, and it
  would require updating the benchmark's ground-truth SQL and the MCP schema tool
  for a distinction nothing uses.
- **Keep PT60M-only parsing and accept a data gap from 2025-10-01 onward.**
  Rejected: that gap covers nearly all of the benchmark's "most recent" price
  questions, which is exactly the data this connector exists to provide.

## Consequences
- The full backfill (2024-02-01 -> today) now succeeds end to end: 23,462 rows in
  `day_ahead_prices_hourly`, closing the gap tracked in ADR 0001.
- Any future resolution ENTSO-E might introduce (e.g. a further move to PT5M) will
  still raise `EntsoeError` rather than silently averaging something unintended --
  `_MINUTES_PER_POINT` only recognizes `PT60M`/`PT15M` on purpose.
- Re-running the Phase 3 benchmark (ADR 0005) can now exercise `lookup-4` and
  `aggregation-3` against real price data instead of failing cleanly on a missing
  table.
