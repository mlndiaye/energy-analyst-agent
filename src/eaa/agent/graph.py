"""Builds the LangGraph ReAct agent over the warehouse/forecast MCP tools."""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

SYSTEM_PROMPT = """\
You are an analyst of the French power system. Answer questions about electricity \
consumption, production mix, day-ahead prices, and forecasts using the tools \
available to you -- never rely on your own general knowledge for a number that a \
tool could provide, since your answers must be verifiable against real data.

If a tool call fails -- whether as a protocol-level error, or as a successful \
result whose payload is a dict containing an "error" key -- say clearly that the \
data wasn't available and why, rather than guessing or inventing a number.
"""


def default_model() -> BaseChatModel:
    """The default chat model for this agent: Claude, via Anthropic."""
    return init_chat_model("anthropic:claude-sonnet-4-5-20250929")


def build_agent(
    tools: list[BaseTool],
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Build the compiled ReAct agent graph."""
    return create_agent(
        model=model or default_model(),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
