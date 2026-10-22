import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from eaa.agent import cli


def _fake_checkpointer() -> MagicMock:
    checkpointer = MagicMock()
    checkpointer.conn.close = AsyncMock()
    return checkpointer


def test_repl_prints_answers_until_exit(capsys) -> None:
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(
        return_value={"messages": [HumanMessage(content="hi"), AIMessage(content="hello!")]}
    )

    with (
        patch("eaa.agent.cli.build_agent", return_value=fake_agent),
        patch("eaa.agent.cli.get_mcp_tools", AsyncMock(return_value=[])),
        patch("eaa.agent.cli.get_checkpointer", AsyncMock(return_value=_fake_checkpointer())),
        patch("builtins.input", side_effect=["hi", "exit"]),
    ):
        cli.main()

    captured = capsys.readouterr()
    assert "hello!" in captured.out


def test_repl_uses_one_thread_id_for_the_whole_session() -> None:
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(
        return_value={"messages": [HumanMessage(content="hi"), AIMessage(content="ok")]}
    )

    with (
        patch("eaa.agent.cli.build_agent", return_value=fake_agent),
        patch("eaa.agent.cli.get_mcp_tools", AsyncMock(return_value=[])),
        patch("eaa.agent.cli.get_checkpointer", AsyncMock(return_value=_fake_checkpointer())),
        patch("builtins.input", side_effect=["one", "two", "exit"]),
    ):
        cli.main()

    first_thread_id = fake_agent.ainvoke.call_args_list[0].kwargs["config"]["configurable"][
        "thread_id"
    ]
    second_thread_id = fake_agent.ainvoke.call_args_list[1].kwargs["config"]["configurable"][
        "thread_id"
    ]
    assert first_thread_id == second_thread_id
    assert uuid.UUID(first_thread_id)  # it's a real UUID


def test_repl_continues_after_a_failed_invocation(capsys) -> None:
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(
        side_effect=[
            Exception("boom"),
            {"messages": [HumanMessage(content="hi"), AIMessage(content="ok")]},
        ]
    )

    with (
        patch("eaa.agent.cli.build_agent", return_value=fake_agent),
        patch("eaa.agent.cli.get_mcp_tools", AsyncMock(return_value=[])),
        patch("eaa.agent.cli.get_checkpointer", AsyncMock(return_value=_fake_checkpointer())),
        patch("builtins.input", side_effect=["one", "two", "exit"]),
    ):
        cli.main()

    captured = capsys.readouterr()
    assert "boom" in captured.out
    assert "ok" in captured.out
    assert fake_agent.ainvoke.call_count == 2
