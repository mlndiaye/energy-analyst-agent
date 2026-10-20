"""MCP server exposing the DuckDB warehouse and project 1's forecasting API as
tools, over streamable-http. Run standalone: `uv run eaa-mcp-server`.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# mcp SDK v2.0+ renamed FastMCP to MCPServer -- see
# https://py.sdk.modelcontextprotocol.io/v2/migration/#fastmcp-renamed-to-mcpserver
from mcp.server.mcpserver import MCPServer

from eaa import warehouse
from eaa.mcp.tools import (
    get_forecast_history_impl,
    get_latest_forecast_impl,
    get_schema_impl,
    run_sql_query_impl,
)

load_dotenv()
FORECAST_API_URL = os.environ.get("FORECAST_API_URL", "http://localhost:8000")

mcp = MCPServer("energy-analyst-agent-warehouse")


@mcp.tool()
def get_schema() -> str:
    """Describe the warehouse tables, columns, and available production sources."""
    con = warehouse.get_connection(read_only=True)
    try:
        return get_schema_impl(con)
    finally:
        con.close()


@mcp.tool()
def run_sql_query(query: str) -> list[dict]:
    """Run a read-only SELECT query against the warehouse and return the rows."""
    con = warehouse.get_connection(read_only=True)
    try:
        return run_sql_query_impl(con, query)
    finally:
        con.close()


@mcp.tool()
def get_latest_forecast() -> list[dict] | dict:
    """Get tomorrow's electricity consumption forecast from the forecasting API."""
    return get_latest_forecast_impl(FORECAST_API_URL)


@mcp.tool()
def get_forecast_history(start: str | None = None, end: str | None = None) -> list[dict] | dict:
    """Get historical forecast-vs-actual-vs-RTE data (ISO dates, both optional)."""
    return get_forecast_history_impl(FORECAST_API_URL, start, end)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
