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

**Phase 2 — shipped, verified against a real LLM call**: a LangGraph ReAct agent
(Gemini by default, via Google GenAI — swapped in for Claude for budget reasons, see
[ADR 0003](docs/decisions/0003-gemini-instead-of-claude.md)) using Phase 1's MCP
server as tools, with local SQLite conversation memory, served over a FastAPI endpoint
(`POST /ask`) and an interactive CLI (`uv run eaa-agent`). All code is built and tested
(99 tests). A real end-to-end run (real Gemini call, real tool calls over the real MCP
server) surfaced two bugs invisible to the mocked test suite — a sync `agent.invoke()`
can't call the MCP tools (coroutine-only) or use the sync `SqliteSaver` checkpointer —
fixed by switching the whole call chain to async (see
[ADR 0004](docs/decisions/0004-async-agent-invocation.md)). After the fix, a real run
correctly called `get_schema` and `get_latest_forecast` and produced a coherent answer,
including a clean "forecast unavailable" when a tool call failed, rather than a
hallucinated number.

**Phase 3 — shipped, run once for real (partial data)**: a custom benchmark comparing
Gemini 3.5 Flash against two local Ollama models (`llama3.2`, `llama3.1:8b`) on
accuracy, tool use, cost, and latency over 15 questions (5 lookup, 5 aggregation, 5
multi-tool), with Langfuse tracing (verified working against the real cloud
dashboard). All code is built and tested (107 tests). A real run against a
partially-backfilled warehouse (éCO2mix only -- ENTSO-E day-ahead prices are still
blocked on Phase 1's token, see
[ADR 0001](docs/decisions/0001-entsoe-day-ahead-prices.md)) surfaced three real bugs
invisible to the mocked suite -- a provider rate limit crashing the whole run, a
ground-truth query picking up a not-yet-reported NULL hour, and a scoring regex
grabbing the wrong number out of a verbose answer -- all fixed, plus a retry/backoff
middleware and a report section explaining how to read a 0% row (see
[ADR 0005](docs/decisions/0005-first-benchmark-run-fixes.md)). After the fixes,
accuracy is still 0% for every model in this partial run, for two distinct and
diagnosed reasons: Gemini's free-tier quota (5 req/min) is too tight for even one
model's 15-question run, and the two Ollama models guess at the SQL schema instead of
calling `get_schema` first -- a genuine capability gap, not a bug. See
`docs/benchmark_report.md` for the full report. A fair, complete run still needs the
ENTSO-E token, project 1's forecasting API actually running, and either a paid Gemini
key or a slower pace to clear free-tier quota windows.

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

Requires `GOOGLE_API_KEY` in `.env` (see `.env.example` — a free-tier key from
[Google AI Studio](https://aistudio.google.com/apikey) works). Verified against a real
Gemini call: tool calls show up correctly, and a failed tool call produces a clean
"data wasn't available" answer instead of a hallucinated number. Multi-turn memory and
the `/ask` HTTP path are still only covered by the mocked test suite, not a live run —
worth re-confirming before a live demo.

## Running the benchmark (Phase 3)

Requires `eaa-mcp-server` running (port 8001), a populated `warehouse.duckdb`
(`uv run warehouse backfill`), `GOOGLE_API_KEY` and `LANGFUSE_PUBLIC_KEY`/
`LANGFUSE_SECRET_KEY` in `.env`, and Ollama running locally with `llama3.2` and
`llama3.1:8b` pulled (`ollama pull llama3.2 && ollama pull llama3.1:8b`).

```bash
uv run eaa-mcp-server &
uv run eaa-benchmark
```

Writes `docs/benchmark_report.md` (committed) and `benchmark_results.json` (local,
gitignored raw results, including the full error/tool-call trace per run). **Run once
for real**, against a warehouse backfilled from éCO2mix only (no ENTSO-E day-ahead
prices yet) and `FORECAST_API_URL` pointed at an unreachable host (project 1's
forecasting API wasn't running that round) — see
[ADR 0005](docs/decisions/0005-first-benchmark-run-fixes.md) for what that run found
and fixed. `lookup-4`, `aggregation-3` (price questions) and all 5 `multi_tool`
questions fail cleanly on those known gaps, not silently. Once the ENTSO-E token
closes the data gap and project 1's API is reachable, re-run the benchmark and commit
the regenerated `docs/benchmark_report.md` for a complete, fair comparison.
