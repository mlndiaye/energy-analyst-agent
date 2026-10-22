from pathlib import Path

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from eaa.agent import graph, memory


async def test_get_checkpointer_creates_a_working_sqlite_file(tmp_path: Path) -> None:
    db_path = tmp_path / "test_memory.sqlite"

    checkpointer = await memory.get_checkpointer(db_path)
    try:
        assert db_path.exists()
    finally:
        # aiosqlite runs a non-daemon background thread per connection that
        # only stops on conn.close() -- an unclosed one here would block
        # pytest's own process exit at interpreter shutdown.
        await checkpointer.conn.close()


async def test_get_checkpointer_persists_conversation_history_across_calls(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test_memory.sqlite"
    checkpointer = await memory.get_checkpointer(db_path)

    try:
        fake_model = GenericFakeChatModel(
            messages=iter([AIMessage(content="first answer"), AIMessage(content="second answer")])
        )
        agent = graph.build_agent(tools=[], model=fake_model, checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "thread-1"}}

        await agent.ainvoke({"messages": [("user", "first question")]}, config=config)
        second_result = await agent.ainvoke(
            {"messages": [("user", "second question")]}, config=config
        )

        contents = [m.content for m in second_result["messages"]]
        assert "first question" in contents
        assert "first answer" in contents
        assert "second question" in contents
        assert contents[-1] == "second answer"
    finally:
        # Same reason as the test above: close the background thread so it
        # doesn't outlive the test and block pytest's process exit.
        await checkpointer.conn.close()
