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
from langchain.agents.middleware import ModelRetryMiddleware

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
    error: str | None = None


async def run_one(
    question: BenchmarkQuestion,
    model_key: str,
    agent: Any,
    con: duckdb.DuckDBPyConnection | None,
    callbacks: list | None = None,
) -> RunResult:
    """Run a single (model, question) pair and score it.

    A failure anywhere in the agent call (e.g. a provider error surviving
    ModelRetryMiddleware's retries) is caught and turned into a failed
    RunResult rather than raised, so one bad (model, question) pair doesn't
    abort the rest of the benchmark.
    """
    start = time.perf_counter()
    try:
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
        # .text, not .content: Gemini's adaptive thinking returns content as
        # a list of typed blocks ({"type": "thinking", ...}, {"type": "text",
        # ...}) rather than a plain string. .text is LangChain's own accessor
        # that extracts just the text parts, and works for a plain-string
        # content too (e.g. Ollama's).
        answer_text = messages[-1].text
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
    except Exception as exc:  # noqa: BLE001 -- one bad run must not abort the benchmark
        try:
            expected = question.ground_truth_fn(con)
        except Exception:  # noqa: BLE001 -- ground truth must still be reportable on failure
            expected = float("nan")
        return RunResult(
            question_id=question.id,
            category=question.category,
            model_key=model_key,
            correct=False,
            expected=expected,
            extracted=None,
            all_expected_tools_called=False,
            called_tools=[],
            cost_usd=0.0,
            latency_seconds=time.perf_counter() - start,
            error=f"{type(exc).__name__}: {exc}",
        )


async def run_benchmark(
    models: dict[str, Any],
    questions: list[BenchmarkQuestion],
    tools: list,
    con: duckdb.DuckDBPyConnection | None,
    callbacks: list | None = None,
) -> list[RunResult]:
    """Build one agent per model (no conversation memory needed -- each run is
    a single, independent question) and run every question through each.

    Each agent gets a ModelRetryMiddleware: free-tier Gemini hits a 5
    requests/minute quota (HTTP 429) well within a 15-question run, and
    without a retry the first rate limit error used to crash the whole
    benchmark rather than just that one call.
    """
    results: list[RunResult] = []
    for model_key, model in models.items():
        agent = build_agent(tools=tools, model=model, middleware=[ModelRetryMiddleware()])
        for question in questions:
            results.append(await run_one(question, model_key, agent, con, callbacks))
    return results
