# Phase 1 — Data Warehouse and MCP Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a DuckDB data warehouse of French power-system data (consumption, production mix by source, day-ahead spot prices) and an MCP server exposing it — plus project 1's forecasting API — as tools, ready for the Phase 2 LangGraph agent to consume.

**Architecture:** Two independent connectors (RTE éCO2mix via ODRÉ, ENTSO-E Transparency Platform) write into a single DuckDB file through shared upsert helpers; a CLI drives backfill/refresh. A standalone `FastMCP` HTTP server wraps the warehouse (`get_schema`, `run_sql_query`) and project 1's serving API (`get_latest_forecast`, `get_forecast_history`) as four MCP tools, with the tool logic kept in plain, unit-testable functions separate from the MCP decorators.

**Tech Stack:** Python 3.12, `uv`, DuckDB, pandas, `requests`, the official `mcp` Python SDK (`FastMCP`), `python-dotenv`, pytest, ruff.

**Reference:** `docs/superpowers/specs/2026-10-20-warehouse-mcp-design.md` (approved design this plan implements).

---

## Task 1: Bootstrap the project

**Files:**
- Create: `pyproject.toml`
- Create: `src/eaa/__init__.py`
- Create: `src/eaa/ingestion/__init__.py`
- Create: `src/eaa/mcp/__init__.py`
- Create: `.env.example`
- Create: `CLAUDE.md` (gitignored, never committed)
- Modify: `.gitignore`

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p src/eaa/ingestion src/eaa/mcp tests/ingestion tests/mcp tests/fixtures
touch src/eaa/__init__.py src/eaa/ingestion/__init__.py src/eaa/mcp/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "energy-analyst-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "duckdb",
    "pandas",
    "requests",
    "mcp[cli]",
    "python-dotenv",
]

[project.optional-dependencies]
dev = ["pytest", "ruff"]

[project.scripts]
warehouse = "eaa.cli:main"
eaa-mcp-server = "eaa.mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/eaa"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 3: Install and verify the environment**

Run: `uv sync --extra dev`
Expected: completes with no errors, creates `.venv/` and `uv.lock`.

Run: `uv run python -c "import eaa; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Append project-specific entries to `.gitignore`**

Append to the end of the existing `.gitignore` (after the `.streamlit/secrets.toml` line):

```gitignore

CLAUDE.md

# DuckDB warehouse (rebuilt from source APIs via `warehouse backfill`)
*.duckdb
*.duckdb.wal
```

- [ ] **Step 5: Create `.env.example`**

```bash
# ENTSO-E Transparency Platform API token — request via https://transparency.entsoe.eu
ENTSOE_API_TOKEN=

# Base URL of france-electricity-forecasting's serving API
FORECAST_API_URL=http://localhost:8000
```

- [ ] **Step 6: Create the project `CLAUDE.md`** (gitignored — this file is never committed)

```markdown
# Project: energy-analyst-agent

Repository: https://github.com/mlndiaye/energy-analyst-agent

## Who I am

I am Mouhamadou Lamine NDIAYE, an engineer in Computer Science and Telecommunications
(École Polytechnique de Thiès, highest honors), currently in the M2 DataScale
(large-scale data management) at Université Paris-Saclay, positioning myself as a
Data & AI Engineer.

## Why this project exists

Third project of a three-project portfolio built to support applications for a
6-month end-of-studies internship in Data/AI Engineering (France, 2027):
`france-electricity-forecasting` (ML + MLOps), `french-business-registry` (Data
Engineering + Big Data), and this one — the AI Engineering project. Must be
defensible in a 20-30 minute technical interview.

## The project

An LLM agent that answers analytical questions about the French power system by
querying a data warehouse and calling project 1's forecasting model, evaluated on a
custom benchmark comparing API-based and local models. Three phases, each with its
own design spec written just before it is built:

- **Phase 1** (current): DuckDB warehouse (consumption, production mix, day-ahead
  prices) + MCP server exposing it and project 1's forecasting API as tools. See
  `docs/superpowers/specs/2026-10-20-warehouse-mcp-design.md`.
- **Phase 2**: LangGraph agent (MCP client), served over FastAPI + CLI.
- **Phase 3**: custom benchmark, Claude vs. two local Ollama models, Langfuse tracing.

## How I want to work with you

- Think with me, explain trade-offs before writing significant code, build step by
  step — never hundreds of lines at once.
- Challenge me if something is unnecessary, too complex, too simple, or not credible.
- No buzzword engineering — every tool must be justified against the simplest option.
- Measure and document; report disappointing results honestly.
- Communicate with me in French; code, comments, commits and docs in English.

## Git rules

- Remote: https://github.com/mlndiaye/energy-analyst-agent (branch `main`)
- Small, meaningful conventional commits (`feat:`, `fix:`, `docs:`, `test:`...);
  commit after each validated step.
- Commit messages and PR descriptions must never mention Claude, Claude Code or AI
  assistance: no Co-Authored-By trailer, no "Generated with" footer, no session link.
- `CLAUDE.md` is listed in `.gitignore` and must never be committed.

## Current phase

Phase 1 in progress: DuckDB warehouse + MCP server.
```

- [ ] **Step 7: Lint and commit**

Run: `uv run ruff check .`
Expected: `All checks passed!`

```bash
git add pyproject.toml uv.lock src/eaa/__init__.py src/eaa/ingestion/__init__.py src/eaa/mcp/__init__.py .gitignore .env.example
git commit -m "chore: bootstrap project skeleton"
```

---

## Task 2: DuckDB schema and connection helper

**Files:**
- Create: `src/eaa/warehouse.py`
- Test: `tests/test_warehouse.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_warehouse.py
from pathlib import Path

from eaa import warehouse


