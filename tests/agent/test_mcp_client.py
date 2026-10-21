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


def test_load_mcp_tools_runs_the_async_version_synchronously() -> None:
    with patch("eaa.agent.mcp_client.get_mcp_tools") as mock_get:

        async def _fake(url: str) -> list[str]:
            return ["tool_a"]

        mock_get.side_effect = _fake

        tools = mcp_client.load_mcp_tools("http://127.0.0.1:8001/mcp")

    assert tools == ["tool_a"]
