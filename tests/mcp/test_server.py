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
