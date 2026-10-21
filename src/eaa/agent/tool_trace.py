"""Extracts a flat tool-call trace from a LangGraph run's message list."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


def extract_tool_calls(messages: list[BaseMessage]) -> list[dict]:
    """Pair each AIMessage tool call with its matching ToolMessage result."""
    results_by_id = {m.tool_call_id: m.content for m in messages if isinstance(m, ToolMessage)}

    calls = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            calls.append(
                {
                    "name": call["name"],
                    "args": call["args"],
                    "result": results_by_id.get(call["id"]),
                }
            )
    return calls
