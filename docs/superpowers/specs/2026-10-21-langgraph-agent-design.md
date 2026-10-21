# Design: Phase 2 — LangGraph agent, FastAPI, and CLI

## Context

Phase 1 (shipped) built a DuckDB warehouse and an MCP server (`src/eaa/mcp/server.py`,
`streamable-http`) exposing 4 tools: `get_schema`, `run_sql_query`, `get_latest_forecast`,
`get_forecast_history`. Phase 2 builds the agent that actually uses them: a LangGraph
agent, served over a FastAPI endpoint and an interactive CLI. Phase 3 (future spec) adds
the evaluation benchmark and the Claude-vs-Ollama comparison this agent is built to
support.

```
MCP server (Phase 1, port 8001)          Agent (Phase 2)
┌──────────────────────┐                 ┌─────────────────────────────┐
│ get_schema            │◄────MCP─────────│ create_react_agent (LangGraph)│
│ run_sql_query         │  streamable-http │  - model: Claude (Anthropic)  │
│ get_latest_forecast   │                 │  - tools: via langchain-mcp-  │
│ get_forecast_history  │                 │    adapters                   │
└──────────────────────┘                 │  - memory: SqliteSaver local   │
                                           └───────────┬───────────────┘
france-electricity-forecasting                         │
API (port 8000) ◄── (via MCP server) ────────────────────┤
                                             ┌───────────┴───────────────┐
                                             │ FastAPI POST /ask (port 8002)│
                                             │ CLI REPL (uv run eaa-agent)  │
                                             └─────────────────────────────┘
```

## Decision

### Port assignment (practical fix, adjusts Phase 1)

Project 1's forecasting API keeps its documented default (8000). The MCP server moves
to **8001** (currently defaulted to 8000 at verification time, colliding with project 1).
The agent's own FastAPI app uses **8002**. `src/eaa/mcp/server.py`'s `main()` is updated
to pass an explicit host/port to `mcp.run(...)`, configurable via an `MCP_SERVER_PORT`
env var defaulting to 8001. `.env.example` gains `MCP_SERVER_URL` (default
`http://127.0.0.1:8001`) for the agent to connect to.

### Agent architecture: prebuilt ReAct agent

`langgraph.prebuilt.create_react_agent(model, tools, checkpointer=..., prompt=...)` —
no hand-written graph. With 4 flat tools and no routing logic needed, a custom graph
would reproduce the same loop (call model → execute tool calls → call model again →
final answer) with more code to maintain for no present benefit. `src/eaa/agent/graph.py`
exposes `build_agent()`, assembling model + tools + memory + system prompt into a
compiled graph.

### Model: Claude, via a provider-agnostic abstraction

Built against Claude (Anthropic API) by default — consistent with Phase 3's planned
comparison, where Claude is the "API-based" reference model. Uses LangChain's
`init_chat_model("anthropic:claude-...")` rather than importing `langchain_anthropic`
directly, so Phase 3 can point the same `build_agent()` code at an Ollama model via
config alone, not a code change. New env var: `ANTHROPIC_API_KEY`.

### MCP client: `langchain-mcp-adapters`

`langchain_mcp_adapters.client.MultiServerMCPClient` connects to the MCP server
(`MCP_SERVER_URL`) and exposes its 4 tools as LangChain tools automatically — the
standard LangGraph↔MCP integration, avoiding a hand-rolled JSON-schema-to-tool
conversion. `src/eaa/agent/mcp_client.py` wraps the connection setup. The connection is
established once at process startup (FastAPI or CLI), not per-request; if the MCP
server is unreachable at startup, the process fails immediately with a clear message
(not a half-initialized agent that fails confusingly on the first real request) —
matching Phase 1's `_check_required_env_vars()` fail-fast pattern.

### Memory: LangGraph's `SqliteSaver` checkpointer

Multi-turn conversation is in scope (confirmed during brainstorming — interactive CLI
use benefits from follow-up questions). Rejected Redis: this is a local, single-user
tool (no concurrent processes, no deployment), so Redis would add a Docker service for
a need nothing in the project demonstrates. `langgraph.checkpoint.sqlite.SqliteSaver`
persists to a local file (`agent_memory.sqlite`, gitignored like `warehouse.duckdb`),
keyed by a `thread_id` passed in LangGraph's invocation config — zero extra
infrastructure, and it's LangGraph's own native mechanism rather than a bolted-on one.

### System prompt

States the agent's role (analyst of the French power system), instructs it to ground
every numeric answer in tool results rather than general knowledge (the project's core
value proposition — verifiable answers), and explains how to interpret both MCP failure
shapes it may see: a protocol-level tool failure, or a successful call whose payload is
`{"error": ...}` (see `src/eaa/mcp/tools.py`'s documented error-shape split from Phase 1)
— both mean "this tool failed, say so, don't invent a number."

### `POST /ask` (`src/eaa/agent/api.py`)

Request: `{"question": str, "session_id": str | None}`.
Response: `{"answer": str, "session_id": str, "tool_calls": [{"name": str, "args": dict, "result": ...}]}`.

`session_id` is generated (`uuid4`) when omitted and returned to the client to continue
the conversation on a later call. `tool_calls` is extracted from the LangGraph run's
intermediate messages after invocation — required now because Phase 3's benchmark scores
tool-use correctness, not just the final answer; adding this field later would mean
revisiting this API a second time. Also exposes `GET /health`.

### CLI (`src/eaa/agent/cli.py`, `uv run eaa-agent`)

An interactive REPL: reads a line, invokes the agent with a `thread_id` fixed for the
process's lifetime, prints the answer, repeats until `Ctrl+D`/`exit`. Shares the same
SQLite memory file as the API — same mechanism, different `thread_id` per session.

### Testing

Unit tests mock the chat model and the MCP client — no real network calls, no API key
required to run `pytest`. A manual end-to-end verification step (real Claude + a real
running MCP server) closes out the implementation, mirroring Phase 1's Task 13.

## Alternatives considered

- **Custom LangGraph graph with explicit nodes**: rejected for now — no routing logic
  exists yet that a prebuilt ReAct loop can't handle; revisit if a real need for extra
  nodes (validation, retries) appears.
- **Redis for conversation memory**: rejected — no concurrent/multi-process use case
  exists; `SqliteSaver` gives persistence with zero added infrastructure.
- **One-shot CLI (single question per command)**: rejected in favor of a REPL, since a
  one-shot CLI would need an explicit `--session-id` flag to benefit from multi-turn
  memory at all, adding friction for the interactive use case memory was chosen for.
- **Hand-rolled MCP client**: rejected — `langchain-mcp-adapters` is the maintained,
  standard integration; reimplementing it isn't justified.

## Consequences

- Running the full stack locally now requires three processes on three fixed ports
  (8000 project 1, 8001 MCP server, 8002 agent API) — to be documented clearly in the
  README's getting-started instructions.
- `POST /ask`'s `tool_calls` field is designed in now specifically to avoid Phase 3
  needing to modify this API later.
- Swapping in an Ollama model for Phase 3's comparison is a config change to
  `build_agent()`'s model argument, not a code change — a direct result of using
  `init_chat_model` instead of a provider-specific import.

## Out of scope for Phase 2

- Web UI.
- Public deployment.
- The Claude-vs-Ollama comparison itself, the benchmark dataset, and Langfuse tracing
  (all Phase 3).
