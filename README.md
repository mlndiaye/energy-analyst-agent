# energy-analyst-agent
LLM agent answering analytical questions on the French power system using SQL, forecasting and weather tools. Evaluated on a custom benchmark for accuracy, tool use, cost and latency.

See [`docs/superpowers/specs/`](docs/superpowers/specs/) for design specs (one per
phase) and [`docs/decisions/`](docs/decisions/) for ADRs.

## Status

**Phase 1 — shipped**: a DuckDB data warehouse (consumption, production mix by
source, day-ahead spot prices — RTE éCO2mix + ENTSO-E) and an MCP server exposing
it, plus project 1's forecasting API (`france-electricity-forecasting`), as four
tools (`get_schema`, `run_sql_query`, `get_latest_forecast`, `get_forecast_history`).
All code is built and tested (49 tests); the éCO2mix connector is verified against
the real API, but the ENTSO-E day-ahead price connector is still pending real-API
verification (requires an API token requested by email — see
[ADR 0001](docs/decisions/0001-entsoe-day-ahead-prices.md)).

**Phase 2 — shipped**: a LangGraph ReAct agent (Claude by default) using Phase 1's MCP
server as tools, with local SQLite conversation memory, served over a FastAPI endpoint
(`POST /ask`) and an interactive CLI (`uv run eaa-agent`). All code is built and tested
(67 tests). A real end-to-end Claude verification (actual tool calls, multi-turn memory,
`/ask` over HTTP) is still pending an `ANTHROPIC_API_KEY` — no key is configured in this
environment, so this remains an open verification gap, the same way Phase 1's ENTSO-E
connector is pending real-API verification (see
[ADR 0001](docs/decisions/0001-entsoe-day-ahead-prices.md)).

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

## Running the agent (Phase 2)

Three processes, three ports: project 1's forecasting API (8000, run separately from
that project), this project's MCP server (8001), and either the agent CLI or its API (8002).

```bash
uv run eaa-mcp-server &          # port 8001

uv run eaa-agent                  # interactive CLI, Ctrl+D to quit
# or:
uv run uvicorn eaa.agent.api:app --port 8002 &
curl -X POST http://127.0.0.1:8002/ask -H "Content-Type: application/json" \
  -d '{"question": "What was yesterday'"'"'s consumption?"}'
```

Requires `ANTHROPIC_API_KEY` in `.env` (see `.env.example`). **Not yet verified against
a real Claude call in this environment** — no `ANTHROPIC_API_KEY` is configured here, so
the agent, memory and `/ask` endpoint are covered by the unit/integration test suite
(mocked LLM calls) but not by an actual end-to-end run. Before relying on this for a
live demo, run it once with a real key and confirm: tool calls show up in the trace
(no hallucinated numbers), multi-turn memory holds across turns, and `/ask` returns a
non-empty `tool_calls` array.
