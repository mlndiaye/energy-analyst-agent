# Phase 2 — LangGraph Agent, FastAPI, CLI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LangGraph ReAct agent that uses Phase 1's MCP server as its tools, exposed via a FastAPI `/ask` endpoint and an interactive CLI, both with multi-turn memory.

**Architecture:** A `create_react_agent` (LangGraph prebuilt) wired to Claude (via `init_chat_model`), LangChain tools fetched from the MCP server through `langchain-mcp-adapters`, and a local SQLite checkpointer for conversation memory. FastAPI and the CLI both build one agent instance at startup and call `.invoke()` per turn.

**Tech Stack:** Python 3.12, `uv`, LangGraph, `langchain-mcp-adapters`, `langchain-anthropic`, FastAPI, `langgraph-checkpoint-sqlite`, pytest, ruff.

**Reference:** `docs/superpowers/specs/2026-10-21-langgraph-agent-design.md` (approved design this plan implements). Phase 1 code this builds on: `src/eaa/mcp/server.py`, `src/eaa/warehouse.py`.

**A note on library APIs:** this plan depends on three fast-moving libraries (`mcp`-adjacent: `langchain-mcp-adapters`; `langgraph-checkpoint-sqlite`; the installed `mcp` server's own `run()`/settings API). Phase 1 already hit one real surprise this way (`FastMCP` renamed to `MCPServer` between SDK versions). Several tasks below include an explicit **verification step**: inspect the actual installed API before writing the final code, and adapt the snippet given here if it differs — the same pattern Phase 1's Task 13 used. Don't skip these steps even though "move fast" is the brief; skipping them is how Phase 1's SDK surprise happened in the first place.

---

## Task 1: Bootstrap the agent subpackage

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `src/eaa/agent/__init__.py`

- [ ] **Step 1: Add dependencies and the CLI script entry to `pyproject.toml`**

Change the `dependencies` list to:

```toml
dependencies = [
    "duckdb",
    "pandas",
    "requests",
    "mcp[cli]>=2.0,<3.0",
    "python-dotenv",
    "langgraph",
    "langchain",
    "langchain-anthropic",
    "langchain-mcp-adapters",
    "langgraph-checkpoint-sqlite",
    "fastapi[standard]",
]
```

Add to `[project.scripts]`:

```toml
eaa-agent = "eaa.agent.cli:main"
```

- [ ] **Step 2: Install and verify**

Run: `uv sync --extra dev`
Expected: resolves and installs without errors. Note the resolved `langgraph`/`langchain-mcp-adapters`/`langgraph-checkpoint-sqlite` versions printed — you'll need them for the verification steps in later tasks.

Run: `uv run python -c "import langgraph, langchain_mcp_adapters, langchain_anthropic, fastapi; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Add new env vars to `.env.example`**

Append:

```bash
# Anthropic API key — https://console.anthropic.com
ANTHROPIC_API_KEY=

# Phase 1's MCP server (streamable-http)
MCP_SERVER_URL=http://127.0.0.1:8001/mcp
```

- [ ] **Step 4: Ignore the agent's local memory file**

Append to `.gitignore` (after the existing `*.duckdb.wal` line):

```gitignore

# LangGraph conversation memory (local, rebuildable)
agent_memory.sqlite
```

- [ ] **Step 5: Create the package skeleton**

```bash
mkdir -p src/eaa/agent tests/agent
touch src/eaa/agent/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .env.example .gitignore src/eaa/agent/__init__.py
git commit -m "chore: bootstrap the agent subpackage for Phase 2"
```

---

## Task 2: Fix the MCP server's port (Phase 1 adjustment)

**Context:** at Phase 1 verification time, `uv run eaa-mcp-server` started on port 8000 by default — the same default port as project 1's forecasting API. Both now need to run at once, so the MCP server needs a fixed, different port (8001).

**Files:**
- Modify: `src/eaa/mcp/server.py`
- Test: `tests/mcp/test_server.py`

- [ ] **Step 1: Verify the installed `MCPServer`'s actual port-configuration API**

Run:
```bash
uv run python -c "
import inspect
from mcp.server.mcpserver import MCPServer
print(inspect.signature(MCPServer.__init__))
print(inspect.signature(MCPServer.run))
"
```

Look for how host/port are configured — likely either keyword arguments on `run()` (e.g. `host=`, `port=`), or settings passed to `__init__` (e.g. `MCPServer(name, host=..., port=...)`), or a `mcp.settings.port = ...` attribute set before calling `run()`. Use whichever mechanism the actual signature shows. The steps below assume `run()` keyword arguments; **adjust Step 3's code to match what you actually find** if it differs.

- [ ] **Step 2: Write the failing test**

```python
# tests/mcp/test_server.py
import os
from unittest.mock import patch

from eaa.mcp import server


def test_main_uses_configured_port(monkeypatch) -> None:
    monkeypatch.setenv("MCP_SERVER_PORT", "9999")
    with patch("eaa.mcp.server.mcp.run") as mock_run:
        server.main()

    _, kwargs = mock_run.call_args
    assert kwargs.get("port") == 9999


def test_main_defaults_to_port_8001(monkeypatch) -> None:
    monkeypatch.delenv("MCP_SERVER_PORT", raising=False)
    with patch("eaa.mcp.server.mcp.run") as mock_run:
        server.main()

    _, kwargs = mock_run.call_args
    assert kwargs.get("port") == 8001
```

If Step 1 found a different mechanism than a `port=` kwarg on `run()` (e.g. a settings attribute), rewrite these two tests to assert on that mechanism instead — keep the same two scenarios (explicit `MCP_SERVER_PORT` env var honored; default is 8001).

- [ ] **Step 3: Run and confirm failure**

Run: `uv run pytest tests/mcp/test_server.py -v`
Expected: `FAIL` (current `main()` doesn't read `MCP_SERVER_PORT` or pass a port at all).

- [ ] **Step 4: Update `main()` in `src/eaa/mcp/server.py`**

```python
def main() -> None:
    port = int(os.environ.get("MCP_SERVER_PORT", "8001"))
    mcp.run(transport="streamable-http", host="127.0.0.1", port=port)
```

Adjust to match whatever mechanism Step 1 actually found, if different.

- [ ] **Step 5: Run and confirm success**

Run: `uv run pytest tests/mcp/test_server.py -v`
Expected: `PASS`

Run the full suite to confirm nothing else broke: `uv run pytest -q`

- [ ] **Step 6: Manually confirm the server actually starts on the new port**

```bash
uv run eaa-mcp-server &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/mcp || true
kill %1
```

Expected: the server starts (check for `Uvicorn running on http://127.0.0.1:8001` in its output) and the port is no longer 8000. The exact curl status code doesn't matter (MCP's streamable-http endpoint doesn't necessarily respond to a bare GET) — what matters is confirming the server bound to 8001, not 8000.

- [ ] **Step 7: Commit**

```bash
git add src/eaa/mcp/server.py tests/mcp/test_server.py
git commit -m "fix: move MCP server to port 8001 to avoid colliding with project 1's API"
```

---

## Task 3: MCP client wrapper

**Files:**
- Create: `src/eaa/agent/mcp_client.py`
- Test: `tests/agent/test_mcp_client.py`

- [ ] **Step 1: Verify `langchain-mcp-adapters`'s actual connection config shape**

Run:
```bash
uv run python -c "
import inspect
from langchain_mcp_adapters.client import MultiServerMCPClient
print(inspect.signature(MultiServerMCPClient.__init__))
print(inspect.signature(MultiServerMCPClient.get_tools))
"
```

Confirm the connections dict shape (server name → config dict with a URL and a transport key — likely `"transport": "streamable_http"` and `"url": "..."`, but confirm the exact key names and value from the real signature/docstring) and that `get_tools()` is async. Adjust Step 3's code if the shape differs.

- [ ] **Step 2: Write the failing test**

```python
# tests/agent/test_mcp_client.py
from unittest.mock import AsyncMock, patch

import pytest

from eaa.agent import mcp_client


@pytest.mark.asyncio
async def test_get_mcp_tools_returns_tools_from_the_server() -> None:
    fake_tools = ["tool_a", "tool_b"]

    with patch("eaa.agent.mcp_client.MultiServerMCPClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.get_tools = AsyncMock(return_value=fake_tools)

        tools = await mcp_client.get_mcp_tools("http://127.0.0.1:8001/mcp")

    assert tools == fake_tools


def test_load_mcp_tools_runs_the_async_version_synchronously() -> None:
    with patch("eaa.agent.mcp_client.get_mcp_tools") as mock_get:
        async def _fake(url: str) -> list[str]:
            return ["tool_a"]

        mock_get.side_effect = _fake

        tools = mcp_client.load_mcp_tools("http://127.0.0.1:8001/mcp")

    assert tools == ["tool_a"]
```

This needs `pytest-asyncio` for the `@pytest.mark.asyncio` test. Add it to `pyproject.toml`'s `dev` extra:

```toml
dev = ["pytest", "pytest-asyncio", "ruff"]
```

And add to `[tool.pytest.ini_options]`:

```toml
asyncio_mode = "auto"
```

Run `uv sync --extra dev` after this change, before continuing.

- [ ] **Step 3: Run and confirm failure**

Run: `uv run pytest tests/agent/test_mcp_client.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.agent.mcp_client'`

- [ ] **Step 4: Implement `src/eaa/agent/mcp_client.py`**

```python
"""Connects to Phase 1's MCP server and exposes its tools as LangChain tools."""

from __future__ import annotations

import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient


async def get_mcp_tools(url: str) -> list:
    """Fetch the warehouse MCP server's tools as LangChain tools."""
    client = MultiServerMCPClient(
        {"warehouse": {"url": url, "transport": "streamable_http"}}
    )
    return await client.get_tools()


def load_mcp_tools(url: str) -> list:
    """Synchronous wrapper for get_mcp_tools, for use at process startup."""
    return asyncio.run(get_mcp_tools(url))
```

Adjust the `MultiServerMCPClient({...})` config shape to match what Step 1 actually found, if different.

- [ ] **Step 5: Run and confirm success**

Run: `uv run pytest tests/agent/test_mcp_client.py -v`
Expected: `PASS`

- [ ] **Step 6: Commit**

```bash
git add src/eaa/agent/mcp_client.py tests/agent/test_mcp_client.py pyproject.toml uv.lock
git commit -m "feat: add MCP client wrapper fetching warehouse tools for the agent"
```

---

## Task 4: System prompt and agent graph

**Files:**
- Create: `src/eaa/agent/graph.py`
- Test: `tests/agent/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_graph.py
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from eaa.agent import graph


def test_build_agent_returns_a_final_ai_message() -> None:
    fake_model = GenericFakeChatModel(messages=iter([AIMessage(content="42 TWh")]))

    agent = graph.build_agent(tools=[], model=fake_model)
    result = agent.invoke({"messages": [("user", "What was yesterday's consumption?")]})

    final_message = result["messages"][-1]
    assert final_message.content == "42 TWh"


def test_build_agent_uses_the_system_prompt() -> None:
    fake_model = GenericFakeChatModel(messages=iter([AIMessage(content="ok")]))

    agent = graph.build_agent(tools=[], model=fake_model)
    result = agent.invoke({"messages": [("user", "hi")]})

    system_messages = [m for m in result["messages"] if m.type == "system"]
    assert len(system_messages) == 1
    assert "power system" in system_messages[0].content.lower()
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/agent/test_graph.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.agent.graph'`

- [ ] **Step 3: Implement `src/eaa/agent/graph.py`**

```python
"""Builds the LangGraph ReAct agent over the warehouse/forecast MCP tools."""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import create_react_agent

SYSTEM_PROMPT = """\
You are an analyst of the French power system. Answer questions about electricity \
consumption, production mix, day-ahead prices, and forecasts using the tools \
available to you -- never rely on your own general knowledge for a number that a \
tool could provide, since your answers must be verifiable against real data.

If a tool call fails -- whether as a protocol-level error, or as a successful \
result whose payload is a dict containing an "error" key -- say clearly that the \
data wasn't available and why, rather than guessing or inventing a number.
"""


def default_model() -> BaseChatModel:
    """The default chat model for this agent: Claude, via Anthropic."""
    return init_chat_model("anthropic:claude-sonnet-4-5-20250929")


def build_agent(
    tools: list,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Build the compiled ReAct agent graph."""
    return create_react_agent(
        model=model or default_model(),
        tools=tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
```

**Verification note:** if `uv run pytest tests/agent/test_graph.py -v` fails with an error about `create_react_agent`'s `prompt` parameter name (some LangGraph versions call it `state_modifier` or `messages_modifier` instead), run `uv run python -c "import inspect; from langgraph.prebuilt import create_react_agent; print(inspect.signature(create_react_agent))"` and adjust the parameter name used above to match.

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/agent/test_graph.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/agent/graph.py tests/agent/test_graph.py
git commit -m "feat: add the ReAct agent graph with the analyst system prompt"
```

---

## Task 5: Tool-call trace extraction

**Files:**
- Create: `src/eaa/agent/tool_trace.py`
- Test: `tests/agent/test_tool_trace.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_tool_trace.py
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from eaa.agent import tool_trace


def test_extract_tool_calls_returns_name_args_and_result() -> None:
    messages = [
        HumanMessage(content="What was yesterday's consumption?"),
        AIMessage(
            content="",
            tool_calls=[
                {"name": "run_sql_query", "args": {"query": "SELECT 1"}, "id": "call_1"}
            ],
        ),
        ToolMessage(content="[{'x': 1}]", tool_call_id="call_1", name="run_sql_query"),
        AIMessage(content="It was 1."),
    ]

    calls = tool_trace.extract_tool_calls(messages)

    assert calls == [
        {"name": "run_sql_query", "args": {"query": "SELECT 1"}, "result": "[{'x': 1}]"}
    ]


def test_extract_tool_calls_returns_empty_list_when_no_tools_used() -> None:
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]

    assert tool_trace.extract_tool_calls(messages) == []
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/agent/test_tool_trace.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.agent.tool_trace'`

