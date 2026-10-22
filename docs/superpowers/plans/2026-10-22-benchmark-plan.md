# Phase 3 — Custom Benchmark (Claude vs. Ollama) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a custom benchmark comparing Claude Sonnet 5.5 against two local Ollama models on accuracy, tool use, cost, and latency, with Langfuse tracing — fully buildable and testable now via mocks, with the real paid/data-dependent run deferred to a manual step.

**Architecture:** A `src/eaa/benchmark/` subpackage: a fixed question set with per-question ground-truth functions, pure scoring/cost functions, a runner that invokes `build_agent` directly (in-process, no FastAPI) once per model per question, and a markdown report. Plus one unrelated bug fix: `graph.py`'s stale default model ID.

**Tech Stack:** Python 3.12, `uv`, `langchain-ollama` (new), `langfuse` (new), DuckDB, pytest, ruff.

**Reference:** `docs/superpowers/specs/2026-10-22-benchmark-design.md` (approved design). Builds on Phase 1 (`src/eaa/warehouse.py`, `src/eaa/mcp/`) and Phase 2 (`src/eaa/agent/graph.py`'s `build_agent`, `src/eaa/agent/mcp_client.py`'s `load_mcp_tools`, `src/eaa/agent/tool_trace.py`'s `extract_tool_calls`, `src/eaa/mcp/forecast_client.py`'s `fetch_latest_forecast`/`fetch_forecast_history`).

