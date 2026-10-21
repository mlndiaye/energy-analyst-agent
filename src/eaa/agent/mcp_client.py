"""Connects to Phase 1's MCP server (via the official mcp SDK) and exposes its
tools as LangChain StructuredTools, since langchain-mcp-adapters (the originally
planned integration) is unmaintained and incompatible with mcp>=2.0 -- see
docs/superpowers/specs/2026-10-21-langgraph-agent-design.md.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@asynccontextmanager
async def _open_session(url: str):
    async with (
        streamable_http_client(url) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        yield session


def _make_tool_caller(url: str, name: str):
    # Opens a new connection per call rather than keeping one session open for
    # the agent's whole lifetime. Deliberate simplicity trade-off for Phase 2's
    # scope (tool calls are occasional, not a tight loop) -- don't "optimize"
    # this into a shared long-lived session unless a real need appears.
    async def _call(**kwargs) -> str:
        # LangGraph's default ToolNode only catches ValidationError/ToolException --
        # any other exception aborts the whole agent turn. A dead or unreachable MCP
        # server must not crash the graph; it should read like a failed tool result
        # the agent can react to, mirroring Phase 1's duckdb.Error -> {"error": ...}
        # clean-failure pattern at the next layer down.
        try:
            async with _open_session(url) as session:
                result = await session.call_tool(name, kwargs)
                return "".join(block.text for block in result.content if hasattr(block, "text"))
        except Exception as exc:  # noqa: BLE001 -- intentional catch-all boundary, see comment above
            return f"MCP tool call failed: {exc}"

    return _call


async def get_mcp_tools(url: str) -> list[StructuredTool]:
    """Fetch the warehouse MCP server's tools as LangChain StructuredTools."""
    async with _open_session(url) as session:
        mcp_tools = (await session.list_tools()).tools

    return [
        StructuredTool.from_function(
            coroutine=_make_tool_caller(url, mcp_tool.name),
            name=mcp_tool.name,
            description=mcp_tool.description or "",
            args_schema=mcp_tool.input_schema,
        )
        for mcp_tool in mcp_tools
    ]


def load_mcp_tools(url: str) -> list[StructuredTool]:
    """Synchronous wrapper for get_mcp_tools, for use at process startup."""
    return asyncio.run(get_mcp_tools(url))
