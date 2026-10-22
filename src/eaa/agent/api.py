"""FastAPI service exposing the agent as POST /ask."""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from eaa.agent.graph import build_agent
from eaa.agent.mcp_client import load_mcp_tools
from eaa.agent.memory import get_checkpointer
from eaa.agent.tool_trace import extract_tool_calls

load_dotenv()

_MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")

# asyncio.run(), not a bare await: this module-level init runs at import time,
# before uvicorn's event loop exists, so there's no running loop to nest
# into (same reasoning as load_mcp_tools's own internal asyncio.run()).
_checkpointer = asyncio.run(get_checkpointer())
AGENT = build_agent(
    tools=load_mcp_tools(_MCP_SERVER_URL),
    checkpointer=_checkpointer,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await _checkpointer.conn.close()


app = FastAPI(title="energy-analyst-agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    session_id: str | None = None


class ToolCall(BaseModel):
    name: str
    args: dict
    result: object


class AskResponse(BaseModel):
    answer: str
    session_id: str
    tool_calls: list[ToolCall]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask")
async def ask(request: AskRequest) -> AskResponse:
    session_id = request.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    try:
        # ainvoke, not invoke: the MCP tools are coroutine-only (see
        # mcp_client.py), so a sync AGENT.invoke() raises NotImplementedError
        # the moment the model calls one.
        result = await AGENT.ainvoke({"messages": [("user", request.question)]}, config=config)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"agent invocation failed: {exc}") from exc

    messages = result["messages"]

    return AskResponse(
        answer=messages[-1].content,
        session_id=session_id,
        tool_calls=extract_tool_calls(messages),
    )
