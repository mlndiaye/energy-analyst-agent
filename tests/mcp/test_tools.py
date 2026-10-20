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
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00"]),
            "source": ["wind"],
            "production_mw": [100.0],
        }
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
    df = pd.DataFrame({"datetime": pd.to_datetime(["2026-01-01 00:00"]), "consumption_mw": [42.0]})
    warehouse.upsert_consumption(con, df)

    rows = tools.run_sql_query_impl(con, "SELECT consumption_mw FROM consumption_hourly")

    assert rows == [{"consumption_mw": 42.0}]


def test_run_sql_query_truncates_at_max_rows(con, monkeypatch) -> None:
    monkeypatch.setattr(tools, "MAX_ROWS", 2)
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                ["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 02:00"]
            ),
            "consumption_mw": [1.0, 2.0, 3.0],
        }
    )
    warehouse.upsert_consumption(con, df)

    rows = tools.run_sql_query_impl(
        con, "SELECT consumption_mw FROM consumption_hourly ORDER BY datetime"
    )

    assert len(rows) == 3  # 2 data rows + 1 truncation notice
    assert "_notice" in rows[-1]
