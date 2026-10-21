"""Interactive CLI for the energy analyst agent."""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv

from eaa.agent.graph import build_agent
from eaa.agent.mcp_client import load_mcp_tools
from eaa.agent.memory import get_checkpointer


def main() -> None:
    load_dotenv()
    mcp_url = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")

    checkpointer = get_checkpointer()
    agent = build_agent(tools=load_mcp_tools(mcp_url), checkpointer=checkpointer)
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
            result = agent.invoke({"messages": [("user", question)]}, config=config)
        except Exception as exc:  # noqa: BLE001 -- REPL should recover and keep prompting, not propagate
            print(f"Error: {exc}")
            continue
        print(result["messages"][-1].content)

    checkpointer.conn.close()


if __name__ == "__main__":
    main()