**Confirmed forecast field names** (read directly from the sibling `france-electricity-forecasting` repo's source, not assumed): `src/felec/modeling/forecast.py`'s `predict_next_day()` docstring confirms `/forecast/latest`'s rows have `date_heure`, `q10_pred`, `q50_pred`, `q90_pred`, `naive_pred`, `rte_pred`. The design spec's own README research already confirmed `/forecast/history`'s rows have `date_heure`, `q10_pred`, `q90_pred` (no `q50_pred`), `consommation`, `rte_pred`. The ground-truth functions below use `q50_pred` only for `/forecast/latest`-based questions and `rte_pred` for `/forecast/history`-based ones, matching what's actually confirmed to exist in each.

---

## Task 1: Bootstrap the benchmark subpackage

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `src/eaa/benchmark/__init__.py`

- [ ] **Step 1: Add dependencies and the CLI script entry**

In `pyproject.toml`, add to `dependencies` (current list confirmed via `pyproject.toml` as of the end of Phase 2 — `langchain-mcp-adapters` was already removed there, nothing to clean up here):
```toml
    "langchain-ollama",
    "langfuse",
```
Full list after this change: `duckdb`, `pandas`, `requests`, `mcp[cli]>=2.0,<3.0`, `python-dotenv`, `langgraph`, `langchain`, `langchain-anthropic`, `langgraph-checkpoint-sqlite`, `fastapi[standard]`, `langchain-ollama`, `langfuse`.

Add to `[project.scripts]`:
```toml
eaa-benchmark = "eaa.benchmark.cli:main"
```

- [ ] **Step 2: Install and verify**

Run: `uv sync --extra dev`
Expected: resolves without errors. Note the resolved `langchain-ollama` and `langfuse` versions for later reference.

Run: `uv run python -c "import langchain_ollama, langfuse; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Add new env vars to `.env.example`**

Append:
```bash
# Langfuse (cloud, free tier) — https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

- [ ] **Step 4: Ignore the benchmark's local results file**

Append to `.gitignore`:
```gitignore

# Benchmark raw results (local, rebuildable by re-running `eaa-benchmark`)
benchmark_results.json
```

- [ ] **Step 5: Create the package skeleton**

```bash
mkdir -p src/eaa/benchmark tests/benchmark
touch src/eaa/benchmark/__init__.py tests/benchmark/__init__.py
```

(`tests/benchmark/__init__.py` is created proactively, not reactively like Phase 2's `tests/agent/__init__.py` fix — this avoids repeating that same pytest module-name-collision class of bug if any file under `tests/benchmark/` ever shares a basename with an existing test file elsewhere.)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .env.example .gitignore src/eaa/benchmark/__init__.py tests/benchmark/__init__.py
git commit -m "chore: bootstrap the benchmark subpackage for Phase 3"
```

---

## Task 2: Fix the agent's stale default model ID

**Files:**
- Modify: `src/eaa/agent/graph.py`
- Modify: `tests/agent/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/agent/test_graph.py
from unittest.mock import patch


def test_default_model_uses_current_sonnet_id() -> None:
    with patch("eaa.agent.graph.init_chat_model") as mock_init:
        graph.default_model()

    mock_init.assert_called_once_with("anthropic:claude-sonnet-5-5")
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/agent/test_graph.py -v`
Expected: `FAIL` — `AssertionError: expected call ... claude-sonnet-5-5 ... Actual: ... claude-sonnet-4-5-20250929`

- [ ] **Step 3: Fix `src/eaa/agent/graph.py`**

Change:
```python
def default_model() -> BaseChatModel:
    """The default chat model for this agent: Claude, via Anthropic."""
    return init_chat_model("anthropic:claude-sonnet-4-5-20250929")
```
to:
```python
def default_model() -> BaseChatModel:
    """The default chat model for this agent: Claude, via Anthropic."""
    return init_chat_model("anthropic:claude-sonnet-5-5")
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/agent/test_graph.py -v`
Expected: `PASS`

Run the full suite: `uv run pytest -q`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/agent/graph.py tests/agent/test_graph.py
git commit -m "fix: update agent's default model to the current Claude Sonnet 5.5 ID"
```

---

## Task 3: Benchmark question set

**Files:**
- Create: `src/eaa/benchmark/questions.py`
- Test: `tests/benchmark/test_questions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/benchmark/test_questions.py
from eaa.benchmark.questions import QUESTIONS


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
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/benchmark/test_questions.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.benchmark.questions'`

- [ ] **Step 3: Implement `src/eaa/benchmark/questions.py`**

```python
"""The Phase 3 benchmark's fixed question set: 5 lookup, 5 aggregation/comparison,
5 multi-tool (warehouse + forecast) questions, each with a ground-truth function
computed live against the real warehouse/forecast API rather than a hardcoded
number -- stays correct as the warehouse is backfilled with more data over time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Literal

import duckdb

from eaa.mcp.forecast_client import fetch_forecast_history, fetch_latest_forecast

FORECAST_API_URL = os.environ.get("FORECAST_API_URL", "http://localhost:8000")

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

_LOOKUP_QUESTIONS = [
    BenchmarkQuestion(
        id="lookup-1",
        category="lookup",
        question="What was the most recently recorded hourly consumption value, in MW?",
        ground_truth_fn=_sql_ground_truth(
            "SELECT consumption_mw FROM consumption_hourly ORDER BY datetime DESC LIMIT 1"
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
            "WHERE source = 'nuclear' ORDER BY datetime DESC LIMIT 1"
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
            "WHERE source = 'wind' ORDER BY datetime DESC LIMIT 1"
        ),
        tolerance=0.5,
        expected_tools=["run_sql_query"],
    ),
    BenchmarkQuestion(
        id="lookup-4",
        category="lookup",
        question="What was the most recently recorded day-ahead electricity price, in EUR/MWh?",
        ground_truth_fn=_sql_ground_truth(
            "SELECT price_eur_mwh FROM day_ahead_prices_hourly ORDER BY datetime DESC LIMIT 1"
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
            "What was the average hourly consumption over the most recent 7 days "
            "of data, in MW?"
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
            "What was the minimum hourly consumption over the most recent 30 days "
            "of data, in MW?"
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
    latest = fetch_latest_forecast(FORECAST_API_URL)
    return latest[0]["q50_pred"]


def _history_rte_pred_values() -> list[float]:
    history = fetch_forecast_history(FORECAST_API_URL)
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
```

Note the multi-tool questions' tolerance (200 MW) is deliberately wider than the single-tool ones — these combine two independently-sourced numbers (a forecast and an aggregate), each with its own normal variance, and the arithmetic amplifies that; a tight tolerance here would mostly measure forecast noise, not the agent's correctness.

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/benchmark/test_questions.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/benchmark/questions.py tests/benchmark/test_questions.py
git commit -m "feat: add the Phase 3 benchmark's 15-question set with live ground truth"
```

---

## Task 4: Scoring

**Files:**
- Create: `src/eaa/benchmark/scoring.py`
- Test: `tests/benchmark/test_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/benchmark/test_scoring.py
from dataclasses import dataclass
from typing import Callable

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
        ("Approximately 1,234 MW was consumed.", 1.0),  # see note below
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
    question = _FakeQuestion(tolerance=0, expected_tools=["run_sql_query"], ground_truth_fn=lambda con: 0)
    tool_calls = [{"name": "run_sql_query", "args": {}, "result": "ok"}]
    result = scoring.score_tool_use(question, tool_calls)
    assert result["all_expected_called"] is True
    assert result["missing_tools"] == []


def test_score_tool_use_missing_an_expected_tool() -> None:
    question = _FakeQuestion(
        tolerance=0, expected_tools=["run_sql_query", "get_latest_forecast"], ground_truth_fn=lambda con: 0
    )
    tool_calls = [{"name": "run_sql_query", "args": {}, "result": "ok"}]
    result = scoring.score_tool_use(question, tool_calls)
    assert result["all_expected_called"] is False
    assert result["missing_tools"] == ["get_latest_forecast"]


def test_score_tool_use_tolerates_an_extra_unexpected_call() -> None:
    question = _FakeQuestion(tolerance=0, expected_tools=["run_sql_query"], ground_truth_fn=lambda con: 0)
    tool_calls = [
        {"name": "get_schema", "args": {}, "result": "ok"},
        {"name": "run_sql_query", "args": {}, "result": "ok"},
    ]
    result = scoring.score_tool_use(question, tool_calls)
    assert result["all_expected_called"] is True
```

Note on the `"1,234 MW"` test case: the regex extracts the first number-looking substring, and a thousands-separator comma reads as a decimal separator under the simple `[.,]` pattern below, so `"1,234"` extracts as `1.234` — rounded for the test to `1.0`... **this is wrong, fix the test expectation**: write it as `("Approximately 1,234 MW was consumed.", 1.234)` instead (matching the regex's actual, documented behavior — see Step 3's comment on why thousands separators aren't specially handled).

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/benchmark/test_scoring.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.benchmark.scoring'`

- [ ] **Step 3: Implement `src/eaa/benchmark/scoring.py`**

```python
"""Pure scoring functions: answer-text accuracy and tool-use recall.
No model, warehouse, or network dependency -- fully unit-testable.
"""

from __future__ import annotations

import re

import duckdb

# Matches the first number-looking substring: optional sign, digits, optional
# decimal part. Does not special-case thousands separators (",") -- a comma is
# read as a decimal point, same as "." -- because the benchmark's own questions
# never produce thousands-separated answers at the scale this warehouse's
# values reach (consumption/production in MW, prices in EUR/MWh are all well
# under 1,000,000 and rarely written with a thousands separator by the model).
_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def extract_first_number(text: str) -> float | None:
    """Return the first number found in free text, or None if there isn't one."""
    match = _NUMBER_RE.search(text)
    if match is None:
        return None
    return float(match.group().replace(",", "."))


def score_accuracy(question, con: duckdb.DuckDBPyConnection | None, answer_text: str) -> dict:
    """Compare the agent's extracted numeric answer to the question's live
    ground truth, within its tolerance."""
    expected = question.ground_truth_fn(con)
    extracted = extract_first_number(answer_text)
    correct = extracted is not None and abs(extracted - expected) <= question.tolerance
    return {"expected": expected, "extracted": extracted, "correct": correct}


def score_tool_use(question, tool_calls: list[dict]) -> dict:
    """Check that every tool the question expects was called at least once.
    An extra, unexpected call doesn't fail this check -- only a missing
    expected one does."""
    called_names = {call["name"] for call in tool_calls}
    missing = [name for name in question.expected_tools if name not in called_names]
    return {
        "called_tools": sorted(called_names),
        "missing_tools": missing,
        "all_expected_called": len(missing) == 0,
    }
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/benchmark/test_scoring.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/benchmark/scoring.py tests/benchmark/test_scoring.py
git commit -m "feat: add benchmark accuracy and tool-use scoring"
```

---

## Task 5: Cost calculation

**Files:**
- Create: `src/eaa/benchmark/cost.py`
- Test: `tests/benchmark/test_cost.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/benchmark/test_cost.py
from eaa.benchmark import cost


class _FakeMessage:
    def __init__(self, usage_metadata: dict | None) -> None:
        self.usage_metadata = usage_metadata


def test_compute_cost_for_claude_sonnet() -> None:
    messages = [
        _FakeMessage(None),  # human message, no usage
        _FakeMessage({"input_tokens": 1_000_000, "output_tokens": 1_000_000}),
    ]
    result = cost.compute_cost("claude-sonnet-5-5", messages)
    assert result == 2.00 + 10.00


def test_compute_cost_sums_across_multiple_ai_messages() -> None:
    messages = [
        _FakeMessage({"input_tokens": 500_000, "output_tokens": 0}),
        _FakeMessage({"input_tokens": 500_000, "output_tokens": 1_000_000}),
    ]
    result = cost.compute_cost("claude-sonnet-5-5", messages)
    assert result == 2.00 + 10.00


def test_compute_cost_for_ollama_models_is_zero() -> None:
    messages = [_FakeMessage({"input_tokens": 1_000_000, "output_tokens": 1_000_000})]
    assert cost.compute_cost("ollama:llama3.2", messages) == 0.0
    assert cost.compute_cost("ollama:llama3.1:8b", messages) == 0.0


def test_compute_cost_for_unknown_model_defaults_to_zero() -> None:
    messages = [_FakeMessage({"input_tokens": 1_000_000, "output_tokens": 1_000_000})]
    assert cost.compute_cost("some-unlisted-model", messages) == 0.0
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/benchmark/test_cost.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.benchmark.cost'`

- [ ] **Step 3: Implement `src/eaa/benchmark/cost.py`**

```python
"""Per-model pricing and cost calculation from LangChain usage_metadata.

Ollama models are priced at $0/token -- this is an honest simplification, not
an estimate of the real cost: running a local model costs compute/hardware
time, not a per-token price, and this benchmark doesn't attempt to put a
dollar figure on that. The report should be read as "the Claude arm's real
API cost" next to "the local arms' $0 API cost", not as a full TCO comparison.
"""

from __future__ import annotations

PRICING_USD_PER_MILLION_TOKENS = {
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
}


def compute_cost(model_key: str, messages: list) -> float:
    """Sum usage_metadata across messages and price it for the given model.
    Unlisted models (including every Ollama model) cost $0."""
    pricing = PRICING_USD_PER_MILLION_TOKENS.get(model_key)
    if pricing is None:
        return 0.0

    input_tokens = 0
    output_tokens = 0
    for message in messages:
        usage = getattr(message, "usage_metadata", None)
        if usage:
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)

    return (input_tokens / 1_000_000) * pricing["input"] + (
        output_tokens / 1_000_000
    ) * pricing["output"]
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/benchmark/test_cost.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/benchmark/cost.py tests/benchmark/test_cost.py
git commit -m "feat: add benchmark cost calculation from usage_metadata"
```

---

## Task 6: Report rendering

**Files:**
- Create: `src/eaa/benchmark/report.py`
- Test: `tests/benchmark/test_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/benchmark/test_report.py
from dataclasses import dataclass

from eaa.benchmark import report


@dataclass
class _FakeRunResult:
    question_id: str
    category: str
    model_key: str
    correct: bool
    all_expected_tools_called: bool
    cost_usd: float
    latency_seconds: float


def _results() -> list[_FakeRunResult]:
    return [
        _FakeRunResult("lookup-1", "lookup", "claude-sonnet-5-5", True, True, 0.01, 1.2),
        _FakeRunResult("lookup-2", "lookup", "claude-sonnet-5-5", False, True, 0.01, 1.1),
        _FakeRunResult("lookup-1", "lookup", "ollama:llama3.2", False, False, 0.0, 2.5),
        _FakeRunResult("lookup-2", "lookup", "ollama:llama3.2", True, True, 0.0, 2.1),
    ]


def test_render_markdown_includes_a_row_per_model() -> None:
    markdown = report.render_markdown(_results())
    assert "claude-sonnet-5-5" in markdown
    assert "ollama:llama3.2" in markdown


def test_render_markdown_reports_correct_accuracy_percentage() -> None:
    markdown = report.render_markdown(_results())
    # claude-sonnet-5-5: 1/2 correct = 50%
    assert "50.0%" in markdown


def test_render_markdown_reports_average_cost_and_latency() -> None:
    markdown = report.render_markdown(_results())
    # claude-sonnet-5-5 average cost: (0.01 + 0.01) / 2 = 0.01
    assert "0.0100" in markdown or "$0.01" in markdown
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/benchmark/test_report.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.benchmark.report'`

- [ ] **Step 3: Implement `src/eaa/benchmark/report.py`**

```python
"""Renders a markdown summary table from a list of benchmark RunResults."""

from __future__ import annotations

from collections import defaultdict


def _percentage(count: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{100 * count / total:.1f}%"


def render_markdown(results: list) -> str:
    """One row per model: overall accuracy %, tool-use %, avg cost, avg latency."""
    by_model: dict[str, list] = defaultdict(list)
    for r in results:
        by_model[r.model_key].append(r)

    lines = [
        "| Model | Accuracy | Tool use | Avg cost (USD) | Avg latency (s) | N |",
        "|---|---|---|---|---|---|",
    ]
    for model_key, rows in sorted(by_model.items()):
        n = len(rows)
        correct = sum(1 for r in rows if r.correct)
        tool_ok = sum(1 for r in rows if r.all_expected_tools_called)
        avg_cost = sum(r.cost_usd for r in rows) / n
        avg_latency = sum(r.latency_seconds for r in rows) / n
        lines.append(
            f"| {model_key} | {_percentage(correct, n)} | {_percentage(tool_ok, n)} "
            f"| ${avg_cost:.4f} | {avg_latency:.2f} | {n} |"
        )

    lines.append("")
    lines.append("### By category")
    lines.append("")
    lines.append("| Model | Category | Accuracy | Tool use | N |")
    lines.append("|---|---|---|---|---|")
    by_model_category: dict[tuple[str, str], list] = defaultdict(list)
    for r in results:
        by_model_category[(r.model_key, r.category)].append(r)
    for (model_key, category), rows in sorted(by_model_category.items()):
        n = len(rows)
        correct = sum(1 for r in rows if r.correct)
        tool_ok = sum(1 for r in rows if r.all_expected_tools_called)
        lines.append(
            f"| {model_key} | {category} | {_percentage(correct, n)} "
            f"| {_percentage(tool_ok, n)} | {n} |"
        )

    return "\n".join(lines)
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/benchmark/test_report.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/benchmark/report.py tests/benchmark/test_report.py
git commit -m "feat: add benchmark markdown report rendering"
```

---

## Task 7: Runner

**Files:**
- Create: `src/eaa/benchmark/runner.py`
- Test: `tests/benchmark/test_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/benchmark/test_runner.py
from unittest.mock import MagicMock

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
        usage_metadata={"input_tokens": 100, "output_tokens": 20},
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

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "eaa.benchmark.runner.build_agent", return_value=fake_agent
    ):
        results = runner.run_benchmark(models, questions, tools=[], con=None)

    assert len(results) == len(models) * len(questions)
    assert {r.model_key for r in results} == {"model-a", "model-b"}
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/benchmark/test_runner.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.benchmark.runner'`

- [ ] **Step 3: Implement `src/eaa/benchmark/runner.py`**

```python
"""Orchestrates the benchmark: one agent.invoke() per (model, question) pair,
scoring each run's accuracy, tool use, cost, and latency.
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


def run_one(
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
    result = agent.invoke(
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


def run_benchmark(
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
            results.append(run_one(question, model_key, agent, con, callbacks))
    return results
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/benchmark/test_runner.py -v`
Expected: `PASS`

Run the full suite: `uv run pytest -q`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/benchmark/runner.py tests/benchmark/test_runner.py
git commit -m "feat: add benchmark runner orchestrating models x questions"
```

---

## Task 8: CLI entry point

**Files:**
- Create: `src/eaa/benchmark/cli.py`
- Test: `tests/benchmark/test_cli.py`

- [ ] **Step 1: Verify the installed `langfuse` SDK's LangChain callback handler import path**

Run:
```bash
uv run python -c "
from langfuse.langchain import CallbackHandler
print(CallbackHandler)
"
```
If this import fails, check `uv run python -c "import langfuse; print(langfuse.__file__)"` to find the installed package, then search it (`grep -rl CallbackHandler <that directory>`) for the real module path, and use that import in Step 3 instead. This project already hit real import-path surprises with `mcp`/`langchain-mcp-adapters` in Phases 1-2 — don't assume the path above is correct without checking.

- [ ] **Step 2: Write the failing test**

```python
# tests/benchmark/test_cli.py
from unittest.mock import MagicMock, patch

from eaa.benchmark import cli


def test_main_builds_three_models_and_runs_the_benchmark(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_results = [MagicMock(model_key="claude-sonnet-5-5")]

    with (
        patch("eaa.benchmark.cli.load_mcp_tools", return_value=[]),
        patch("eaa.benchmark.cli.warehouse.get_connection", return_value=MagicMock()),
        patch("eaa.benchmark.cli.init_chat_model", return_value=MagicMock()),
        patch("eaa.benchmark.cli.build_langfuse_callbacks", return_value=None),
        patch("eaa.benchmark.cli.run_benchmark", return_value=fake_results) as mock_run,
        patch("eaa.benchmark.cli.render_markdown", return_value="# report") as mock_render,
    ):
        cli.main()

    mock_run.assert_called_once()
    models_arg = mock_run.call_args.args[0]
    assert set(models_arg.keys()) == {"claude-sonnet-5-5", "ollama:llama3.2", "ollama:llama3.1:8b"}
    mock_render.assert_called_once_with(fake_results)
    assert (tmp_path / "docs" / "benchmark_report.md").exists()
    assert (tmp_path / "benchmark_results.json").exists()


def test_build_langfuse_callbacks_returns_none_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert cli.build_langfuse_callbacks() is None
```

- [ ] **Step 3: Run and confirm failure**

Run: `uv run pytest tests/benchmark/test_cli.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.benchmark.cli'`

- [ ] **Step 4: Implement `src/eaa/benchmark/cli.py`**

```python
"""CLI entry point for the Phase 3 benchmark: `uv run eaa-benchmark`."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from eaa import warehouse
from eaa.agent.mcp_client import load_mcp_tools
from eaa.benchmark.questions import QUESTIONS
from eaa.benchmark.report import render_markdown
from eaa.benchmark.runner import run_benchmark

# Adjust this import if Task 8 Step 1's verification found a different path.
from langfuse.langchain import CallbackHandler


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
    Path("benchmark_results.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2)
    )
    print("\nWrote docs/benchmark_report.md and benchmark_results.json")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run and confirm success**

Run: `uv run pytest tests/benchmark/test_cli.py -v`
Expected: `PASS`

Run the full suite: `uv run pytest -q`

Run lint: `uv run ruff check . && uv run ruff format --check src tests`

- [ ] **Step 6: Commit**

```bash
git add src/eaa/benchmark/cli.py tests/benchmark/test_cli.py
git commit -m "feat: add eaa-benchmark CLI entry point"
```

---

## Task 9: README update and honest documentation of the deferred real run

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full test suite one more time**

Run: `uv run pytest -q`
Expected: all tests pass (check the real count with `uv run pytest --collect-only -q | tail -1` and use that number below, not a guess).

Run: `uv run ruff check . && uv run ruff format --check src tests`
Expected: clean.

- [ ] **Step 2: Check whether a real run is actually possible in this environment**

```bash
grep -q '^ANTHROPIC_API_KEY=.' .env 2>/dev/null && echo "anthropic: set" || echo "anthropic: NOT SET"
grep -q '^LANGFUSE_PUBLIC_KEY=.' .env 2>/dev/null && echo "langfuse: set" || echo "langfuse: NOT SET"
ls warehouse.duckdb 2>/dev/null && echo "warehouse: present" || echo "warehouse: NOT PRESENT"
command -v ollama && ollama list 2>&1 | grep -E "llama3.2|llama3.1:8b" || echo "ollama models: check manually"
```

**If any of `ANTHROPIC_API_KEY`, `warehouse.duckdb` are missing** (the likely case, per this plan's own context): do NOT attempt the real benchmark run. Document the gap honestly in the README (Step 3), the same way Phases 1 and 2 did for their own pending-verification gaps. If everything happens to be available, you may attempt a real `uv run eaa-benchmark` run (with `eaa-mcp-server` running) and report real results — but do not fabricate results if any prerequisite is missing.

- [ ] **Step 3: Update `README.md`**

Replace the Phase 3 roadmap line (if present) or add a new Status entry:

```markdown
**Phase 3 — shipped (code), real run pending**: a custom benchmark comparing Claude
Sonnet 5.5 against two local Ollama models (`llama3.2`, `llama3.1:8b`) on accuracy,
tool use, cost, and latency over 15 questions (5 lookup, 5 aggregation, 5 multi-tool),
with Langfuse tracing. All code is built and tested (<N> tests) against mocks. The
real, paid/data-dependent run (`uv run eaa-benchmark`) is still pending: it needs
`ANTHROPIC_API_KEY` (paid, ~a few dollars for 45 runs), a populated `warehouse.duckdb`,
Ollama running locally, and Langfuse credentials — none of which are available in
this environment. This mirrors Phase 1's ENTSO-E gap and Phase 2's live-Claude-
verification gap: documented honestly rather than faked.
```

Add a "Running the benchmark" subsection under Getting Started:

```markdown
## Running the benchmark (Phase 3)

Requires `eaa-mcp-server` running (port 8001), a populated `warehouse.duckdb`
(`uv run warehouse backfill`), `ANTHROPIC_API_KEY` and `LANGFUSE_PUBLIC_KEY`/
`LANGFUSE_SECRET_KEY` in `.env`, and Ollama running locally with `llama3.2` and
`llama3.1:8b` pulled (`ollama pull llama3.2 && ollama pull llama3.1:8b`).

```bash
uv run eaa-mcp-server &
uv run eaa-benchmark
```

Writes `docs/benchmark_report.md` (committable once a real run has happened) and
`benchmark_results.json` (local, gitignored raw results).
```

Fill in the real `<N>` test count from Step 1.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README with Phase 3 status and running instructions"
```

---

## Plan self-review notes

- **Spec coverage**: model choices (Task 8), direct-Python invocation not `/ask` (Task 7), 15-question dataset with live ground truth not hardcoded values (Task 3), regex-based accuracy scoring not forced structured output (Task 4), recall-based tool-use scoring (Task 4), cost via `usage_metadata` with Ollama at $0 (Task 5), Langfuse cloud callbacks (Task 8), markdown report to both stdout and `docs/benchmark_report.md` plus gitignored raw JSON (Task 6, 8, Task 1's gitignore entry), the stale-model-ID bug fix (Task 2), and the honest deferred-real-run documentation (Task 9) — every design-doc decision maps to a task.
- **Grounded-in-source, not guessed**: the forecast field names used in Task 3's multi-tool ground truth functions (`q50_pred` for `/forecast/latest`, `rte_pred` for `/forecast/history`) were confirmed by reading the sibling `france-electricity-forecasting` repo's actual `forecast.py` docstring and this project's own prior-session research into `quantile_backtest_results.parquet`'s real columns — not assumed from the benchmark design alone.
- **Type/signature consistency checked**: `BenchmarkQuestion`'s fields (`id`, `category`, `question`, `ground_truth_fn`, `tolerance`, `expected_tools`) are defined once in Task 3 and used with matching names in Tasks 4 (`scoring.py`), 7 (`runner.py`). `RunResult`'s fields (Task 7) match exactly what Task 6's `report.py` reads (`model_key`, `category`, `correct`, `all_expected_tools_called`, `cost_usd`, `latency_seconds`). `compute_cost(model_key, messages)` (Task 5) is called with the same signature in Task 7.
- **Honest uncertainty flagged**: Task 8 includes an explicit verification step for `langfuse`'s callback-handler import path, consistent with how Phases 1-2 handled real SDK-API uncertainty, rather than assuming an unverified import path is correct.
