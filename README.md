# energy-analyst-agent
LLM agent answering analytical questions on the French power system using SQL, forecasting and weather tools. Evaluated on a custom benchmark for accuracy, tool use, cost and latency.

See [`docs/superpowers/specs/`](docs/superpowers/specs/) for design specs (one per
phase) and [`docs/decisions/`](docs/decisions/) for ADRs.

## Status

**Phase 1 — shipped**: a DuckDB data warehouse (consumption, production mix by
source, day-ahead spot prices — RTE éCO2mix + ENTSO-E) and an MCP server exposing
it, plus project 1's forecasting API (`france-electricity-forecasting`), as four
tools (`get_schema`, `run_sql_query`, `get_latest_forecast`, `get_forecast_history`).
All code is built and tested (47 tests); the éCO2mix connector is verified against
the real API, but the ENTSO-E day-ahead price connector is still pending real-API
verification (requires an API token requested by email — see
[ADR 0001](docs/decisions/0001-entsoe-day-ahead-prices.md)).

**Phase 2 — ahead**: a LangGraph agent (MCP client), served over FastAPI and a CLI.

**Phase 3 — ahead**: a custom benchmark comparing Claude against two local Ollama
models on accuracy, tool use, cost and latency, traced with Langfuse.

## Getting started (Phase 1)

```bash
uv sync --extra dev
cp .env.example .env   # fill in ENTSOE_API_TOKEN (see docs/decisions/0001-entsoe-day-ahead-prices.md)

uv run warehouse backfill   # builds warehouse.duckdb from RTE éCO2mix + ENTSO-E
uv run warehouse refresh    # incremental update

uv run eaa-mcp-server        # serves get_schema / run_sql_query / get_latest_forecast / get_forecast_history
```

Until `ENTSOE_API_TOKEN` is set to a real token, `warehouse backfill` and
`warehouse refresh` exit immediately with a clear `SystemExit` ("Missing required
environment variable(s): ENTSOE_API_TOKEN") — this is expected, not a bug, and is
the current blocker for real-data verification tracked in ADR 0001.

```bash
uv run pytest        # test suite
uv run ruff check .  # lint
```