def test_get_connection_creates_the_three_tables(tmp_path: Path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    con.close()
    assert tables == {
        "consumption_hourly",
        "production_by_source_hourly",
        "day_ahead_prices_hourly",
    }
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_warehouse.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.warehouse'` (or `AttributeError`).

- [ ] **Step 3: Implement `src/eaa/warehouse.py`**

```python
"""DuckDB warehouse: connection, schema, and upsert helpers."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_DB_PATH = Path("warehouse.duckdb")

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS consumption_hourly (
        datetime TIMESTAMP PRIMARY KEY,
        consumption_mw DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS production_by_source_hourly (
        datetime TIMESTAMP,
        source VARCHAR,
        production_mw DOUBLE,
        PRIMARY KEY (datetime, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS day_ahead_prices_hourly (
        datetime TIMESTAMP PRIMARY KEY,
        price_eur_mwh DOUBLE
    )
    """,
]


def get_connection(
    db_path: Path = DEFAULT_DB_PATH, *, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """Open the warehouse. Creates the schema on first write-mode connection."""
    con = duckdb.connect(str(db_path), read_only=read_only)
    if not read_only:
        create_schema(con)
    return con


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    for statement in _SCHEMA_STATEMENTS:
        con.execute(statement)


def upsert_consumption(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    con.register("_df_consumption", df[["datetime", "consumption_mw"]])
    con.execute(
        """
        INSERT INTO consumption_hourly
        SELECT datetime, consumption_mw FROM _df_consumption
        ON CONFLICT (datetime) DO UPDATE SET consumption_mw = EXCLUDED.consumption_mw
        """
    )
    con.unregister("_df_consumption")


def upsert_production_mix(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    con.register("_df_production", df[["datetime", "source", "production_mw"]])
    con.execute(
        """
        INSERT INTO production_by_source_hourly
        SELECT datetime, source, production_mw FROM _df_production
        ON CONFLICT (datetime, source) DO UPDATE SET production_mw = EXCLUDED.production_mw
        """
    )
    con.unregister("_df_production")


def upsert_prices(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    con.register("_df_prices", df[["datetime", "price_eur_mwh"]])
    con.execute(
        """
        INSERT INTO day_ahead_prices_hourly
        SELECT datetime, price_eur_mwh FROM _df_prices
        ON CONFLICT (datetime) DO UPDATE SET price_eur_mwh = EXCLUDED.price_eur_mwh
        """
    )
    con.unregister("_df_prices")
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `uv run pytest tests/test_warehouse.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/warehouse.py tests/test_warehouse.py
git commit -m "feat: add DuckDB warehouse schema and connection helper"
```

---

## Task 3: Warehouse upsert functions — idempotency tests

**Files:**
- Modify: `tests/test_warehouse.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_warehouse.py
import pandas as pd


def test_upsert_consumption_is_idempotent_and_updates(tmp_path: Path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 01:00"]),
            "consumption_mw": [100.0, 110.0],
        }
    )
    warehouse.upsert_consumption(con, df)
    warehouse.upsert_consumption(con, df)  # re-running must not duplicate rows

    rows = con.execute("SELECT COUNT(*) FROM consumption_hourly").fetchone()
    assert rows[0] == 2

    update = pd.DataFrame(
        {"datetime": pd.to_datetime(["2026-01-01 00:00"]), "consumption_mw": [999.0]}
    )
    warehouse.upsert_consumption(con, update)
    value = con.execute(
        "SELECT consumption_mw FROM consumption_hourly WHERE datetime = '2026-01-01 00:00'"
    ).fetchone()
    con.close()
    assert value[0] == 999.0


def test_upsert_production_mix_is_idempotent_and_updates(tmp_path: Path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:00"]),
            "source": ["nuclear", "wind"],
            "production_mw": [40000.0, 3000.0],
        }
    )
    warehouse.upsert_production_mix(con, df)
    warehouse.upsert_production_mix(con, df)

    rows = con.execute("SELECT COUNT(*) FROM production_by_source_hourly").fetchone()
    assert rows[0] == 2

    update = pd.DataFrame(
        {"datetime": pd.to_datetime(["2026-01-01 00:00"]), "source": ["wind"], "production_mw": [3500.0]}
    )
    warehouse.upsert_production_mix(con, update)
    value = con.execute(
        "SELECT production_mw FROM production_by_source_hourly "
        "WHERE datetime = '2026-01-01 00:00' AND source = 'wind'"
    ).fetchone()
    con.close()
    assert value[0] == 3500.0


def test_upsert_prices_is_idempotent_and_updates(tmp_path: Path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    df = pd.DataFrame(
        {"datetime": pd.to_datetime(["2026-01-01 00:00"]), "price_eur_mwh": [45.0]}
    )
    warehouse.upsert_prices(con, df)
    warehouse.upsert_prices(con, df)

    rows = con.execute("SELECT COUNT(*) FROM day_ahead_prices_hourly").fetchone()
    assert rows[0] == 1

    update = pd.DataFrame(
        {"datetime": pd.to_datetime(["2026-01-01 00:00"]), "price_eur_mwh": [50.0]}
    )
    warehouse.upsert_prices(con, update)
    value = con.execute(
        "SELECT price_eur_mwh FROM day_ahead_prices_hourly WHERE datetime = '2026-01-01 00:00'"
    ).fetchone()
    con.close()
    assert value[0] == 50.0
```

- [ ] **Step 2: Run and confirm they pass**

(`upsert_*` were already implemented in Task 2.)

Run: `uv run pytest tests/test_warehouse.py -v`
Expected: `PASS` — 4 tests total.

- [ ] **Step 3: Commit**

```bash
git add tests/test_warehouse.py
git commit -m "test: cover upsert idempotency for all three warehouse tables"
```

---

## Task 4: éCO2mix connector — paginated fetch

**Files:**
- Create: `src/eaa/ingestion/eco2mix.py`
- Test: `tests/ingestion/test_eco2mix.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ingestion/test_eco2mix.py
from datetime import date
from unittest.mock import patch

from eaa.ingestion import eco2mix


def _page(rows: list[dict]) -> object:
    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"results": rows}

    return _Response()


def test_fetch_records_paginates_and_dedups_on_cursor() -> None:
    page1 = [{"date_heure": f"2026-01-01T0{i}:00:00+00:00", "consommation": str(1000 + i)} for i in range(3)]
    # Last row of page1 (hour 2) is re-sent as the first row of page2 (inclusive cursor).
    page2 = [{"date_heure": "2026-01-01T02:00:00+00:00", "consommation": "1002"}]

    with patch("eaa.ingestion.eco2mix.requests.get") as mock_get:
        mock_get.side_effect = [_page(page1), _page(page2)]
        with patch("eaa.ingestion.eco2mix.PAGE_SIZE", 3):
            df = eco2mix.fetch_records(eco2mix.TR_DATASET, date(2026, 1, 1), date(2026, 1, 1))

    assert len(df) == 3
    assert mock_get.call_count == 2
    assert list(df["date_heure"]) == [row["date_heure"] for row in page1]
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/ingestion/test_eco2mix.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.ingestion.eco2mix'`

- [ ] **Step 3: Implement `src/eaa/ingestion/eco2mix.py` (fetch part only)**

