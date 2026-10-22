"""Interactive CLI for the energy analyst agent."""

from __future__ import annotations

import asyncio
import os
import uuid

from dotenv import load_dotenv

from eaa.agent.graph import build_agent
from eaa.agent.mcp_client import get_mcp_tools
from eaa.agent.memory import get_checkpointer


async def _run() -> None:
    load_dotenv()
    mcp_url = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")

    checkpointer = await get_checkpointer()
    # get_mcp_tools (async), not load_mcp_tools (its sync asyncio.run()
    # wrapper): we're already inside the event loop started by main() below,
    # and asyncio.run() cannot be nested inside a running loop.
    agent = build_agent(tools=await get_mcp_tools(mcp_url), checkpointer=checkpointer)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("energy-analyst-agent -- type 'exit' or Ctrl+D to quit")
    while True:
        try:
            question = input("> ")
        except EOFError:
            print()
            break
        if question.strip().lower() == "exit":
            break

        try:
            # ainvoke, not invoke: the MCP tools are coroutine-only (see
            # mcp_client.py), so a sync agent.invoke() raises
            # NotImplementedError the moment the model calls one.
            result = await agent.ainvoke({"messages": [("user", question)]}, config=config)
        except Exception as exc:  # noqa: BLE001 -- REPL should recover and keep prompting, not propagate
            print(f"Error: {exc}")
            continue
        print(result["messages"][-1].content)

    await checkpointer.conn.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