- [ ] **Step 3: Implement `src/eaa/agent/tool_trace.py`**

```python
"""Extracts a flat tool-call trace from a LangGraph run's message list."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


def extract_tool_calls(messages: list[BaseMessage]) -> list[dict]:
    """Pair each AIMessage tool call with its matching ToolMessage result."""
    results_by_id = {
        m.tool_call_id: m.content for m in messages if isinstance(m, ToolMessage)
    }

    calls = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            calls.append(
                {
                    "name": call["name"],
                    "args": call["args"],
                    "result": results_by_id.get(call["id"]),
                }
            )
    return calls
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/agent/test_tool_trace.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/agent/tool_trace.py tests/agent/test_tool_trace.py
git commit -m "feat: add tool-call trace extraction for /ask's response"
```

---

## Task 6: SQLite checkpointer helper

**Files:**
- Create: `src/eaa/agent/memory.py`
- Test: `tests/agent/test_memory.py`

- [ ] **Step 1: Verify the installed `SqliteSaver`'s actual constructor/setup API**

Run:
```bash
uv run python -c "
import inspect
from langgraph.checkpoint.sqlite import SqliteSaver
print(inspect.signature(SqliteSaver.__init__))
print(inspect.signature(SqliteSaver.from_conn_string))
"
```

Confirm whether `SqliteSaver(conn)` takes a raw `sqlite3.Connection` directly, and whether a `.setup()` call is needed/available to create the checkpoint tables. Adjust Step 3 if the real API differs (e.g. if `from_conn_string` is the only supported entry point, use it as a context manager entered once and kept open, rather than a plain constructor call).

