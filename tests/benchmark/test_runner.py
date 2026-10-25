from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from eaa.benchmark import runner
from eaa.benchmark.questions import BenchmarkQuestion


def _question() -> BenchmarkQuestion:
    return BenchmarkQuestion(
        id="q1",
        category="lookup",
        question="What is the value?",
        ground_truth_fn=lambda con: 42.0,
        tolerance=1.0,
        expected_tools=["run_sql_query"],
    )


async def test_run_one_scores_accuracy_tool_use_cost_and_latency() -> None:
    fake_agent = MagicMock()
    answer = AIMessage(
        content="The value is 42.0.",
        tool_calls=[{"name": "run_sql_query", "args": {"query": "SELECT 1"}, "id": "c1"}],
        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
    )
    fake_agent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                HumanMessage(content="What is the value?"),
                answer,
            ]
        }
    )

    result = await runner.run_one(_question(), "gemini-3.5-flash", fake_agent, con=None)

    assert result.question_id == "q1"
    assert result.category == "lookup"
    assert result.model_key == "gemini-3.5-flash"
    assert result.correct is True
    assert result.all_expected_tools_called is True
    assert result.cost_usd > 0
    assert result.latency_seconds >= 0


async def test_run_one_scores_a_multi_part_gemini_style_answer() -> None:
    # Gemini's adaptive thinking returns AIMessage.content as a list of typed
    # blocks (e.g. {"type": "thinking", ...} + {"type": "text", ...}) rather
    # than a plain string. Scoring must read the text part, not crash trying
    # to regex-search a list.
    fake_agent = MagicMock()
    answer = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Let me compute this..."},
            {"type": "text", "text": "The value is 42.0."},
        ],
        tool_calls=[{"name": "run_sql_query", "args": {"query": "SELECT 1"}, "id": "c1"}],
        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
    )
    fake_agent.ainvoke = AsyncMock(
        return_value={"messages": [HumanMessage(content="What is the value?"), answer]}
    )

    result = await runner.run_one(_question(), "gemini-3.5-flash", fake_agent, con=None)

    assert result.error is None
    assert result.correct is True
    assert result.extracted == 42.0


async def test_run_benchmark_iterates_every_model_and_question() -> None:
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(
        return_value={"messages": [HumanMessage(content="q"), AIMessage(content="100")]}
    )

    questions = [_question(), _question()]
    models = {"model-a": object(), "model-b": object()}

    with patch("eaa.benchmark.runner.build_agent", return_value=fake_agent):
        results = await runner.run_benchmark(models, questions, tools=[], con=None)

    assert len(results) == len(models) * len(questions)
    assert {r.model_key for r in results} == {"model-a", "model-b"}


async def test_run_benchmark_passes_a_retry_middleware_when_building_the_agent() -> None:
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(
        return_value={"messages": [HumanMessage(content="q"), AIMessage(content="100")]}
    )

    with patch("eaa.benchmark.runner.build_agent", return_value=fake_agent) as mock_build_agent:
        await runner.run_benchmark({"model-a": object()}, [_question()], tools=[], con=None)

    assert len(mock_build_agent.call_args.kwargs["middleware"]) == 1


async def test_run_one_returns_an_error_result_instead_of_raising_when_the_agent_fails() -> None:
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))

    result = await runner.run_one(_question(), "gemini-3.5-flash", fake_agent, con=None)

    assert result.correct is False
    assert result.extracted is None
    assert result.all_expected_tools_called is False
    assert result.called_tools == []
    assert result.cost_usd == 0.0
    assert result.latency_seconds >= 0
    assert result.error is not None and "boom" in result.error


async def test_run_benchmark_continues_with_other_questions_after_one_raises() -> None:
    fake_agent = MagicMock()
    fake_agent.ainvoke = AsyncMock(
        side_effect=[
            RuntimeError("boom"),
            {"messages": [HumanMessage(content="q"), AIMessage(content="42")]},
        ]
    )

    questions = [_question(), _question()]
    with patch("eaa.benchmark.runner.build_agent", return_value=fake_agent):
        results = await runner.run_benchmark({"model-a": object()}, questions, tools=[], con=None)

    assert len(results) == 2
    assert results[0].error is not None
    assert results[1].error is None
    assert results[1].correct is True
