from unittest.mock import AsyncMock, MagicMock, patch

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
        mock_agent.ainvoke = AsyncMock(return_value=_fake_agent_result("42 TWh"))

        client = TestClient(app)
        response = client.post("/ask", json={"question": "yesterday's consumption?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "42 TWh"
    assert body["session_id"]
    assert body["tool_calls"] == []


def test_ask_reuses_a_provided_session_id() -> None:
    with patch("eaa.agent.api.AGENT") as mock_agent:
        mock_agent.ainvoke = AsyncMock(return_value=_fake_agent_result("ok"))

        client = TestClient(app)
        response = client.post("/ask", json={"question": "hi", "session_id": "existing-session"})

    assert response.json()["session_id"] == "existing-session"
    call_config = mock_agent.ainvoke.call_args.kwargs["config"]
    assert call_config["configurable"]["thread_id"] == "existing-session"


def test_lifespan_shutdown_closes_the_checkpointer_connection() -> None:
    with patch("eaa.agent.api._checkpointer") as mock_checkpointer:
        mock_checkpointer.conn.close = AsyncMock()
        with TestClient(app) as client:
            client.get("/health")
        mock_checkpointer.conn.close.assert_called_once()


def test_ask_returns_502_when_agent_invocation_fails() -> None:
    with patch("eaa.agent.api.AGENT") as mock_agent:
        mock_agent.ainvoke = AsyncMock(side_effect=Exception("boom"))

        client = TestClient(app)
        response = client.post("/ask", json={"question": "hi"})

    assert response.status_code == 502
    assert "boom" in response.json()["detail"]


def test_ask_rejects_an_empty_question() -> None:
    with patch("eaa.agent.api.AGENT") as mock_agent:
        mock_agent.ainvoke = AsyncMock()
        client = TestClient(app)
        response = client.post("/ask", json={"question": ""})

    assert response.status_code == 422
    mock_agent.ainvoke.assert_not_called()
