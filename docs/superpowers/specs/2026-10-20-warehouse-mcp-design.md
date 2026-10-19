# Design: Phase 1 — Data warehouse and MCP server

## Context

`energy-analyst-agent` is the third project of a three-project portfolio (AI Engineering),
following `france-electricity-forecasting` (ML + MLOps) and `french-business-registry`
(Data Engineering + Big Data). It is an LLM agent that answers analytical questions about
the French power system by querying a data warehouse and calling a forecasting model,
evaluated on a custom benchmark comparing API-based and local models on accuracy, tool
use, cost and latency.

The project splits into three largely independent blocks, each getting its own design
spec written just before it is built — the same approach used for
`french-business-registry`'s step-by-step specs:

- **Phase 1** (this spec): a DuckDB data warehouse and an MCP server exposing it, plus
  the forecasting model of project 1, as tools.
- **Phase 2** (future spec): a LangGraph agent, served over FastAPI and a CLI.
- **Phase 3** (future spec): a custom benchmark, a comparison of Claude vs. two local
  Ollama models on accuracy/tool use/cost/latency, and Langfuse tracing.

```
Phase 1 (this spec)          Phase 2 (future spec)         Phase 3 (future spec)
┌──────────────────┐        ┌──────────────────┐        ┌───────────────────┐
│ DuckDB warehouse  │        │ LangGraph agent   │        │ Custom benchmark   │
│ (consumption,     │◄──MCP──│ (MCP client)      │        │ + Claude vs Ollama │
│  production mix,  │  HTTP  │ FastAPI /ask + CLI│◄───────│ comparison         │
│  day-ahead prices)│        └──────────┬────────┘        │ + Langfuse         │
│                   │                   │                 └───────────────────┘
│ MCP server        │                   │
│ (run_sql_query,   │                   │
│  get_schema,      │                   │
│  get_latest_      │
│  forecast,        │
│  get_forecast_    │
│  history)         │───HTTP──► france-electricity-forecasting API
└───────────────────┘            (/forecast/latest, /forecast/history)
```

## Decision

### Data sources

- **Consumption + production mix by source**: RTE éCO2mix via the ODRÉ API
  (`eco2mix-national-cons-def` + `eco2mix-national-tr`), the same source already used and
  verified by project 1. Production-by-source fields (`nuclear`, `wind`, `solar`,
  `hydro`, `gas`, ...) are part of the same dataset.
- **Day-ahead spot prices**: candidate source is the **ENTSO-E Transparency Platform**
  (free API, token requested by email, document A44 for French day-ahead prices).
  **Not yet verified** — confirming real access and response format is the first
  implementation task, before writing the final connector, the same way project 1's
  ADR 0001 verified weather/consumption data against real API responses rather than
  documentation alone. If ENTSO-E proves impractical (token delay, unusable format), an
  alternative source will be chosen at that point rather than blocking this spec on an
  unverified assumption.

### Why a new connector instead of reusing project 1's code

The éCO2mix connector is rewritten in this repository rather than imported from
`france-electricity-forecasting`. Each portfolio project must be independently
defensible in a 20-30 minute interview; a cross-repo Python import would create a
fragile coupling (install paths, versioning) for a connector small enough (~100 lines)
to rewrite rather than package.

### Warehouse schema

Single DuckDB file (`warehouse.duckdb`), never committed, rebuildable from source APIs —
same rule as raw data in the other two projects.

```sql
consumption_hourly (
    datetime       TIMESTAMP,  -- UTC, hour boundary
    consumption_mw DOUBLE,
    PRIMARY KEY (datetime)
)

production_by_source_hourly (
    datetime       TIMESTAMP,
    source         VARCHAR,    -- 'nuclear', 'wind', 'solar', 'hydro', 'gas', ...
    production_mw  DOUBLE,
    PRIMARY KEY (datetime, source)
)

day_ahead_prices_hourly (
    datetime        TIMESTAMP,
    price_eur_mwh    DOUBLE,
    PRIMARY KEY (datetime)
)
```

- Production mix uses a **long** format (one row per source) rather than one column per
  source: simpler for generic SQL (`GROUP BY source`), and extensible without a schema
  migration if a source is added later.
