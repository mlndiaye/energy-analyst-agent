from unittest.mock import MagicMock, patch

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


def test_run_one_scores_accuracy_tool_use_cost_and_latency() -> None:
    fake_agent = MagicMock()
    answer = AIMessage(
        content="The value is 42.0.",
        tool_calls=[{"name": "run_sql_query", "args": {"query": "SELECT 1"}, "id": "c1"}],
        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
    )
    fake_agent.invoke.return_value = {
        "messages": [
            HumanMessage(content="What is the value?"),
            answer,
        ]
    }

    result = runner.run_one(_question(), "claude-sonnet-5-5", fake_agent, con=None)

    assert result.question_id == "q1"
    assert result.category == "lookup"
    assert result.model_key == "claude-sonnet-5-5"
    assert result.correct is True
    assert result.all_expected_tools_called is True
    assert result.cost_usd > 0
    assert result.latency_seconds >= 0


def test_run_benchmark_iterates_every_model_and_question() -> None:
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = {
        "messages": [HumanMessage(content="q"), AIMessage(content="100")]
    }

    questions = [_question(), _question()]
    models = {"model-a": object(), "model-b": object()}

    with patch("eaa.benchmark.runner.build_agent", return_value=fake_agent):
        results = runner.run_benchmark(models, questions, tools=[], con=None)

    assert len(results) == len(models) * len(questions)
    assert {r.model_key for r in results} == {"model-a", "model-b"}
