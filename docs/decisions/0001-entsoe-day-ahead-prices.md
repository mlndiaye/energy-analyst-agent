# ADR 0001: ENTSO-E as the day-ahead price source

## Context
Phase 1's design (docs/superpowers/specs/2026-10-20-warehouse-mcp-design.md) named
the ENTSO-E Transparency Platform as the candidate source for French day-ahead spot
prices, explicitly unverified pending real API access.

## Decision
ENTSO-E's Transparency Platform (A44 Publication_MarketDocument) is implemented as
the day-ahead price connector (`src/eaa/ingestion/entsoe.py`), against the publicly
documented schema. **Real-API verification is still pending** — it requires a human
to register an account at https://transparency.entsoe.eu and request a security
token by email (turnaround: minutes to days), which did not happen during automated
implementation. Until that verification happens, treat `tests/fixtures/entsoe_sample.xml`
and the parsing XPath expressions in `parse_day_ahead_prices` as unverified against
reality, even though all current tests pass against the documented-schema fixture.

**Before trusting this connector against production data:**
1. Obtain an `ENTSOE_API_TOKEN` (see above) and set it in `.env`.
2. Run: `uv run python -c "from datetime import date; from eaa.ingestion.entsoe import fetch_day_ahead_prices; print(fetch_day_ahead_prices(date(2026, 1, 1), date(2026, 1, 2)))"`.
3. If it raises `xml.etree.ElementTree.ParseError` or `entsoe.EntsoeError`, capture the
   real response text, replace `tests/fixtures/entsoe_sample.xml` with it, and adjust
   `parse_day_ahead_prices`'s XPath expressions to match the real structure.
4. Update this ADR's Decision/Consequences sections with the actual outcome once
   verified.

## Alternatives considered
- RTE's own data portal: no equivalent free day-ahead price dataset found via ODRÉ.
- Scraping the EPEX Spot public results page: rejected — fragile, no stable API.

## Consequences
Real-API verification is a blocking prerequisite before this connector is used for
anything beyond unit tests against the documented-schema fixture. The `warehouse`
table `day_ahead_prices_hourly` will remain empty until `backfill_into`/`refresh_into`
are actually run against live, verified data.
