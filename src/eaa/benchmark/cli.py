"""CLI entry point for the Phase 3 benchmark: `uv run eaa-benchmark`."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langfuse.langchain import CallbackHandler

from eaa import warehouse
from eaa.agent.mcp_client import load_mcp_tools
from eaa.benchmark.questions import QUESTIONS
from eaa.benchmark.report import render_markdown
from eaa.benchmark.runner import run_benchmark


def build_langfuse_callbacks() -> list | None:
    """Return a Langfuse callback list if credentials are configured, else None."""
    if not os.environ.get("LANGFUSE_PUBLIC_KEY") or not os.environ.get("LANGFUSE_SECRET_KEY"):
        return None
    return [CallbackHandler()]


def main() -> None:
    load_dotenv()

    mcp_url = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8001/mcp")
    tools = load_mcp_tools(mcp_url)
    con = warehouse.get_connection(read_only=True)

    models = {
        "claude-sonnet-5-5": init_chat_model("anthropic:claude-sonnet-5-5"),
        "ollama:llama3.2": init_chat_model("ollama:llama3.2"),
        "ollama:llama3.1:8b": init_chat_model("ollama:llama3.1:8b"),
    }

    callbacks = build_langfuse_callbacks()

    print(f"Running {len(models)} models x {len(QUESTIONS)} questions...")
    results = run_benchmark(models, QUESTIONS, tools, con, callbacks)
    con.close()

    markdown = render_markdown(results)
    print(markdown)

    Path("docs").mkdir(exist_ok=True)
    Path("docs/benchmark_report.md").write_text(markdown)
    Path("benchmark_results.json").write_text(json.dumps([asdict(r) for r in results], indent=2))
    print("\nWrote docs/benchmark_report.md and benchmark_results.json")


if __name__ == "__main__":
    main()
