"""Local SQLite-backed conversation memory for the agent."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

DEFAULT_MEMORY_PATH = Path("agent_memory.sqlite")


def get_checkpointer(db_path: Path = DEFAULT_MEMORY_PATH) -> SqliteSaver:
    """Open (creating if needed) the local conversation-memory database.

    The returned `SqliteSaver` wraps a raw `sqlite3.Connection` kept open for
    the lifetime of the process -- it is meant to be created once at startup
    and passed as `build_agent`'s `checkpointer`.
    """
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    return checkpointer
