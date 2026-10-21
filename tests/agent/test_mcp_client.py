from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from eaa.agent import mcp_client


@pytest.mark.asyncio
async def test_get_mcp_tools_converts_mcp_tools_to_structured_tools() -> None:
    fake_mcp_tool = MagicMock()
    fake_mcp_tool.name = "get_schema"
    fake_mcp_tool.description = "Describe the warehouse."
    fake_mcp_tool.input_schema = {"type": "object", "properties": {}}

    fake_list_result = MagicMock()
    fake_list_result.tools = [fake_mcp_tool]

    fake_session = AsyncMock()
    fake_session.list_tools.return_value = fake_list_result

    with patch("eaa.agent.mcp_client._open_session") as mock_open_session:
        mock_open_session.return_value.__aenter__.return_value = fake_session

        tools = await mcp_client.get_mcp_tools("http://127.0.0.1:8001/mcp")

    assert len(tools) == 1
    assert tools[0].name == "get_schema"
    assert tools[0].description == "Describe the warehouse."


@pytest.mark.asyncio
async def test_tool_call_prefers_structured_content_for_multi_row_results() -> None:
    # Mirrors what the real mcp SDK returns for run_sql_query against a multi-row
    # SELECT: one TextContent block per row (naively joining them with no
    # separator would produce invalid, concatenated JSON), plus a clean
    # structured_content shape the server derived from the same rows.
    fake_result = MagicMock()
    fake_result.structured_content = {"result": [{"x": 1}, {"x": 2}]}
    fake_result.content = [
        MagicMock(text='{\n  "x": 1\n}'),
        MagicMock(text='{\n  "x": 2\n}'),
    ]

    fake_session = AsyncMock()
    fake_session.call_tool.return_value = fake_result

    with patch("eaa.agent.mcp_client._open_session") as mock_open_session:
        mock_open_session.return_value.__aenter__.return_value = fake_session

        call = mcp_client._make_tool_caller("http://127.0.0.1:8001/mcp", "run_sql_query")
        result = await call(query="SELECT x FROM t")

    assert result == str({"result": [{"x": 1}, {"x": 2}]})
    naive_join = "".join(block.text for block in fake_result.content)
    assert result != naive_join


@pytest.mark.asyncio
async def test_tool_call_unwraps_fastmcp_scalar_wrapping_for_plain_string_tools() -> None:
    # FastMCP wraps any non-dict return value (including get_schema's plain str)
    # as {"result": <value>} in structured_content. For a plain-string tool, that
    # wrapper should be unwrapped back to the bare string -- real newlines, no
    # {'result': ...} dict-repr noise -- rather than str()'d as a whole dict.
    schema_text = (
        "consumption_hourly(datetime TIMESTAMP, consumption_mw DOUBLE)\n\nDistinct sources: wind"
    )
    fake_result = MagicMock()
    fake_result.structured_content = {"result": schema_text}
    fake_result.content = [MagicMock(text=schema_text)]

    fake_session = AsyncMock()
    fake_session.call_tool.return_value = fake_result

    with patch("eaa.agent.mcp_client._open_session") as mock_open_session:
        mock_open_session.return_value.__aenter__.return_value = fake_session

        call = mcp_client._make_tool_caller("http://127.0.0.1:8001/mcp", "get_schema")
        result = await call()

    assert result == schema_text
    assert "\\n" not in result  # real newlines, not an escaped dict-repr
    assert not result.startswith("{'result'")  # no leftover wrapper


@pytest.mark.asyncio
async def test_tool_call_falls_back_to_text_join_when_structured_content_is_none() -> None:
    # e.g. get_schema's server-side implementation returns a plain str, not
    # structured data, so structured_content comes back None.
    fake_result = MagicMock()
    fake_result.structured_content = None
    fake_result.content = [MagicMock(text="plain schema description")]

    fake_session = AsyncMock()
    fake_session.call_tool.return_value = fake_result

    with patch("eaa.agent.mcp_client._open_session") as mock_open_session:
        mock_open_session.return_value.__aenter__.return_value = fake_session

        call = mcp_client._make_tool_caller("http://127.0.0.1:8001/mcp", "get_schema")
        result = await call()

    assert result == "plain schema description"


@pytest.mark.asyncio
async def test_tool_call_returns_clean_error_string_when_mcp_server_is_unreachable() -> None:
    with patch("eaa.agent.mcp_client._open_session") as mock_open_session:
        mock_open_session.return_value.__aenter__.side_effect = ConnectionError("down")

        call = mcp_client._make_tool_caller("http://127.0.0.1:8001/mcp", "get_schema")
        result = await call()

    assert isinstance(result, str)
    assert "MCP tool call failed" in result


def test_load_mcp_tools_runs_the_async_version_synchronously() -> None:
    with patch("eaa.agent.mcp_client.get_mcp_tools") as mock_get:

        async def _fake(url: str) -> list[str]:
            return ["tool_a"]

        mock_get.side_effect = _fake

        tools = mcp_client.load_mcp_tools("http://127.0.0.1:8001/mcp")

    assert tools == ["tool_a"]
