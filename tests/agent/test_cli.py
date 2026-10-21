import uuid
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from eaa.agent import cli


def test_repl_prints_answers_until_exit(capsys) -> None:
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = {
        "messages": [HumanMessage(content="hi"), AIMessage(content="hello!")]
    }

    with (
        patch("eaa.agent.cli.build_agent", return_value=fake_agent),
        patch("eaa.agent.cli.load_mcp_tools", return_value=[]),
        patch("eaa.agent.cli.get_checkpointer", return_value=MagicMock()),
        patch("builtins.input", side_effect=["hi", "exit"]),
    ):
        cli.main()

    captured = capsys.readouterr()
    assert "hello!" in captured.out


def test_repl_uses_one_thread_id_for_the_whole_session() -> None:
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = {
        "messages": [HumanMessage(content="hi"), AIMessage(content="ok")]
    }

    with (
        patch("eaa.agent.cli.build_agent", return_value=fake_agent),
        patch("eaa.agent.cli.load_mcp_tools", return_value=[]),
        patch("eaa.agent.cli.get_checkpointer", return_value=MagicMock()),
        patch("builtins.input", side_effect=["one", "two", "exit"]),
    ):
        cli.main()

    first_thread_id = fake_agent.invoke.call_args_list[0].kwargs["config"]["configurable"]["thread_id"]
    second_thread_id = fake_agent.invoke.call_args_list[1].kwargs["config"]["configurable"]["thread_id"]
    assert first_thread_id == second_thread_id
    assert uuid.UUID(first_thread_id)  # it's a real UUID


def test_repl_continues_after_a_failed_invocation(capsys) -> None:
    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = [
        Exception("boom"),
        {"messages": [HumanMessage(content="hi"), AIMessage(content="ok")]},
    ]

    with (
        patch("eaa.agent.cli.build_agent", return_value=fake_agent),
        patch("eaa.agent.cli.load_mcp_tools", return_value=[]),
        patch("eaa.agent.cli.get_checkpointer", return_value=MagicMock()),
        patch("builtins.input", side_effect=["one", "two", "exit"]),
    ):
        cli.main()

    captured = capsys.readouterr()
    assert "boom" in captured.out
    assert "ok" in captured.out
    assert fake_agent.invoke.call_count == 2
