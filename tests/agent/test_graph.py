from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage

from eaa.agent import graph


class _MessageCapturingHandler(BaseCallbackHandler):
    """Records every message batch sent to the chat model.

    `create_agent`'s `system_prompt` is applied only to the messages sent to
    the model for a given turn -- it is not merged into the graph's persisted
    `messages` state. So the only way to verify it was actually used is to
    capture what the model received, via the standard callback hook.
    """

    def __init__(self) -> None:
        self.message_batches: list[list[BaseMessage]] = []

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self.message_batches.extend(messages)


def test_build_agent_returns_a_final_ai_message() -> None:
    fake_model = GenericFakeChatModel(messages=iter([AIMessage(content="42 TWh")]))

    agent = graph.build_agent(tools=[], model=fake_model)
    result = agent.invoke({"messages": [("user", "What was yesterday's consumption?")]})

    final_message = result["messages"][-1]
    assert final_message.content == "42 TWh"


def test_build_agent_uses_the_system_prompt() -> None:
    fake_model = GenericFakeChatModel(messages=iter([AIMessage(content="ok")]))
    handler = _MessageCapturingHandler()

    agent = graph.build_agent(tools=[], model=fake_model)
    agent.invoke({"messages": [("user", "hi")]}, config={"callbacks": [handler]})

    sent_messages = [m for batch in handler.message_batches for m in batch]
    system_messages = [m for m in sent_messages if m.type == "system"]
    assert len(system_messages) == 1
    assert "power system" in system_messages[0].content.lower()
