from unittest.mock import MagicMock, patch

with (
    patch("eaa.agent.mcp_client.load_mcp_tools", return_value=[]),
    patch("eaa.agent.graph.build_agent", return_value=MagicMock()),
):
    from eaa.agent.api import app  # import must happen inside the patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage


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
        response = client.post("/ask", json={"question": "hi", "session_id": "existing-session"})

    assert response.json()["session_id"] == "existing-session"
    call_config = mock_agent.invoke.call_args.kwargs["config"]
    assert call_config["configurable"]["thread_id"] == "existing-session"


def test_lifespan_shutdown_closes_the_checkpointer_connection() -> None:
    with patch("eaa.agent.api._checkpointer") as mock_checkpointer:
        with TestClient(app) as client:
            client.get("/health")
        mock_checkpointer.conn.close.assert_called_once()
