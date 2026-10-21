from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from eaa.agent import tool_trace


def test_extract_tool_calls_returns_name_args_and_result() -> None:
    messages = [
        HumanMessage(content="What was yesterday's consumption?"),
        AIMessage(
            content="",
            tool_calls=[{"name": "run_sql_query", "args": {"query": "SELECT 1"}, "id": "call_1"}],
        ),
        ToolMessage(content="[{'x': 1}]", tool_call_id="call_1", name="run_sql_query"),
        AIMessage(content="It was 1."),
    ]

    calls = tool_trace.extract_tool_calls(messages)

    assert calls == [
        {"name": "run_sql_query", "args": {"query": "SELECT 1"}, "result": "[{'x': 1}]"}
    ]


def test_extract_tool_calls_returns_empty_list_when_no_tools_used() -> None:
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]

    assert tool_trace.extract_tool_calls(messages) == []
