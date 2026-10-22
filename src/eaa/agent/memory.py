"""Local SQLite-backed conversation memory for the agent."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

DEFAULT_MEMORY_PATH = Path("agent_memory.sqlite")


async def get_checkpointer(db_path: Path = DEFAULT_MEMORY_PATH) -> AsyncSqliteSaver:
    """Open (creating if needed) the local conversation-memory database.

    Async, not the sync `SqliteSaver`: the agent is invoked via `ainvoke()`
    (the MCP tools are coroutine-only, see mcp_client.py), and `SqliteSaver`
    raises `NotImplementedError` from any async checkpoint method.

    The returned `AsyncSqliteSaver` wraps an `aiosqlite.Connection` kept open
    for the lifetime of the process -- it is meant to be created once at
    startup and passed as `build_agent`'s `checkpointer`.
    """
    conn = await aiosqlite.connect(str(db_path))
    checkpointer = AsyncSqliteSaver(conn)
    await checkpointer.setup()
    return checkpointer