- Everything is aggregated to **hourly** grain (mean of the underlying 15/30-min points,
  mirroring project 1's approach), so the three tables stay easy to join and compare.
- No calendar dimension for now — none of the chosen benchmark categories (Phase 3) need
  one, and `EXTRACT(dow FROM datetime)` covers simple cases in SQL directly. Can be added
  later without breaking existing tables if a real need appears.

### Ingestion

No separate raw/bronze layer: unlike project 1, there is no ML feature engineering step
here, so the DuckDB warehouse is written to directly from each source connector.

```bash
uv run warehouse backfill --start 2024-02-01   # éCO2mix + ENTSO-E, idempotent
uv run warehouse refresh                        # incremental, from each table's last datetime
```

Idempotence: upsert (delete then insert over the affected date range) per table — the
same "idempotent, deduplicated, resumable" pattern already proven in project 1.

Concurrency: no support for concurrent write/read access. The MCP server opens the
DuckDB file `read_only=True`; ingestion runs to completion, then the server reads —
same assumption project 1 makes between its daily Airflow run and its serving API.
Acceptable for a local-dev portfolio project.

### MCP server

A standalone HTTP service (own process, `streamable-http` transport via the `mcp`
Python SDK's `FastMCP`), separate from the Phase 2 agent's own FastAPI app — matching
the architecture diagram above.

| Tool | Role |
|---|---|
| `get_schema()` | Returns warehouse tables/columns and the distinct `source` values — prevents the agent from inventing a column name or production source. |
| `run_sql_query(query: str)` | Executes a single read-only `SELECT` against `warehouse.duckdb`. |
| `get_latest_forecast()` | Direct wrapper of project 1's `GET /forecast/latest`. |
| `get_forecast_history(start, end)` | Direct wrapper of project 1's `GET /forecast/history?start=&end=`. |

The two forecast tools are kept separate (rather than one parametrized tool) because
they map 1:1 to project 1's two endpoints, which disambiguates the agent's tool choice —
relevant for scoring tool-use correctness in Phase 3.

**`run_sql_query` safeguards** (the only point that executes agent-written code):
- DuckDB connection opened `read_only=True` — blocks any write at the engine level.
- Pre-execution validation: exactly one statement, must start with `SELECT` (reject
  multi-statement input or write keywords). Defense in depth, not a full SQL sandbox —
  the real risk is near zero here (local DuckDB, read-only, no sensitive data).
- No timeout handling needed: all three tables hold at most a few hundred thousand
  hourly rows (~2 years of data), so even a malformed query costs milliseconds, not a
  real local DoS risk. Results are capped at 500 rows with an explicit message asking
  the agent to aggregate instead of listing, to avoid flooding its context.

**Robustness**: if project 1's API is unreachable, the forecast tools return a clear MCP
error ("forecast API unreachable") instead of a raw exception — not to handle a specific
benchmark trap category (the "out-of-scope" category was not selected for Phase 3), just
so the Phase 2 agent can report "I don't know" instead of crashing.

### Testing

- Connectors (éCO2mix, ENTSO-E): response parsing against fixtures (no real network
  calls in the unit test suite), 15/30-min → hourly aggregation, idempotent upsert/dedup.
- Warehouse schema: an integration test building a small in-memory/temp-file warehouse,
  inserting known rows, and checking constraints (primary keys, no duplicates after a
  second upsert over the same range).
- `run_sql_query`: valid queries pass; multi-statement or non-`SELECT` input is rejected;
  the row cap is enforced.
- Forecast tools: HTTP client to project 1's API is mocked — success case and API-down
  case (clean error message, no raw stack trace propagated).

No automated test hits the real RTE/ENTSO-E/ODRÉ APIs — as in project 1, verification
against real data happens once, manually, during implementation, and is recorded in an
ADR (mirroring project 1's ADR 0001).

## Alternatives considered

- **Reuse project 1's parquet files directly** (no new ingestion): rejected — that
  schema is shaped for ML feature engineering, not ad-hoc analytical SQL, and it would
  tightly couple the two projects.
- **Postgres instead of DuckDB**: rejected for Phase 1 — a real server is unjustified
  infrastructure for a read-mostly, modest-volume analytical store; DuckDB is the
  simplest option that solves the actual problem (consistent with `french-business-
  registry` already covering the "real warehouse server" pattern).
- **Structured tools with fixed parameters** (e.g. `get_consumption(start, end)`,
  `get_production_mix(start, end, source)`) instead of a generic SQL tool: rejected —
  less representative of "an agent that queries a data warehouse" (a weaker AI
  Engineering signal), and would require adding a new tool for every question shape not
  anticipated upfront. A single read-only `run_sql_query` is both simpler (one tool
  instead of several) and more capable.
- **stdio transport for MCP**: rejected in favor of `streamable-http` — a real,
  independently running HTTP service is more representative of production use and
  reusable from other MCP clients, at the cost of managing one more port locally.

## Consequences

- The warehouse and its MCP server can be built, tested, and verified end-to-end
  entirely independently of the agent (Phase 2) and the benchmark (Phase 3).
- The day-ahead price source (ENTSO-E) is not yet confirmed to work as assumed; the
  first implementation task must verify real API access before the connector is
  considered done, and the result (confirmed or revised) will be recorded in an ADR.
- Cross-border exchanges, CO2 intensity, and a calendar dimension are deliberately left
  out of Phase 1; adding them later is a schema addition, not a migration, if Phase 3's
  benchmark design surfaces a real need for them.
