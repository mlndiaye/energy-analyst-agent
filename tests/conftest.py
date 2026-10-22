"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio
import sys

import pytest


@pytest.fixture(scope="session", autouse=True)
def _close_agent_api_checkpointer():
    """eaa.agent.api opens a real aiosqlite connection at import time (see its
    module-level `_checkpointer = asyncio.run(get_checkpointer())`). aiosqlite
    runs a non-daemon background thread per connection that only stops on
    conn.close() -- most tests exercise the app via a bare `TestClient(app)`
    (no `with`), which never triggers the FastAPI lifespan shutdown that would
    close it, so the thread survives and blocks pytest's own process exit at
    interpreter shutdown. Close it once, after the whole session.
    """
    yield
    api_module = sys.modules.get("eaa.agent.api")
    if api_module is not None:
        asyncio.run(api_module._checkpointer.conn.close())
