# ADR 0004: Async agent invocation (`ainvoke`, `AsyncSqliteSaver`) everywhere

## Context
Obtaining a working Gemini key (ADR 0003) made it possible, for the first time,
to run the agent end-to-end against a real LLM and the real MCP server instead
of mocks. The first real run failed twice in a row, on bugs the mocked test
suite was structurally unable to catch — every test mocked `agent.invoke` or
`agent.ainvoke` directly, never exercising the real tool objects or the real
checkpointer's sync/async surface.

1. `src/eaa/agent/mcp_client.py` builds each MCP tool as a `StructuredTool`
   constructed with `coroutine=...` and no `func=` — coroutine-only by design,
   since the underlying `mcp.ClientSession` calls are async. LangGraph's
   `ToolNode`, when the graph is run via the sync `agent.invoke()`, calls
   `tool.invoke()` → `tool.run()`, which raises `NotImplementedError:
   StructuredTool does not support sync invocation` the instant the model
   calls any tool — i.e. on nearly every real turn, since the agent's whole
   purpose is to call tools.
2. Fixing that by switching to `agent.ainvoke()` surfaced a second bug one
   layer down: `src/eaa/agent/memory.py`'s `get_checkpointer()` returned a
   `SqliteSaver` (wrapping a plain `sqlite3.Connection`), whose async
   checkpoint methods (`aget_tuple`, etc.) are all unimplemented stubs that
   raise `NotImplementedError: The SqliteSaver does not support async
   methods.` LangGraph's async loop calls exactly those methods.

## Decision
Make the whole real-tool-calling path async, end to end, rather than patching
around it:
- `src/eaa/agent/memory.py`: `get_checkpointer()` is now `async def`, opens an
  `aiosqlite.Connection` and returns `AsyncSqliteSaver` instead of `SqliteSaver`.
- `src/eaa/agent/cli.py`: the REPL body (`_run()`) is `async def`; `main()`
  wraps it in `asyncio.run()`. Uses `agent.ainvoke(...)` and
  `await get_mcp_tools(...)` (the unwrapped async function, not its sync
  `load_mcp_tools` wrapper — see below).
- `src/eaa/agent/api.py`: the `/ask` route handler is `async def` and uses
  `await AGENT.ainvoke(...)`. Module-level init (`_checkpointer`, `AGENT`)
  still runs at import time via `asyncio.run(get_checkpointer())`, before
  uvicorn's event loop exists, so there's no loop to conflict with; the
  `lifespan` shutdown now does `await _checkpointer.conn.close()`.
- `src/eaa/benchmark/runner.py`: `run_one` and `run_benchmark` are both
  `async def`, calling `await agent.ainvoke(...)`.
- `src/eaa/benchmark/cli.py`: same `_run()`/`main()` split as the agent CLI.

**Why `get_mcp_tools` (async) instead of `load_mcp_tools` (its sync
`asyncio.run()` wrapper) inside the new async entry points:** `asyncio.run()`
cannot be nested inside an already-running event loop — calling the sync
wrapper from inside `_run()` (itself running under `asyncio.run(_run())`)
raises `RuntimeError`. `src/eaa/agent/api.py` is the one exception: its call
to `load_mcp_tools` happens at module import time, before any loop is running,
so the sync wrapper is correct there — nesting isn't possible when there's
nothing to nest into.

**Why `AsyncSqliteSaver`'s sync surface can't be used as a stopgap either:**
confirmed by reading its source — every sync method (`get_tuple`, etc.) checks
`asyncio.get_running_loop() is self.loop` and raises `asyncio.InvalidStateError`
telling the caller to use the async interface instead. There is no sync/async
bridge to lean on; the fix has to be "go async," not "make async optional."

## Alternatives considered
- **Give the MCP tools a sync `func=` too** (e.g. wrapping each async call in
  its own `asyncio.run()`). Rejected: `asyncio.run()` cannot be called from
  within a running loop, and the agent's own invocation can legitimately
  happen from either a sync or async caller depending on entry point — a sync
  wrapper would just reintroduce the same nesting failure one level down.
- **Keep `SqliteSaver` and avoid tools that need an event loop.** Not
  possible: the MCP SDK's `ClientSession` is inherently async (it talks to the
  server over `streamable_http_client`), so there is no sync implementation to
  fall back to.

## Consequences
- A new pytest hang, caused by this same change, had to be fixed separately:
  `aiosqlite.Connection` runs a non-daemon background thread that only stops on
  `conn.close()`. `tests/agent/test_api.py` exercises the FastAPI app through a
  bare `TestClient(app)` (no `with` block) in most tests, which never triggers
  the `lifespan` shutdown that would close the module-level `_checkpointer`.
  `tests/conftest.py` now closes it once, in a session-scoped `autouse`
  fixture, after the whole test session. The two tests in
  `tests/agent/test_memory.py` that create their own checkpointer now close it
  in a `finally` block for the same reason.
- Every test mocking `agent.invoke`/`checkpointer` had to be rewritten to mock
  `agent.ainvoke`/an async-compatible checkpointer (`unittest.mock.AsyncMock`)
  instead — a mechanical but repo-wide change across
  `tests/agent/test_cli.py`, `tests/agent/test_api.py`,
  `tests/agent/test_memory.py`, `tests/benchmark/test_runner.py`, and
  `tests/benchmark/test_cli.py`.
- Verified against a real Gemini call end-to-end after the fix: the agent
  called `get_schema` and `get_latest_forecast` through the real MCP server
  and produced a coherent answer, including a clean "forecast unavailable"
  message when the forecast tool call itself failed — the intended
  clean-failure behavior, not a crash or a hallucinated number.
- This mocked-test blind spot is worth remembering for any future tool
  integration in this codebase: a 100%-passing mocked suite proved nothing
  about whether the sync/async contract between the agent and a real tool
  actually holds. Only a real run against the real tool caught it.
