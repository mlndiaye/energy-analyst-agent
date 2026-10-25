"""The Phase 3 benchmark's fixed question set: 5 lookup, 5 aggregation/comparison,
5 multi-tool (warehouse + forecast) questions, each with a ground-truth function
computed live against the real warehouse/forecast API rather than a hardcoded
number -- stays correct as the warehouse is backfilled with more data over time.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import duckdb

from eaa.mcp.forecast_client import fetch_forecast_history, fetch_latest_forecast

Category = Literal["lookup", "aggregation", "multi_tool"]


@dataclass(frozen=True)
class BenchmarkQuestion:
    id: str
    category: Category
    question: str
    ground_truth_fn: Callable[[duckdb.DuckDBPyConnection], float]
    tolerance: float
    expected_tools: list[str]


def _sql_ground_truth(sql: str) -> Callable[[duckdb.DuckDBPyConnection], float]:
    """Wrap a single-value SQL query as a ground_truth_fn."""

    def _fn(con: duckdb.DuckDBPyConnection) -> float:
        return con.execute(sql).fetchone()[0]

    return _fn


# --- Lookup (single tool, simple fact) ---------------------------------
#
# "Most recently recorded" queries below filter out NULL: eco2mix's hourly
# resample fills a not-yet-reported ("gap") hour with NULL rather than
# omitting the row (see ingestion/eco2mix.py), so an unfiltered
# `ORDER BY datetime DESC LIMIT 1` can land on that placeholder instead of
# the latest real value.

_LOOKUP_QUESTIONS = [
    BenchmarkQuestion(
        id="lookup-1",
        category="lookup",
        question="What was the most recently recorded hourly consumption value, in MW?",
        ground_truth_fn=_sql_ground_truth(
            "SELECT consumption_mw FROM consumption_hourly "
            "WHERE consumption_mw IS NOT NULL ORDER BY datetime DESC LIMIT 1"
        ),
        tolerance=0.5,
        expected_tools=["run_sql_query"],
    ),
    BenchmarkQuestion(
        id="lookup-2",
        category="lookup",
        question="What was the most recently recorded hourly nuclear production value, in MW?",
        ground_truth_fn=_sql_ground_truth(
            "SELECT production_mw FROM production_by_source_hourly "
            "WHERE source = 'nuclear' AND production_mw IS NOT NULL "
            "ORDER BY datetime DESC LIMIT 1"
        ),
        tolerance=0.5,
        expected_tools=["run_sql_query"],
    ),
    BenchmarkQuestion(
        id="lookup-3",
        category="lookup",
        question="What was the most recently recorded hourly wind production value, in MW?",
        ground_truth_fn=_sql_ground_truth(
            "SELECT production_mw FROM production_by_source_hourly "
            "WHERE source = 'wind' AND production_mw IS NOT NULL "
            "ORDER BY datetime DESC LIMIT 1"
        ),
        tolerance=0.5,
        expected_tools=["run_sql_query"],
    ),
    BenchmarkQuestion(
        id="lookup-4",
        category="lookup",
        question="What was the most recently recorded day-ahead electricity price, in EUR/MWh?",
        ground_truth_fn=_sql_ground_truth(
            "SELECT price_eur_mwh FROM day_ahead_prices_hourly "
            "WHERE price_eur_mwh IS NOT NULL ORDER BY datetime DESC LIMIT 1"
        ),
        tolerance=0.5,
        expected_tools=["run_sql_query"],
    ),
    BenchmarkQuestion(
        id="lookup-5",
        category="lookup",
        question="How many hourly consumption records are stored in the warehouse in total?",
        ground_truth_fn=_sql_ground_truth("SELECT COUNT(*) FROM consumption_hourly"),
        tolerance=0.5,
        expected_tools=["run_sql_query"],
    ),
]

# --- Aggregation / comparison (single tool, GROUP BY / ORDER BY) -------

_AGGREGATION_QUESTIONS = [
    BenchmarkQuestion(
        id="aggregation-1",
        category="aggregation",
        question=(
            "What was the average hourly consumption over the most recent 7 days of data, in MW?"
        ),
        ground_truth_fn=_sql_ground_truth(
            "SELECT AVG(consumption_mw) FROM consumption_hourly "
            "WHERE datetime >= (SELECT MAX(datetime) FROM consumption_hourly) - INTERVAL 7 DAY"
        ),
        tolerance=50.0,
        expected_tools=["run_sql_query"],
    ),
    BenchmarkQuestion(
        id="aggregation-2",
        category="aggregation",
        question=(
            "Among all production sources, what was the highest average hourly "
            "production over the most recent 30 days of data, in MW?"
        ),
        ground_truth_fn=_sql_ground_truth(
            "SELECT AVG(production_mw) AS avg_mw FROM production_by_source_hourly "
            "WHERE datetime >= (SELECT MAX(datetime) FROM production_by_source_hourly) - INTERVAL 30 DAY "
            "GROUP BY source ORDER BY avg_mw DESC LIMIT 1"
        ),
        tolerance=50.0,
        expected_tools=["run_sql_query"],
    ),
    BenchmarkQuestion(
        id="aggregation-3",
        category="aggregation",
        question=(
            "What was the maximum hourly day-ahead price over the most recent 30 "
            "days of data, in EUR/MWh?"
        ),
        ground_truth_fn=_sql_ground_truth(
            "SELECT MAX(price_eur_mwh) FROM day_ahead_prices_hourly "
            "WHERE datetime >= (SELECT MAX(datetime) FROM day_ahead_prices_hourly) - INTERVAL 30 DAY"
        ),
        tolerance=0.5,
        expected_tools=["run_sql_query"],
    ),
    BenchmarkQuestion(
        id="aggregation-4",
        category="aggregation",
        question=(
            "What was the minimum hourly consumption over the most recent 30 days of data, in MW?"
        ),
        ground_truth_fn=_sql_ground_truth(
            "SELECT MIN(consumption_mw) FROM consumption_hourly "
            "WHERE datetime >= (SELECT MAX(datetime) FROM consumption_hourly) - INTERVAL 30 DAY"
        ),
        tolerance=0.5,
        expected_tools=["run_sql_query"],
    ),
    BenchmarkQuestion(
        id="aggregation-5",
        category="aggregation",
        question=(
            "What was the total (summed) hourly solar production over the most "
            "recent 7 days of data, in MW?"
        ),
        ground_truth_fn=_sql_ground_truth(
            "SELECT SUM(production_mw) FROM production_by_source_hourly "
            "WHERE source = 'solar' "
            "AND datetime >= (SELECT MAX(datetime) FROM production_by_source_hourly) - INTERVAL 7 DAY"
        ),
        tolerance=100.0,
        expected_tools=["run_sql_query"],
    ),
]

# --- Multi-tool (warehouse + forecast) ----------------------------------


def _latest_q50_first_hour() -> float:
    # Read fresh, not from a module-level constant: this module is imported
    # (and any such constant captured) before the benchmark CLI's
    # load_dotenv() call, so a stale default would silently ignore .env.
    forecast_api_url = os.environ.get("FORECAST_API_URL", "http://localhost:8000")
    latest = fetch_latest_forecast(forecast_api_url)
    return latest[0]["q50_pred"]


def _history_rte_pred_values() -> list[float]:
    forecast_api_url = os.environ.get("FORECAST_API_URL", "http://localhost:8000")
    history = fetch_forecast_history(forecast_api_url)
    return [row["rte_pred"] for row in history]


def _m1_ground_truth(con: duckdb.DuckDBPyConnection) -> float:
    forecast_q50 = _latest_q50_first_hour()
    avg_recent = con.execute(
        "SELECT AVG(consumption_mw) FROM consumption_hourly "
        "WHERE datetime >= (SELECT MAX(datetime) FROM consumption_hourly) - INTERVAL 7 DAY"
    ).fetchone()[0]
    return forecast_q50 - avg_recent


def _m2_ground_truth(con: duckdb.DuckDBPyConnection) -> float:
    forecast_q50 = _latest_q50_first_hour()
    min_recent = con.execute(
        "SELECT MIN(consumption_mw) FROM consumption_hourly "
        "WHERE datetime >= (SELECT MAX(datetime) FROM consumption_hourly) - INTERVAL 30 DAY"
    ).fetchone()[0]
    return forecast_q50 - min_recent


def _m3_ground_truth(con: duckdb.DuckDBPyConnection) -> float:
    forecast_q50 = _latest_q50_first_hour()
    latest_actual = con.execute(
        "SELECT consumption_mw FROM consumption_hourly ORDER BY datetime DESC LIMIT 1"
    ).fetchone()[0]
    return forecast_q50 + latest_actual


def _m4_ground_truth(con: duckdb.DuckDBPyConnection) -> float:
    rte_values = _history_rte_pred_values()
    max_rte = max(rte_values)
    max_recent = con.execute(
        "SELECT MAX(consumption_mw) FROM consumption_hourly "
        "WHERE datetime >= (SELECT MAX(datetime) FROM consumption_hourly) - INTERVAL 30 DAY"
    ).fetchone()[0]
    return max_rte - max_recent


def _m5_ground_truth(con: duckdb.DuckDBPyConnection) -> float:
    rte_values = _history_rte_pred_values()
    avg_rte = sum(rte_values) / len(rte_values)
    latest_actual = con.execute(
        "SELECT consumption_mw FROM consumption_hourly ORDER BY datetime DESC LIMIT 1"
    ).fetchone()[0]
    return latest_actual - avg_rte


_MULTI_TOOL_QUESTIONS = [
    BenchmarkQuestion(
        id="multi-tool-1",
        category="multi_tool",
        question=(
            "What is the difference between tomorrow's forecasted median (q50) "
            "consumption for the first hour and the average actual hourly "
            "consumption over the most recent 7 days of data, in MW? (forecast "
            "minus average actual)"
        ),
        ground_truth_fn=_m1_ground_truth,
        tolerance=200.0,
        expected_tools=["get_latest_forecast", "run_sql_query"],
    ),
    BenchmarkQuestion(
        id="multi-tool-2",
        category="multi_tool",
        question=(
            "What is the difference between tomorrow's forecasted median (q50) "
            "consumption for the first hour and the minimum actual hourly "
            "consumption over the most recent 30 days of data, in MW? (forecast "
            "minus minimum actual)"
        ),
        ground_truth_fn=_m2_ground_truth,
        tolerance=200.0,
        expected_tools=["get_latest_forecast", "run_sql_query"],
    ),
    BenchmarkQuestion(
        id="multi-tool-3",
        category="multi_tool",
        question=(
            "What is the sum of tomorrow's forecasted median (q50) consumption "
            "for the first hour and the most recently recorded actual hourly "
            "consumption value, in MW?"
        ),
        ground_truth_fn=_m3_ground_truth,
        tolerance=200.0,
        expected_tools=["get_latest_forecast", "run_sql_query"],
    ),
    BenchmarkQuestion(
        id="multi-tool-4",
        category="multi_tool",
        question=(
            "What is the difference between the maximum RTE day-ahead forecast "
            "value across the available forecast history and the maximum actual "
            "hourly consumption over the most recent 30 days of data, in MW? "
            "(max RTE forecast minus max actual)"
        ),
        ground_truth_fn=_m4_ground_truth,
        tolerance=200.0,
        expected_tools=["get_forecast_history", "run_sql_query"],
    ),
    BenchmarkQuestion(
        id="multi-tool-5",
        category="multi_tool",
        question=(
            "What is the difference between the most recently recorded actual "
            "hourly consumption value and the average RTE day-ahead forecast "
            "value across the available forecast history, in MW? (most recent "
            "actual minus average RTE forecast)"
        ),
        ground_truth_fn=_m5_ground_truth,
        tolerance=200.0,
        expected_tools=["get_forecast_history", "run_sql_query"],
    ),
]

QUESTIONS: list[BenchmarkQuestion] = (
    _LOOKUP_QUESTIONS + _AGGREGATION_QUESTIONS + _MULTI_TOOL_QUESTIONS
)