- [ ] **Step 2: Write the failing test**

```python
# tests/agent/test_memory.py
from pathlib import Path

from eaa.agent import memory


def test_get_checkpointer_creates_a_working_sqlite_file(tmp_path: Path) -> None:
    db_path = tmp_path / "test_memory.sqlite"

    checkpointer = memory.get_checkpointer(db_path)

    assert db_path.exists()
    # A checkpointer that round-trips a trivial write/read proves the tables exist.
    config = {"configurable": {"thread_id": "t1"}}
    checkpointer.put(config, {"v": 1, "ts": "2026-01-01", "id": "c1", "channel_values": {}}, {}, {})
    assert checkpointer.get(config) is not None
```

If Step 1's real API makes this exact `put`/`get` call shape wrong (checkpoint APIs vary by version), simplify the test to just asserting the file exists and no exception was raised during setup — the important behavior is "calling this function produces a usable checkpointer backed by a real file," not the exact internal checkpoint tuple shape.

- [ ] **Step 3: Run and confirm failure**

Run: `uv run pytest tests/agent/test_memory.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.agent.memory'`

- [ ] **Step 4: Implement `src/eaa/agent/memory.py`**

```python
"""Local SQLite-backed conversation memory for the agent."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

DEFAULT_MEMORY_PATH = Path("agent_memory.sqlite")


def get_checkpointer(db_path: Path = DEFAULT_MEMORY_PATH) -> SqliteSaver:
    """Open (creating if needed) the local conversation-memory database."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    return checkpointer
```

