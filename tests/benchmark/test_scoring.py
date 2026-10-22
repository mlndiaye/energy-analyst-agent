from collections.abc import Callable
from dataclasses import dataclass

import duckdb
import pytest

from eaa.benchmark import scoring


@dataclass(frozen=True)
class _FakeQuestion:
    tolerance: float
    expected_tools: list[str]
    ground_truth_fn: Callable[[duckdb.DuckDBPyConnection], float]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The answer is 42.5 MW.", 42.5),
        ("It was -3 MW last hour.", -3.0),
        ("Approximately 1,234 MW was consumed.", 1.234),
        ("No numbers here.", None),
    ],
)
def test_extract_first_number(text: str, expected: float | None) -> None:
    assert scoring.extract_first_number(text) == expected


def test_score_accuracy_within_tolerance_is_correct() -> None:
    question = _FakeQuestion(tolerance=1.0, expected_tools=[], ground_truth_fn=lambda con: 100.0)
    result = scoring.score_accuracy(question, con=None, answer_text="The value is 100.5 MW.")
    assert result["correct"] is True
    assert result["expected"] == 100.0
    assert result["extracted"] == 100.5


def test_score_accuracy_outside_tolerance_is_incorrect() -> None:
    question = _FakeQuestion(tolerance=1.0, expected_tools=[], ground_truth_fn=lambda con: 100.0)
    result = scoring.score_accuracy(question, con=None, answer_text="The value is 150 MW.")
    assert result["correct"] is False


def test_score_accuracy_with_no_number_in_answer_is_incorrect() -> None:
    question = _FakeQuestion(tolerance=1.0, expected_tools=[], ground_truth_fn=lambda con: 100.0)
    result = scoring.score_accuracy(question, con=None, answer_text="I don't know.")
    assert result["correct"] is False
    assert result["extracted"] is None


def test_score_tool_use_all_expected_called() -> None:
    question = _FakeQuestion(
        tolerance=0, expected_tools=["run_sql_query"], ground_truth_fn=lambda con: 0
    )
    tool_calls = [{"name": "run_sql_query", "args": {}, "result": "ok"}]
    result = scoring.score_tool_use(question, tool_calls)
    assert result["all_expected_called"] is True
    assert result["missing_tools"] == []


def test_score_tool_use_missing_an_expected_tool() -> None:
    question = _FakeQuestion(
        tolerance=0,
        expected_tools=["run_sql_query", "get_latest_forecast"],
        ground_truth_fn=lambda con: 0,
    )
    tool_calls = [{"name": "run_sql_query", "args": {}, "result": "ok"}]
    result = scoring.score_tool_use(question, tool_calls)
    assert result["all_expected_called"] is False
    assert result["missing_tools"] == ["get_latest_forecast"]


def test_score_tool_use_tolerates_an_extra_unexpected_call() -> None:
    question = _FakeQuestion(
        tolerance=0, expected_tools=["run_sql_query"], ground_truth_fn=lambda con: 0
    )
    tool_calls = [
        {"name": "get_schema", "args": {}, "result": "ok"},
        {"name": "run_sql_query", "args": {}, "result": "ok"},
    ]
    result = scoring.score_tool_use(question, tool_calls)
    assert result["all_expected_called"] is True
