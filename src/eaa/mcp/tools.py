"""Pure functions backing the MCP tools. Unit-tested directly here, so tests
don't need a running MCP server or client; server.py wraps these in thin
@mcp.tool() decorators.
"""

from __future__ import annotations

from datetime import date

import duckdb

from eaa.mcp.forecast_client import ForecastAPIError, fetch_forecast_history, fetch_latest_forecast

# Error-shape split (intentional, not an inconsistency):
# - run_sql_query_impl raises (ValueError for a rejected query shape, or a
#   duckdb.Error propagated from execution) on failure. server.py's @mcp.tool()
#   wrapper turns that into a protocol-level isError=true tool result -- bad
#   SQL is a caller/LLM-side mistake worth surfacing as a hard error.
# - get_schema_impl / get_latest_forecast_impl / get_forecast_history_impl catch
#   their failures and return a normal {"error": ...} dict instead -- a
#   protocol-level *success* whose payload happens to describe an operational
#   condition (project 1's forecasting API down, warehouse not yet populated).
# Both shapes reach an MCP client. Phase 2's agent code must check for BOTH an
# isError result AND an "error" key in an otherwise-successful payload to catch
# every tool failure -- checking only one will miss the other failure mode.
MAX_ROWS = 500

# Keep this in sync with warehouse._SCHEMA_STATEMENTS if the schema ever changes.
_SCHEMA_DESCRIPTION = """
consumption_hourly(datetime TIMESTAMP, consumption_mw DOUBLE)
production_by_source_hourly(datetime TIMESTAMP, source VARCHAR, production_mw DOUBLE)
day_ahead_prices_hourly(datetime TIMESTAMP, price_eur_mwh DOUBLE)
""".strip()


def get_schema_impl(con: duckdb.DuckDBPyConnection) -> str:
    """Describe the warehouse tables/columns, plus the distinct production sources."""
    sources = con.execute(
        "SELECT DISTINCT source FROM production_by_source_hourly ORDER BY source"
    ).fetchall()
    source_list = ", ".join(row[0] for row in sources) if sources else "(no data ingested yet)"
    return f"{_SCHEMA_DESCRIPTION}\n\nDistinct production_by_source_hourly.source values: {source_list}"


def run_sql_query_impl(con: duckdb.DuckDBPyConnection, query: str) -> list[dict]:
    """Execute a single read-only SELECT (or WITH ... SELECT) against the warehouse,
    capped at MAX_ROWS rows. Raises on a rejected query shape or a DuckDB error --
    see the error-shape comment above.
    """
    normalized = query.strip().rstrip(";")
    if ";" in normalized:
        raise ValueError("Only a single SQL statement is allowed")
    # Note: a WITH clause can terminate in DELETE/INSERT/UPDATE in DuckDB's
    # grammar, not just SELECT -- rejecting that is intentionally left to the
    # read-only connection the MCP server always opens this with (see design
    # spec), not to this string check.
    if not normalized.upper().startswith(("SELECT", "WITH")):
        raise ValueError("Only SELECT (or WITH ... SELECT) queries are allowed")

    result = con.execute(normalized)
    columns = [d[0] for d in result.description]
    rows = result.fetchmany(MAX_ROWS + 1)
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    records = [dict(zip(columns, row, strict=True)) for row in rows]
    if truncated:
        records.append(
            {"_notice": f"Result truncated at {MAX_ROWS} rows -- aggregate instead of listing."}
        )
    return records


def get_latest_forecast_impl(base_url: str) -> list[dict] | dict:
    """Fetch project 1's latest forecast, or return {"error": ...} if the API is unreachable."""
    try:
        return fetch_latest_forecast(base_url)
    except ForecastAPIError as exc:
        return {"error": str(exc)}


def get_forecast_history_impl(
    base_url: str, start: str | None, end: str | None
) -> list[dict] | dict:
    """Fetch project 1's forecast history for [start, end], or return {"error": ...}
    on an invalid date or an unreachable API."""
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
    except ValueError as exc:
        return {"error": f"invalid date: {exc}"}

    try:
        return fetch_forecast_history(base_url, start_date, end_date)
    except ForecastAPIError as exc:
        return {"error": str(exc)}