Adjust to match whatever Step 1 found if `SqliteSaver(conn)` / `.setup()` isn't the real API.

- [ ] **Step 5: Run and confirm success**

Run: `uv run pytest tests/agent/test_memory.py -v`
Expected: `PASS`

- [ ] **Step 6: Commit**

```bash
git add src/eaa/agent/memory.py tests/agent/test_memory.py
git commit -m "feat: add local SQLite conversation-memory checkpointer"
```

---

## Task 7: FastAPI `/ask` endpoint

**Files:**
- Create: `src/eaa/agent/api.py`
- Test: `tests/agent/test_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_api.py
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from eaa.agent.api import app


def _fake_agent_result(answer: str) -> dict:
    return {"messages": [HumanMessage(content="q"), AIMessage(content=answer)]}


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_returns_answer_and_generates_a_session_id() -> None:
    with patch("eaa.agent.api.AGENT") as mock_agent:
        mock_agent.invoke.return_value = _fake_agent_result("42 TWh")

        client = TestClient(app)
        response = client.post("/ask", json={"question": "yesterday's consumption?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "42 TWh"
    assert body["session_id"]
    assert body["tool_calls"] == []


def test_ask_reuses_a_provided_session_id() -> None:
    with patch("eaa.agent.api.AGENT") as mock_agent:
        mock_agent.invoke.return_value = _fake_agent_result("ok")

        client = TestClient(app)
        response = client.post(
            "/ask", json={"question": "hi", "session_id": "existing-session"}
        )

    assert response.json()["session_id"] == "existing-session"
    call_config = mock_agent.invoke.call_args.kwargs["config"]
    assert call_config["configurable"]["thread_id"] == "existing-session"
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/agent/test_api.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.agent.api'`