```python
"""RTE éCO2mix connector (via the ODRÉ Explore v2.1 API) — consumption and
production mix by source. Independent of france-electricity-forecasting's own
rte.py connector (same public API, rewritten here so this project stays
self-contained — see the design spec's "why a new connector" section).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import requests

RECORDS_URL = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/{dataset}/records"

CONS_DEF_DATASET = "eco2mix-national-cons-def"
TR_DATASET = "eco2mix-national-tr"

# French éCO2mix field name -> English warehouse source name.
SOURCE_FIELDS = {
    "nucleaire": "nuclear",
    "eolien": "wind",
    "solaire": "solar",
    "hydraulique": "hydro",
    "gaz": "gas",
}
FIELDS = ["date_heure", "consommation", *SOURCE_FIELDS]
PAGE_SIZE = 100

# eco2mix-national-tr only keeps a rolling window (~3 months, per the ODRÉ
# dataset description); anything older must come from cons-def instead. Computed
# relative to "today" rather than hardcoded, so this connector doesn't need a
# manually-updated boundary date as time passes.
TR_WINDOW_DAYS = 90


def fetch_records(dataset: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch every record of `dataset` with date_heure in [start_date, end_date], inclusive.

    Paginates by cursoring on date_heure (not offset: the API hard-caps
    offset + limit at 10,000). The cursor is inclusive, so the last row of a
    page is re-requested as the first row of the next page; rows already seen
    (by date_heure) are dropped to deduplicate.
    """
    end_exclusive = end_date + timedelta(days=1)
    cursor = start_date.isoformat()
    rows: list[dict] = []
    seen: set[str] = set()

    while True:
        where = f"date_heure >= '{cursor}' AND date_heure < '{end_exclusive.isoformat()}'"
        response = requests.get(
            RECORDS_URL.format(dataset=dataset),
            params={
                "select": ",".join(FIELDS),
                "where": where,
                "order_by": "date_heure",
                "limit": PAGE_SIZE,
            },
            timeout=30,
        )
        response.raise_for_status()
        page = response.json()["results"]
        if not page:
            break

        new_rows = []
        for r in page:
            if r["date_heure"] not in seen:
                new_rows.append(r)
                seen.add(r["date_heure"])

        if not new_rows and len(page) == PAGE_SIZE:
            raise RuntimeError(
                f"éCO2mix pagination made no progress at cursor {cursor!r} -- more "
                f"than {PAGE_SIZE} records appear to share one date_heure."
            )
        rows.extend(new_rows)

        if len(page) < PAGE_SIZE:
            break
        cursor = page[-1]["date_heure"]

    return pd.DataFrame(rows, columns=FIELDS)
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `uv run pytest tests/ingestion/test_eco2mix.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/ingestion/eco2mix.py tests/ingestion/test_eco2mix.py
git commit -m "feat: add éCO2mix paginated fetch connector"
```

---

## Task 5: éCO2mix hourly transforms

**Files:**
- Modify: `src/eaa/ingestion/eco2mix.py`
- Modify: `tests/ingestion/test_eco2mix.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/ingestion/test_eco2mix.py
import pandas as pd


def test_consumption_hourly_aggregates_subhourly_points_by_mean() -> None:
    raw = pd.DataFrame(
        {
            "date_heure": [
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:15:00+00:00",
                "2026-01-01T00:30:00+00:00",
                "2026-01-01T00:45:00+00:00",
            ],
            "consommation": ["100", "110", "120", "130"],
        }
    )
    result = eco2mix.consumption_hourly(raw)
    assert len(result) == 1
    assert result.loc[0, "consumption_mw"] == 115.0


