from unittest.mock import patch

import duckdb

from eaa.benchmark import questions
from eaa.benchmark.questions import QUESTIONS


def _find(question_id: str):
    return next(q for q in QUESTIONS if q.id == question_id)


def test_there_are_fifteen_questions() -> None:
    assert len(QUESTIONS) == 15


def test_five_questions_per_category() -> None:
    categories = [q.category for q in QUESTIONS]
    assert categories.count("lookup") == 5
    assert categories.count("aggregation") == 5
    assert categories.count("multi_tool") == 5


def test_all_question_ids_are_unique() -> None:
    ids = [q.id for q in QUESTIONS]
    assert len(ids) == len(set(ids))


def test_every_question_has_a_callable_ground_truth_fn() -> None:
    for q in QUESTIONS:
        assert callable(q.ground_truth_fn)


def test_every_question_has_at_least_one_expected_tool() -> None:
    for q in QUESTIONS:
        assert len(q.expected_tools) >= 1


def test_multi_tool_questions_expect_two_distinct_tools() -> None:
    for q in QUESTIONS:
        if q.category == "multi_tool":
            assert len(set(q.expected_tools)) == 2


def test_latest_q50_first_hour_reads_forecast_api_url_at_call_time(
    monkeypatch,
) -> None:
    # questions.py is imported once, well before a benchmark run sets
    # FORECAST_API_URL from .env -- a module-level constant captured at
    # import time would silently keep using whatever (possibly wrong)
    # default was in effect then. Ground truth must read the env var fresh.
    monkeypatch.setenv("FORECAST_API_URL", "http://example-live-value:9999")
    with patch(
        "eaa.benchmark.questions.fetch_latest_forecast", return_value=[{"q50_pred": 1.0}]
    ) as mock_fetch:
        questions._latest_q50_first_hour()

    assert mock_fetch.call_args.args[0] == "http://example-live-value:9999"


def test_history_rte_pred_values_reads_forecast_api_url_at_call_time(monkeypatch) -> None:
    monkeypatch.setenv("FORECAST_API_URL", "http://example-live-value:9999")
    with patch("eaa.benchmark.questions.fetch_forecast_history", return_value=[]) as mock_fetch:
        questions._history_rte_pred_values()

    assert mock_fetch.call_args.args[0] == "http://example-live-value:9999"


# eco2mix's hourly resample fills a not-yet-reported ("gap") hour with NULL
# rather than omitting the row (see ingestion/eco2mix.py), so the very latest
# row in consumption_hourly / production_by_source_hourly can be NULL. A
# "most recently recorded" question should skip that placeholder row and
# return the latest *actual* value instead.


def test_lookup_1_ground_truth_skips_a_null_latest_hour() -> None:
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE consumption_hourly (datetime TIMESTAMP, consumption_mw DOUBLE)")
    con.execute(
        "INSERT INTO consumption_hourly VALUES "
        "('2026-01-01 10:00', 45000.0), ('2026-01-01 11:00', NULL)"
    )
    assert _find("lookup-1").ground_truth_fn(con) == 45000.0


def test_lookup_2_ground_truth_skips_a_null_latest_hour() -> None:
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE production_by_source_hourly "
        "(datetime TIMESTAMP, source VARCHAR, production_mw DOUBLE)"
    )
    con.execute(
        "INSERT INTO production_by_source_hourly VALUES "
        "('2026-01-01 10:00', 'nuclear', 30000.0), ('2026-01-01 11:00', 'nuclear', NULL)"
    )
    assert _find("lookup-2").ground_truth_fn(con) == 30000.0


def test_lookup_3_ground_truth_skips_a_null_latest_hour() -> None:
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE production_by_source_hourly "
        "(datetime TIMESTAMP, source VARCHAR, production_mw DOUBLE)"
    )
    con.execute(
        "INSERT INTO production_by_source_hourly VALUES "
        "('2026-01-01 10:00', 'wind', 5000.0), ('2026-01-01 11:00', 'wind', NULL)"
    )
    assert _find("lookup-3").ground_truth_fn(con) == 5000.0