- [ ] **Step 3: Implement `src/eaa/agent/api.py`**

```python
"""FastAPI service exposing the agent as POST /ask."""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from eaa.agent.graph import build_agent
from eaa.agent.mcp_client import load_mcp_tools
from eaa.agent.memory import get_checkpointer
from eaa.agent.tool_trace import extract_tool_calls

load_dotenv()

app = FastAPI(title="energy-analyst-agent")

_MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")
AGENT = build_agent(
    tools=load_mcp_tools(_MCP_SERVER_URL),
    checkpointer=get_checkpointer(),
)


class AskRequest(BaseModel):
    question: str
    session_id: str | None = None


class ToolCall(BaseModel):
    name: str
    args: dict
    result: object


class AskResponse(BaseModel):
    answer: str
    session_id: str
    tool_calls: list[ToolCall]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest) -> AskResponse:
    session_id = request.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    result = AGENT.invoke({"messages": [("user", request.question)]}, config=config)
    messages = result["messages"]

    return AskResponse(
        answer=messages[-1].content,
        session_id=session_id,
        tool_calls=extract_tool_calls(messages),
    )
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/agent/test_api.py -v`
Expected: `PASS`

Note: this test module imports `eaa.agent.api`, which calls `load_mcp_tools(...)` and `build_agent(...)` at **import time** (module-level `AGENT = ...`). Since no real MCP server or API key is available during the test run, `load_mcp_tools` would try a real network connection and fail. To keep this test hermetic, mock `eaa.agent.mcp_client.load_mcp_tools` and `eaa.agent.graph.build_agent` (or `eaa.agent.memory.get_checkpointer`) at the top of `tests/agent/test_api.py`, **before** importing `eaa.agent.api`, e.g.:

```python
from unittest.mock import MagicMock, patch

with (
    patch("eaa.agent.mcp_client.load_mcp_tools", return_value=[]),
    patch("eaa.agent.graph.build_agent", return_value=MagicMock()),
):
    from eaa.agent.api import app  # noqa: E402  (import must happen inside the patch)
```

Replace the plain `from eaa.agent.api import app` at the top of the test file with this pattern, and adjust the rest of the test file's imports/structure accordingly. Run the tests again after this change to confirm they still pass and are hermetic (temporarily unset `ANTHROPIC_API_KEY` and `MCP_SERVER_URL`/stop any running MCP server to prove no real network call happens).

- [ ] **Step 5: Commit**

```bash
git add src/eaa/agent/api.py tests/agent/test_api.py
git commit -m "feat: add FastAPI /ask endpoint with session memory and tool-call trace"
```

---

## Task 8: CLI REPL

**Files:**
- Create: `src/eaa/agent/cli.py`
- Test: `tests/agent/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_cli.py
import uuid
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from eaa.agent import cli


def test_repl_prints_answers_until_exit(capsys) -> None:
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = {
        "messages": [HumanMessage(content="hi"), AIMessage(content="hello!")]
    }

    with (
        patch("eaa.agent.cli.build_agent", return_value=fake_agent),
        patch("eaa.agent.cli.load_mcp_tools", return_value=[]),
        patch("eaa.agent.cli.get_checkpointer", return_value=MagicMock()),
        patch("builtins.input", side_effect=["hi", "exit"]),
    ):
        cli.main()

    captured = capsys.readouterr()
    assert "hello!" in captured.out


def test_repl_uses_one_thread_id_for_the_whole_session() -> None:
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = {
        "messages": [HumanMessage(content="hi"), AIMessage(content="ok")]
    }

    with (
        patch("eaa.agent.cli.build_agent", return_value=fake_agent),
        patch("eaa.agent.cli.load_mcp_tools", return_value=[]),
        patch("eaa.agent.cli.get_checkpointer", return_value=MagicMock()),
        patch("builtins.input", side_effect=["one", "two", "exit"]),
    ):
        cli.main()

    first_thread_id = fake_agent.invoke.call_args_list[0].kwargs["config"]["configurable"]["thread_id"]
    second_thread_id = fake_agent.invoke.call_args_list[1].kwargs["config"]["configurable"]["thread_id"]
    assert first_thread_id == second_thread_id
    assert uuid.UUID(first_thread_id)  # it's a real UUID
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/agent/test_cli.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.agent.cli'`

- [ ] **Step 3: Implement `src/eaa/agent/cli.py`**

```python
"""Interactive CLI for the energy analyst agent."""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv

from eaa.agent.graph import build_agent
from eaa.agent.mcp_client import load_mcp_tools
from eaa.agent.memory import get_checkpointer


def main() -> None:
    load_dotenv()
    mcp_url = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")

    agent = build_agent(tools=load_mcp_tools(mcp_url), checkpointer=get_checkpointer())
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("energy-analyst-agent -- type 'exit' or Ctrl+D to quit")
    while True:
        try:
            question = input("> ")
        except EOFError:
            print()
            break
        if question.strip().lower() == "exit":
            break

        result = agent.invoke({"messages": [("user", question)]}, config=config)
        print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/agent/test_cli.py -v`