def test_production_mix_hourly_melts_to_long_format_with_english_names() -> None:
    raw = pd.DataFrame(
        {
            "date_heure": ["2026-01-01T00:00:00+00:00", "2026-01-01T00:30:00+00:00"],
            "nucleaire": ["40000", "42000"],
            "eolien": ["3000", "3200"],
            "solaire": ["0", "0"],
            "hydraulique": ["5000", "5100"],
            "gaz": ["2000", "2100"],
        }
    )
    result = eco2mix.production_mix_hourly(raw)
    assert set(result["source"]) == {"nuclear", "wind", "solar", "hydro", "gas"}
    nuclear_row = result[result["source"] == "nuclear"].iloc[0]
    assert nuclear_row["production_mw"] == 41000.0
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/ingestion/test_eco2mix.py -v`
Expected: `FAIL` — `AttributeError: module 'eaa.ingestion.eco2mix' has no attribute 'consumption_hourly'`

- [ ] **Step 3: Append the transforms to `src/eaa/ingestion/eco2mix.py`**

```python
def _to_hourly(df: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    working = df.copy()
    working["datetime"] = pd.to_datetime(working["date_heure"], utc=True).dt.tz_localize(None)
    for col in value_cols:
        working[col] = pd.to_numeric(working[col], errors="coerce")
    hourly = working.set_index("datetime")[value_cols].resample("1h").mean()
    return hourly.reset_index()


def consumption_hourly(df: pd.DataFrame) -> pd.DataFrame:
    hourly = _to_hourly(df, ["consommation"])
    return hourly.rename(columns={"consommation": "consumption_mw"})


def production_mix_hourly(df: pd.DataFrame) -> pd.DataFrame:
    source_cols = list(SOURCE_FIELDS)
    hourly = _to_hourly(df, source_cols)
    long_df = hourly.melt(
        id_vars="datetime", value_vars=source_cols, var_name="source_fr", value_name="production_mw"
    )
    long_df["source"] = long_df["source_fr"].map(SOURCE_FIELDS)
    return long_df[["datetime", "source", "production_mw"]].dropna(subset=["production_mw"])
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/ingestion/test_eco2mix.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/ingestion/eco2mix.py tests/ingestion/test_eco2mix.py
git commit -m "feat: add éCO2mix hourly consumption and production-mix transforms"
```

---

## Task 6: éCO2mix backfill/refresh orchestration

**Files:**
- Modify: `src/eaa/ingestion/eco2mix.py`
- Modify: `tests/ingestion/test_eco2mix.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/ingestion/test_eco2mix.py
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from eaa import warehouse


def test_backfill_chains_cons_def_and_tr_and_upserts(tmp_path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    today = date(2026, 6, 1)
    tr_start = today - timedelta(days=eco2mix.TR_WINDOW_DAYS)

    raw = pd.DataFrame(
        {
            "date_heure": ["2026-01-01T00:00:00+00:00"],
            "consommation": ["1000"],
            "nucleaire": ["40000"],
            "eolien": ["3000"],
            "solaire": ["0"],
            "hydraulique": ["5000"],
            "gaz": ["2000"],
        }
    )

    with (
        patch("eaa.ingestion.eco2mix.fetch_records", return_value=raw) as mock_fetch,
        patch("eaa.ingestion.eco2mix._today", return_value=today),
    ):
        eco2mix.backfill(con, date(2024, 2, 1), today)

    datasets_fetched = [call.args[0] for call in mock_fetch.call_args_list]
    assert eco2mix.CONS_DEF_DATASET in datasets_fetched
    assert eco2mix.TR_DATASET in datasets_fetched

    consumption_rows = con.execute("SELECT COUNT(*) FROM consumption_hourly").fetchone()[0]
    mix_rows = con.execute("SELECT COUNT(*) FROM production_by_source_hourly").fetchone()[0]
    con.close()
    assert consumption_rows > 0
    assert mix_rows > 0
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/ingestion/test_eco2mix.py -v`
Expected: `FAIL` — `AttributeError: module 'eaa.ingestion.eco2mix' has no attribute 'backfill'`

- [ ] **Step 3: Append orchestration to `src/eaa/ingestion/eco2mix.py`**

```python
from eaa import warehouse


def _today() -> date:
    return datetime.now(UTC).date()


def _upsert_all(con, raw_df: pd.DataFrame) -> None:
    warehouse.upsert_consumption(con, consumption_hourly(raw_df))
    warehouse.upsert_production_mix(con, production_mix_hourly(raw_df))


def backfill(con, start_date: date, end_date: date) -> None:
    """Fetch and upsert [start_date, end_date], chaining cons-def (older data)
    and tr (data within TR_WINDOW_DAYS of today).
    """
    tr_start = max(start_date, _today() - timedelta(days=TR_WINDOW_DAYS))

    if start_date < tr_start:
        df = fetch_records(CONS_DEF_DATASET, start_date, tr_start - timedelta(days=1))
        if not df.empty:
            _upsert_all(con, df)

    if end_date >= tr_start:
        df = fetch_records(TR_DATASET, max(start_date, tr_start), end_date)
        if not df.empty:
            _upsert_all(con, df)


def refresh(con) -> None:
    """Re-fetch the last 5 days through today from the tr dataset."""
    today = _today()
    df = fetch_records(TR_DATASET, today - timedelta(days=5), today)
    if not df.empty:
        _upsert_all(con, df)
```

Move the `from eaa import warehouse` import to the top of the file with the other imports (not inline) when applying this step.

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/ingestion/test_eco2mix.py -v`
Expected: `PASS` — 5 tests total.

- [ ] **Step 5: Commit**

```bash
git add src/eaa/ingestion/eco2mix.py tests/ingestion/test_eco2mix.py
git commit -m "feat: add éCO2mix backfill/refresh orchestration into the warehouse"
```

---

## Task 7: ENTSO-E connector — day-ahead price XML parsing

**Context:** the ENTSO-E Transparency Platform's day-ahead price document (type `A44`)
is **not yet verified against a real response** — access requires an API token
requested by email (see Task 8, which also covers that verification). This task
implements parsing against the platform's publicly documented schema, using `{*}`
wildcard namespace matching so a minor namespace-version difference in the real
response doesn't break parsing. If Task 8's real-API check finds the actual shape
differs, come back and adjust the XPath expressions below against the real captured
response (replacing the fixture created in this task).

**Files:**
- Create: `src/eaa/ingestion/entsoe.py`
- Create: `tests/fixtures/entsoe_sample.xml`
- Test: `tests/ingestion/test_entsoe.py`

- [ ] **Step 1: Create the fixture**

```xml
<!-- tests/fixtures/entsoe_sample.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries>
    <Period>
      <timeInterval>
        <start>2026-01-01T23:00Z</start>
        <end>2026-01-02T23:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>45.67</price.amount></Point>
      <Point><position>2</position><price.amount>42.10</price.amount></Point>
      <Point><position>3</position><price.amount>40.05</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/ingestion/test_entsoe.py
from datetime import UTC, datetime
from pathlib import Path

from eaa.ingestion import entsoe

FIXTURE = Path(__file__).parent.parent / "fixtures" / "entsoe_sample.xml"


def test_parse_day_ahead_prices_reads_hourly_points() -> None:
    xml_text = FIXTURE.read_text()
    df = entsoe.parse_day_ahead_prices(xml_text)

    assert len(df) == 3
    assert df.loc[0, "datetime"] == datetime(2026, 1, 1, 23, 0, tzinfo=UTC).replace(tzinfo=None)
    assert df.loc[0, "price_eur_mwh"] == 45.67
    assert df.loc[2, "datetime"] == datetime(2026, 1, 2, 1, 0, tzinfo=UTC).replace(tzinfo=None)


def test_parse_day_ahead_prices_raises_on_empty_response() -> None:
    empty = (
        '<?xml version="1.0"?>'
        '<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">'
        "</Publication_MarketDocument>"
    )
    try:
        entsoe.parse_day_ahead_prices(empty)
        raised = False
    except entsoe.EntsoeError:
        raised = True
    assert raised
```

- [ ] **Step 3: Run and confirm failure**

Run: `uv run pytest tests/ingestion/test_entsoe.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.ingestion.entsoe'`

- [ ] **Step 4: Implement `src/eaa/ingestion/entsoe.py` (parsing part only)**

```python
"""ENTSO-E Transparency Platform connector for French day-ahead spot prices.

Targets the A44 (price) document schema as publicly documented. `{*}` wildcard
namespace matching is used throughout so a minor schema-version change in
ENTSO-E's namespace URI doesn't silently break parsing. Not yet verified against
a real response — see Task 8 / docs/decisions/0001-entsoe-day-ahead-prices.md.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree as ET

import pandas as pd

FRANCE_DOMAIN = "10YFR-RTE------C"  # EIC code for the French bidding zone


class EntsoeError(RuntimeError):
    """Raised when the ENTSO-E API returns an error or an unparseable response."""


def parse_day_ahead_prices(xml_text: str) -> pd.DataFrame:
    """Parse an A44 Publication_MarketDocument into (datetime, price_eur_mwh) rows."""
    root = ET.fromstring(xml_text)
    rows: list[dict] = []

    for timeseries in root.findall("{*}TimeSeries"):
        for period in timeseries.findall("{*}Period"):
            start_str = period.findtext("{*}timeInterval/{*}start")
            resolution = period.findtext("{*}resolution")
            if start_str is None or resolution != "PT60M":
                continue
            period_start = datetime.strptime(start_str, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
            for point in period.findall("{*}Point"):
                position = int(point.findtext("{*}position"))
                price = float(point.findtext("{*}price.amount"))
                rows.append(
                    {
                        "datetime": (period_start + timedelta(hours=position - 1)).replace(tzinfo=None),
                        "price_eur_mwh": price,
                    }
                )

    if not rows:
        raise EntsoeError("No hourly (PT60M) price points found in ENTSO-E response")

    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset="datetime")
        .sort_values("datetime")
        .reset_index(drop=True)
    )
```

- [ ] **Step 5: Run and confirm success**

Run: `uv run pytest tests/ingestion/test_entsoe.py -v`
Expected: `PASS`

- [ ] **Step 6: Commit**

```bash
git add src/eaa/ingestion/entsoe.py tests/ingestion/test_entsoe.py tests/fixtures/entsoe_sample.xml
git commit -m "feat: add ENTSO-E day-ahead price XML parsing"
```

---

## Task 8: ENTSO-E fetch, backfill/refresh, and real-API verification

**Files:**
- Modify: `src/eaa/ingestion/entsoe.py`
- Modify: `tests/ingestion/test_entsoe.py`
- Create: `docs/decisions/0001-entsoe-day-ahead-prices.md`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/ingestion/test_entsoe.py
from datetime import date
from unittest.mock import MagicMock, patch

from eaa import warehouse


def test_fetch_day_ahead_prices_calls_api_with_expected_params() -> None:
    fixture_xml = FIXTURE.read_text()
    mock_response = MagicMock()
    mock_response.text = fixture_xml
    mock_response.raise_for_status.return_value = None

    with patch("eaa.ingestion.entsoe.requests.get", return_value=mock_response) as mock_get:
        df = entsoe.fetch_day_ahead_prices(date(2026, 1, 1), date(2026, 1, 2), token="test-token")

    assert len(df) == 3
    params = mock_get.call_args.kwargs["params"]
    assert params["securityToken"] == "test-token"
    assert params["documentType"] == "A44"
    assert params["in_Domain"] == entsoe.FRANCE_DOMAIN


def test_backfill_into_chunks_by_year_and_upserts(tmp_path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    fixture_df = entsoe.parse_day_ahead_prices(FIXTURE.read_text())

    with patch("eaa.ingestion.entsoe.fetch_day_ahead_prices", return_value=fixture_df) as mock_fetch:
        entsoe.backfill_into(con, date(2024, 1, 1), date(2026, 6, 1), token="test-token")

    assert mock_fetch.call_count >= 2  # more than 1 year of range -> chunked
    rows = con.execute("SELECT COUNT(*) FROM day_ahead_prices_hourly").fetchone()[0]
    con.close()
    assert rows == 3
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/ingestion/test_entsoe.py -v`
Expected: `FAIL` — `AttributeError: module 'eaa.ingestion.entsoe' has no attribute 'fetch_day_ahead_prices'`

- [ ] **Step 3: Append to `src/eaa/ingestion/entsoe.py`**

```python
import os
from datetime import date, datetime as dt, timedelta, UTC
import requests

from eaa import warehouse

API_URL = "https://web-api.tp.entsoe.eu/api"


def fetch_day_ahead_prices(start: date, end: date, *, token: str | None = None) -> pd.DataFrame:
    """Fetch day-ahead prices for [start, end) (end exclusive), hourly."""
    token = token or os.environ["ENTSOE_API_TOKEN"]
    params = {
        "securityToken": token,
        "documentType": "A44",
        "in_Domain": FRANCE_DOMAIN,
        "out_Domain": FRANCE_DOMAIN,
        "periodStart": start.strftime("%Y%m%d0000"),
        "periodEnd": end.strftime("%Y%m%d0000"),
    }
    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    return parse_day_ahead_prices(response.text)


def backfill_into(con, start_date: date, end_date: date, *, token: str | None = None) -> None:
    """Fetch in <=364-day chunks (ENTSO-E's documented per-request range limit
    for this document type) and upsert each chunk."""
    chunk_start = start_date
    while chunk_start < end_date:
        chunk_end = min(chunk_start + timedelta(days=364), end_date)
        df = fetch_day_ahead_prices(chunk_start, chunk_end, token=token)
        warehouse.upsert_prices(con, df)
        chunk_start = chunk_end


def refresh_into(con, *, token: str | None = None) -> None:
    today = dt.now(UTC).date()
    df = fetch_day_ahead_prices(today - timedelta(days=5), today, token=token)
    warehouse.upsert_prices(con, df)
```

Consolidate the duplicate `datetime`/`UTC`/`timedelta` imports with the ones already
present at the top of the file from Task 7 when applying this step.

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/ingestion/test_entsoe.py -v`
Expected: `PASS` — 4 tests total.

- [ ] **Step 5: Commit the code**

```bash
git add src/eaa/ingestion/entsoe.py tests/ingestion/test_entsoe.py
git commit -m "feat: add ENTSO-E fetch and backfill/refresh orchestration"
```

- [ ] **Step 6: Request ENTSO-E API access**

Create an account at https://transparency.entsoe.eu and email
`transparency@entsoe.eu` from that account requesting a Restful API security
token (per the platform's own "Restful API" documentation page). Turnaround is
unpredictable (minutes to a few days) — this can run in the background while
continuing with later tasks.

- [ ] **Step 7: Verify against the real API once the token arrives**

Add the token to `.env` as `ENTSOE_API_TOKEN=<token>` (never commit `.env` — already
gitignored).

Run:
```bash
uv run python -c "
import os
from datetime import date
from dotenv import load_dotenv
load_dotenv()
from eaa.ingestion.entsoe import fetch_day_ahead_prices
df = fetch_day_ahead_prices(date(2026, 1, 1), date(2026, 1, 2))
print(df)
"
```
Expected: a DataFrame with 24 hourly rows and plausible EUR/MWh prices (roughly
0-300). If this raises `xml.etree.ElementTree.ParseError` or `entsoe.EntsoeError`
instead, the real response shape differs from `tests/fixtures/entsoe_sample.xml`:
capture the real `response.text` just before the `parse_day_ahead_prices` call
above, save it over `tests/fixtures/entsoe_sample.xml`, adjust the `{*}TimeSeries` /
`{*}Period` / `{*}Point` XPath expressions in `parse_day_ahead_prices`
(`src/eaa/ingestion/entsoe.py`) to match what it actually contains, and re-run the
test suite and this command until both pass.

- [ ] **Step 8: Record the outcome as an ADR**

```markdown
<!-- docs/decisions/0001-entsoe-day-ahead-prices.md -->
# ADR 0001: ENTSO-E as the day-ahead price source

## Context
Phase 1's design (docs/superpowers/specs/2026-10-20-warehouse-mcp-design.md) named
the ENTSO-E Transparency Platform as the candidate source for French day-ahead spot
prices, explicitly unverified pending real API access.

## Decision
[Fill in once Step 7 above has run: either "Confirmed as documented — the A44
schema matched tests/fixtures/entsoe_sample.xml exactly" or a description of what
actually differed and how parse_day_ahead_prices was adjusted.]

## Alternatives considered
- RTE's own data portal: no equivalent free day-ahead price dataset found via ODRÉ.
- Scraping the EPEX Spot public results page: rejected — fragile, no stable API.

## Consequences
[Fill in once confirmed: e.g. "Token approval took N days — document for anyone
rebuilding this project from scratch that this step is not instantaneous."]
```

Fill in the three bracketed sections with the real outcome from Step 7 before committing.

```bash
git add docs/decisions/0001-entsoe-day-ahead-prices.md
git commit -m "docs: record ENTSO-E day-ahead price verification"
```

---

## Task 9: Ingestion CLI

**Files:**
- Create: `src/eaa/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from unittest.mock import patch

from eaa import cli


def test_backfill_calls_both_connectors() -> None:
    with (
        patch("eaa.cli.warehouse.get_connection") as mock_get_connection,
        patch("eaa.cli.eco2mix.backfill") as mock_eco2mix_backfill,
        patch("eaa.cli.entsoe.backfill_into") as mock_entsoe_backfill,
    ):
        cli.backfill()

    mock_eco2mix_backfill.assert_called_once()
    mock_entsoe_backfill.assert_called_once()
    mock_get_connection.return_value.close.assert_called_once()


def test_refresh_calls_both_connectors() -> None:
    with (
        patch("eaa.cli.warehouse.get_connection") as mock_get_connection,
        patch("eaa.cli.eco2mix.refresh") as mock_eco2mix_refresh,
        patch("eaa.cli.entsoe.refresh_into") as mock_entsoe_refresh,
    ):
        cli.refresh()

    mock_eco2mix_refresh.assert_called_once()
    mock_entsoe_refresh.assert_called_once()
    mock_get_connection.return_value.close.assert_called_once()
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/test_cli.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.cli'`

- [ ] **Step 3: Implement `src/eaa/cli.py`**

```python
"""Command-line entry points for warehouse ingestion."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime

from dotenv import load_dotenv

from eaa import warehouse
from eaa.ingestion import eco2mix, entsoe

STUDY_WINDOW_START = date(2024, 2, 1)


def backfill() -> None:
    today = datetime.now(UTC).date()
    con = warehouse.get_connection()
    try:
        eco2mix.backfill(con, STUDY_WINDOW_START, today)
        entsoe.backfill_into(con, STUDY_WINDOW_START, today)
    finally:
        con.close()


def refresh() -> None:
    con = warehouse.get_connection()
    try:
        eco2mix.refresh(con)
        entsoe.refresh_into(con)
    finally:
        con.close()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="warehouse")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backfill")
    subparsers.add_parser("refresh")
    args = parser.parse_args()

    if args.command == "backfill":
        backfill()
    elif args.command == "refresh":
        refresh()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/test_cli.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/cli.py tests/test_cli.py
git commit -m "feat: add warehouse backfill/refresh CLI"
```

---

## Task 10: Forecast API client

**Files:**
- Create: `src/eaa/mcp/forecast_client.py`
- Test: `tests/mcp/test_forecast_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_forecast_client.py
from unittest.mock import MagicMock, patch

from eaa.mcp import forecast_client


def test_fetch_latest_forecast_returns_parsed_json() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = [{"date_heure": "2026-01-02T00:00:00", "q50_pred": 55000.0}]
    mock_response.raise_for_status.return_value = None

    with patch("eaa.mcp.forecast_client.requests.get", return_value=mock_response):
        result = forecast_client.fetch_latest_forecast("http://localhost:8000")

    assert result == [{"date_heure": "2026-01-02T00:00:00", "q50_pred": 55000.0}]


def test_fetch_latest_forecast_wraps_connection_errors() -> None:
    import requests

    with patch("eaa.mcp.forecast_client.requests.get", side_effect=requests.ConnectionError("down")):
        try:
            forecast_client.fetch_latest_forecast("http://localhost:8000")
            raised = False
        except forecast_client.ForecastAPIError:
            raised = True
    assert raised


def test_fetch_forecast_history_passes_date_params() -> None:
    from datetime import date

    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None

    with patch("eaa.mcp.forecast_client.requests.get", return_value=mock_response) as mock_get:
        forecast_client.fetch_forecast_history(
            "http://localhost:8000", date(2026, 1, 1), date(2026, 1, 31)
        )

    assert mock_get.call_args.kwargs["params"] == {"start": "2026-01-01", "end": "2026-01-31"}
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/mcp/test_forecast_client.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.mcp.forecast_client'`

- [ ] **Step 3: Implement `src/eaa/mcp/forecast_client.py`**

```python
"""Thin HTTP client for france-electricity-forecasting's serving API."""

from __future__ import annotations

from datetime import date

import requests


class ForecastAPIError(RuntimeError):
    """Raised when the forecasting API is unreachable or returns an error."""


def fetch_latest_forecast(base_url: str) -> list[dict]:
    try:
        response = requests.get(f"{base_url}/forecast/latest", timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ForecastAPIError(f"forecast API unreachable: {exc}") from exc
    return response.json()


def fetch_forecast_history(
    base_url: str, start: date | None = None, end: date | None = None
) -> list[dict]:
    params: dict[str, str] = {}
    if start is not None:
        params["start"] = start.isoformat()
    if end is not None:
        params["end"] = end.isoformat()
    try:
        response = requests.get(f"{base_url}/forecast/history", params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ForecastAPIError(f"forecast API unreachable: {exc}") from exc
    return response.json()
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/mcp/test_forecast_client.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/mcp/forecast_client.py tests/mcp/test_forecast_client.py
git commit -m "feat: add HTTP client for the forecasting API"
```

---

## Task 11: MCP tool logic — `get_schema` and `run_sql_query`

**Files:**
- Create: `src/eaa/mcp/tools.py`
- Test: `tests/mcp/test_tools.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/mcp/test_tools.py
import pandas as pd
import pytest

from eaa import warehouse
from eaa.mcp import tools


@pytest.fixture
def con(tmp_path):
    connection = warehouse.get_connection(tmp_path / "test.duckdb")
    yield connection
    connection.close()


def test_get_schema_lists_tables_and_distinct_sources(con) -> None:
    df = pd.DataFrame(
        {"datetime": pd.to_datetime(["2026-01-01 00:00"]), "source": ["wind"], "production_mw": [100.0]}
    )
    warehouse.upsert_production_mix(con, df)

    description = tools.get_schema_impl(con)

    assert "consumption_hourly" in description
    assert "wind" in description


def test_run_sql_query_rejects_non_select(con) -> None:
    with pytest.raises(ValueError):
        tools.run_sql_query_impl(con, "DELETE FROM consumption_hourly")


def test_run_sql_query_rejects_multiple_statements(con) -> None:
    with pytest.raises(ValueError):
        tools.run_sql_query_impl(con, "SELECT 1; SELECT 2")


def test_run_sql_query_returns_rows_as_dicts(con) -> None:
    df = pd.DataFrame(
        {"datetime": pd.to_datetime(["2026-01-01 00:00"]), "consumption_mw": [42.0]}
    )
    warehouse.upsert_consumption(con, df)

    rows = tools.run_sql_query_impl(con, "SELECT consumption_mw FROM consumption_hourly")

    assert rows == [{"consumption_mw": 42.0}]


def test_run_sql_query_truncates_at_max_rows(con, monkeypatch) -> None:
    monkeypatch.setattr(tools, "MAX_ROWS", 2)
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 02:00"]),
            "consumption_mw": [1.0, 2.0, 3.0],
        }
    )
    warehouse.upsert_consumption(con, df)

    rows = tools.run_sql_query_impl(con, "SELECT consumption_mw FROM consumption_hourly ORDER BY datetime")

    assert len(rows) == 3  # 2 data rows + 1 truncation notice
    assert "_notice" in rows[-1]
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/mcp/test_tools.py -v`
Expected: `FAIL` — `ModuleNotFoundError: No module named 'eaa.mcp.tools'`

- [ ] **Step 3: Implement `src/eaa/mcp/tools.py` (schema + SQL tools only)**

```python
"""Pure functions backing the MCP tools. Unit-tested directly here, so tests
don't need a running MCP server or client; server.py wraps these in thin
@mcp.tool() decorators.
"""

from __future__ import annotations

import duckdb

MAX_ROWS = 500

_SCHEMA_DESCRIPTION = """
consumption_hourly(datetime TIMESTAMP, consumption_mw DOUBLE)
production_by_source_hourly(datetime TIMESTAMP, source VARCHAR, production_mw DOUBLE)
day_ahead_prices_hourly(datetime TIMESTAMP, price_eur_mwh DOUBLE)
""".strip()


def get_schema_impl(con: duckdb.DuckDBPyConnection) -> str:
    sources = con.execute(
        "SELECT DISTINCT source FROM production_by_source_hourly ORDER BY source"
    ).fetchall()
    source_list = ", ".join(row[0] for row in sources) if sources else "(no data ingested yet)"
    return f"{_SCHEMA_DESCRIPTION}\n\nDistinct production_by_source_hourly.source values: {source_list}"


def run_sql_query_impl(con: duckdb.DuckDBPyConnection, query: str) -> list[dict]:
    normalized = query.strip().rstrip(";")
    if ";" in normalized:
        raise ValueError("Only a single SQL statement is allowed")
    if not normalized.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    result = con.execute(normalized)
    columns = [d[0] for d in result.description]
    rows = result.fetchmany(MAX_ROWS + 1)
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    records = [dict(zip(columns, row, strict=True)) for row in rows]
    if truncated:
        records.append(
            {"_notice": f"Result truncated at {MAX_ROWS} rows -- aggregate instead of listing."}
        )
    return records
```

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/mcp/test_tools.py -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add src/eaa/mcp/tools.py tests/mcp/test_tools.py
git commit -m "feat: add get_schema and run_sql_query MCP tool logic"
```

---

## Task 12: MCP tool logic — forecast tools

**Files:**
- Modify: `src/eaa/mcp/tools.py`
- Modify: `tests/mcp/test_tools.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/mcp/test_tools.py
from unittest.mock import patch

from eaa.mcp.forecast_client import ForecastAPIError


def test_get_latest_forecast_impl_returns_data_on_success() -> None:
    with patch(
        "eaa.mcp.tools.fetch_latest_forecast",
        return_value=[{"date_heure": "2026-01-02T00:00:00", "q50_pred": 55000.0}],
    ):
        result = tools.get_latest_forecast_impl("http://localhost:8000")

    assert result == [{"date_heure": "2026-01-02T00:00:00", "q50_pred": 55000.0}]


def test_get_latest_forecast_impl_returns_error_dict_on_failure() -> None:
    with patch(
        "eaa.mcp.tools.fetch_latest_forecast", side_effect=ForecastAPIError("forecast API unreachable: down")
    ):
        result = tools.get_latest_forecast_impl("http://localhost:8000")

    assert result == {"error": "forecast API unreachable: down"}


def test_get_forecast_history_impl_rejects_invalid_date() -> None:
    result = tools.get_forecast_history_impl("http://localhost:8000", "not-a-date", None)
    assert "error" in result


def test_get_forecast_history_impl_returns_data_on_success() -> None:
    with patch("eaa.mcp.tools.fetch_forecast_history", return_value=[{"date_heure": "2026-01-01T00:00:00"}]):
        result = tools.get_forecast_history_impl("http://localhost:8000", "2026-01-01", "2026-01-02")

    assert result == [{"date_heure": "2026-01-01T00:00:00"}]
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/mcp/test_tools.py -v`
Expected: `FAIL` — `AttributeError: module 'eaa.mcp.tools' has no attribute 'get_latest_forecast_impl'`

- [ ] **Step 3: Append to `src/eaa/mcp/tools.py`**

```python
from datetime import date

from eaa.mcp.forecast_client import ForecastAPIError, fetch_forecast_history, fetch_latest_forecast


def get_latest_forecast_impl(base_url: str) -> list[dict] | dict:
    try:
        return fetch_latest_forecast(base_url)
    except ForecastAPIError as exc:
        return {"error": str(exc)}


def get_forecast_history_impl(
    base_url: str, start: str | None, end: str | None
) -> list[dict] | dict:
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
    except ValueError as exc:
        return {"error": f"invalid date: {exc}"}

    try:
        return fetch_forecast_history(base_url, start_date, end_date)
    except ForecastAPIError as exc:
        return {"error": str(exc)}
```

Move the `from datetime import date` and the `eaa.mcp.forecast_client` import to
the top of the file with the existing `duckdb` import when applying this step.

- [ ] **Step 4: Run and confirm success**

Run: `uv run pytest tests/mcp/test_tools.py -v`
Expected: `PASS` — 9 tests total.

- [ ] **Step 5: Commit**

```bash
git add src/eaa/mcp/tools.py tests/mcp/test_tools.py
git commit -m "feat: add forecast MCP tool logic with clean error handling"
```

---

## Task 13: MCP server wiring and manual end-to-end verification

**Files:**
- Create: `src/eaa/mcp/server.py`

- [ ] **Step 1: Implement `src/eaa/mcp/server.py`**

```python
"""MCP server exposing the DuckDB warehouse and project 1's forecasting API as
tools, over streamable-http. Run standalone: `uv run eaa-mcp-server`.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from eaa import warehouse
from eaa.mcp.tools import (
    get_forecast_history_impl,
    get_latest_forecast_impl,
    get_schema_impl,
    run_sql_query_impl,
)

load_dotenv()
FORECAST_API_URL = os.environ.get("FORECAST_API_URL", "http://localhost:8000")

mcp = FastMCP("energy-analyst-agent-warehouse")


@mcp.tool()
def get_schema() -> str:
    """Describe the warehouse tables, columns, and available production sources."""
    con = warehouse.get_connection(read_only=True)
    try:
        return get_schema_impl(con)
    finally:
        con.close()


@mcp.tool()
def run_sql_query(query: str) -> list[dict]:
    """Run a read-only SELECT query against the warehouse and return the rows."""
    con = warehouse.get_connection(read_only=True)
    try:
        return run_sql_query_impl(con, query)
    finally:
        con.close()


@mcp.tool()
def get_latest_forecast() -> list[dict] | dict:
    """Get tomorrow's electricity consumption forecast from the forecasting API."""
    return get_latest_forecast_impl(FORECAST_API_URL)


@mcp.tool()
def get_forecast_history(start: str | None = None, end: str | None = None) -> list[dict] | dict:
    """Get historical forecast-vs-actual-vs-RTE data (ISO dates, both optional)."""
    return get_forecast_history_impl(FORECAST_API_URL, start, end)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests pass (`server.py` itself has no new unit tests — its 4 functions
are thin wrappers already covered by `test_tools.py` and `test_warehouse.py`).

- [ ] **Step 3: Manually verify a real backfill**

```bash
uv run warehouse backfill
```
Expected: completes without errors (may take a few minutes); creates `warehouse.duckdb`.

```bash
uv run python -c "
from eaa import warehouse
con = warehouse.get_connection(read_only=True)
for table in ('consumption_hourly', 'production_by_source_hourly', 'day_ahead_prices_hourly'):
    print(table, con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0])
con.close()
"
```
Expected: three non-zero row counts.

- [ ] **Step 4: Manually verify the MCP server starts and serves tools**

```bash
uv run eaa-mcp-server
```
Expected: starts without errors and logs that it is listening (default
`streamable-http` port, typically `8000` unless project 1's API is already using
it — if so, note the actual port printed at startup for Phase 2's agent
configuration). Stop with Ctrl+C once confirmed it started cleanly.

- [ ] **Step 5: Commit**

```bash
git add src/eaa/mcp/server.py
git commit -m "feat: wire up the MCP server exposing warehouse and forecast tools"
```

---

## Task 14: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update `README.md`**

```markdown
# energy-analyst-agent
LLM agent answering analytical questions on the French power system using SQL, forecasting and weather tools. Evaluated on a custom benchmark for accuracy, tool use, cost and latency.

See [`docs/superpowers/specs/`](docs/superpowers/specs/) for design specs (one per
phase) and [`docs/decisions/`](docs/decisions/) for ADRs.

## Status

**Phase 1 — shipped**: a DuckDB data warehouse (consumption, production mix by
source, day-ahead spot prices — RTE éCO2mix + ENTSO-E) and an MCP server exposing
it, plus project 1's forecasting API (`france-electricity-forecasting`), as four
tools (`get_schema`, `run_sql_query`, `get_latest_forecast`, `get_forecast_history`).

**Phase 2 — ahead**: a LangGraph agent (MCP client), served over FastAPI and a CLI.

**Phase 3 — ahead**: a custom benchmark comparing Claude against two local Ollama
models on accuracy, tool use, cost and latency, traced with Langfuse.

## Getting started (Phase 1)

```bash
uv sync --extra dev
cp .env.example .env   # fill in ENTSOE_API_TOKEN (see docs/decisions/0001-entsoe-day-ahead-prices.md)

uv run warehouse backfill   # builds warehouse.duckdb from RTE éCO2mix + ENTSO-E
uv run warehouse refresh    # incremental update

uv run eaa-mcp-server        # serves get_schema / run_sql_query / get_latest_forecast / get_forecast_history
```

```bash
uv run pytest        # test suite
uv run ruff check .  # lint
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with Phase 1 status and getting-started instructions"
```

---

## Plan self-review notes

- **Spec coverage**: data sources (Task 4-9), schema (Task 2-3), "why a new
  connector" (Task 4's docstring), MCP server and all 4 tools with safeguards
  (Task 11-13), testing approach — fixtures/mocks only, no live API calls in the
  suite (every test task), out-of-scope items (Airflow, public deployment,
  additional data) — deliberately absent from every task, matching the spec.
- **Open point carried forward correctly**: ENTSO-E's unverified format is
  implemented against the documented schema (Task 7) with an explicit, concrete
  verification-and-correction procedure (Task 8) rather than being silently assumed
  correct.
- **Type/signature consistency checked**: `warehouse.get_connection`,
  `upsert_consumption`/`upsert_production_mix`/`upsert_prices`,
  `eco2mix.fetch_records`/`consumption_hourly`/`production_mix_hourly`/`backfill`/`refresh`,
  `entsoe.parse_day_ahead_prices`/`fetch_day_ahead_prices`/`backfill_into`/`refresh_into`,
  `forecast_client.fetch_latest_forecast`/`fetch_forecast_history`/`ForecastAPIError`,
  and `tools.get_schema_impl`/`run_sql_query_impl`/`get_latest_forecast_impl`/`get_forecast_history_impl`
  are each defined once and used with matching names/signatures in every later task
  that calls them.
