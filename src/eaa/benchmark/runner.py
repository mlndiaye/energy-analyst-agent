"""Orchestrates the benchmark: one agent.ainvoke() per (model, question) pair,
scoring each run's accuracy, tool use, cost, and latency.

Async, not sync: the MCP tools built in mcp_client.py are coroutine-only, so a
sync agent.invoke() raises NotImplementedError the moment any model (Gemini or
an Ollama model) calls one -- which is every real run, since the whole point
of these questions is to make the agent call a tool.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import duckdb

from eaa.agent.graph import build_agent
from eaa.agent.tool_trace import extract_tool_calls
from eaa.benchmark.cost import compute_cost
from eaa.benchmark.questions import BenchmarkQuestion
from eaa.benchmark.scoring import score_accuracy, score_tool_use


@dataclass
class RunResult:
    question_id: str
    category: str
    model_key: str
    correct: bool
    expected: float
    extracted: float | None
    all_expected_tools_called: bool
    called_tools: list[str]
    cost_usd: float
    latency_seconds: float


async def run_one(
    question: BenchmarkQuestion,
    model_key: str,
    agent: Any,
    con: duckdb.DuckDBPyConnection | None,
    callbacks: list | None = None,
) -> RunResult:
    """Run a single (model, question) pair and score it."""
    start = time.perf_counter()
    config: dict = {}
    if callbacks:
        config["callbacks"] = callbacks
        config["metadata"] = {
            "model": model_key,
            "question_id": question.id,
            "category": question.category,
        }
    result = await agent.ainvoke(
        {"messages": [("user", question.question)]},
        config=config or None,
    )
    latency = time.perf_counter() - start

    messages = result["messages"]
    answer_text = messages[-1].content
    tool_calls = extract_tool_calls(messages)

    accuracy = score_accuracy(question, con, answer_text)
    tool_use = score_tool_use(question, tool_calls)
    cost = compute_cost(model_key, messages)

    return RunResult(
        question_id=question.id,
        category=question.category,
        model_key=model_key,
        correct=accuracy["correct"],
        expected=accuracy["expected"],
        extracted=accuracy["extracted"],
        all_expected_tools_called=tool_use["all_expected_called"],
        called_tools=tool_use["called_tools"],
        cost_usd=cost,
        latency_seconds=latency,
    )


async def run_benchmark(
    models: dict[str, Any],
    questions: list[BenchmarkQuestion],
    tools: list,
    con: duckdb.DuckDBPyConnection | None,
    callbacks: list | None = None,
) -> list[RunResult]:
    """Build one agent per model (no conversation memory needed -- each run is
    a single, independent question) and run every question through each."""
    results: list[RunResult] = []
    for model_key, model in models.items():
        agent = build_agent(tools=tools, model=model)
        for question in questions:
            results.append(await run_one(question, model_key, agent, con, callbacks))
    return results