Expected: `PASS`

Run the full suite to confirm nothing else broke: `uv run pytest -q`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/agent/cli.py tests/agent/test_cli.py
git commit -m "feat: add interactive CLI REPL for the agent"
```

---

## Task 9: Manual end-to-end verification and README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full test suite one more time**

Run: `uv run pytest -q`
Expected: all tests pass (Tasks 1-8's tests plus Phase 1's existing suite).

Run: `uv run ruff check . && uv run ruff format --check src tests`
Expected: clean (ignore the pre-existing, unrelated markdown-formatting nit in the plans directory if `ruff format --check .` is run repo-wide).

- [ ] **Step 2: Manually verify the full stack with a real Claude call**

Requires `ANTHROPIC_API_KEY` set in `.env`, and `warehouse.duckdb` already populated (run `uv run warehouse backfill` first if not — this will itself need `ENTSOE_API_TOKEN`, per ADR 0001; if that's still not available, backfill éCO2mix data alone is enough to test the warehouse tools, even with `day_ahead_prices_hourly` empty).

```bash
uv run eaa-mcp-server &
sleep 2
uv run eaa-agent
```

At the prompt, ask a real question the warehouse can answer, e.g. "What tables are available?" (should trigger `get_schema`) and a follow-up question referencing the first answer (to confirm multi-turn memory works). Confirm tool calls actually happen (no hallucinated numbers) and the conversation remembers context across turns. Stop the CLI (`exit`), then kill the MCP server (`kill %1`).

- [ ] **Step 3: Manually verify `/ask` over HTTP**

```bash
uv run eaa-mcp-server &
sleep 2
uv run uvicorn eaa.agent.api:app --port 8002 &
sleep 2
curl -s -X POST http://127.0.0.1:8002/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What tables are available in the warehouse?"}' | python3 -m json.tool
kill %2 %1
```

Expected: a JSON response with `answer`, `session_id`, and a non-empty `tool_calls` array showing `get_schema` was called.

Report honestly if either manual check can't fully run (e.g. no `ANTHROPIC_API_KEY` available in this environment) — note exactly what was and wasn't verified, the same way Phase 1's Task 13 handled the ENTSO-E token gap.

- [ ] **Step 4: Update `README.md`**

Add a "Phase 2" entry to the Status section (replacing the "Phase 2 — ahead" line) and a "Running the agent" subsection under Getting Started:

```markdown
**Phase 2 — shipped**: a LangGraph ReAct agent (Claude by default) using Phase 1's MCP
server as tools, with local SQLite conversation memory, served over a FastAPI endpoint
(`POST /ask`) and an interactive CLI (`uv run eaa-agent`).
```

```markdown
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

Requires `ANTHROPIC_API_KEY` in `.env` (see `.env.example`).
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: update README with Phase 2 status and running instructions"
```

---

## Plan self-review notes

- **Spec coverage**: ReAct prebuilt agent (Task 4), Claude via `init_chat_model` (Task 4), `langchain-mcp-adapters` client (Task 3), SqliteSaver memory (Task 6), port reassignment (Task 2), `/ask` request/response shape including `tool_calls` (Task 7), CLI REPL with fixed `thread_id` per session (Task 8), manual end-to-end verification (Task 9) — every design-doc decision maps to a task.
- **Honest uncertainty**: three tasks (2, 3, 6) include an explicit API-verification step before locking in code, rather than asserting unverified library internals as fact — consistent with how Phase 1's real SDK-version surprise was handled, and with this plan's "move fast but don't skip verification" framing.
- **Type/signature consistency checked**: `build_agent(tools, model=None, checkpointer=None)`, `load_mcp_tools(url)`/`get_mcp_tools(url)`, `get_checkpointer(db_path=...)`, `extract_tool_calls(messages)` are each defined once (Tasks 3, 4, 5, 6) and used with matching names/signatures in every later task that calls them (Tasks 7, 8).
- **Out of scope confirmed absent from every task**: no web UI, no public deployment, no multi-model comparison, no Langfuse — matching the design doc's explicit exclusions.
