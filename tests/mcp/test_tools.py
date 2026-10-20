from unittest.mock import patch

import duckdb
import pandas as pd
import pytest

from eaa import warehouse
from eaa.mcp import tools
from eaa.mcp.forecast_client import ForecastAPIError


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


def test_run_sql_query_accepts_cte(con) -> None:
    rows = tools.run_sql_query_impl(con, "WITH t AS (SELECT 1 AS x) SELECT * FROM t")

    assert rows == [{"x": 1}]


def test_run_sql_query_works_against_read_only_connection(tmp_path) -> None:
    db_path = tmp_path / "test.duckdb"
    write_con = warehouse.get_connection(db_path)
    df = pd.DataFrame({"datetime": pd.to_datetime(["2026-01-01 00:00"]), "consumption_mw": [42.0]})
    warehouse.upsert_consumption(write_con, df)
    write_con.close()

    read_con = warehouse.get_connection(db_path, read_only=True)
    rows = tools.run_sql_query_impl(read_con, "SELECT consumption_mw FROM consumption_hourly")
    read_con.close()

    assert rows == [{"consumption_mw": 42.0}]


def test_run_sql_query_cte_write_blocked_by_readonly_connection(tmp_path) -> None:
    db_path = tmp_path / "test.duckdb"
    write_con = warehouse.get_connection(db_path)
    df = pd.DataFrame({"datetime": pd.to_datetime(["2026-01-01 00:00"]), "consumption_mw": [42.0]})
    warehouse.upsert_consumption(write_con, df)
    write_con.close()

    read_con = warehouse.get_connection(db_path, read_only=True)
    with pytest.raises(duckdb.Error):
        tools.run_sql_query_impl(read_con, "WITH t AS (SELECT 1) DELETE FROM consumption_hourly")
    read_con.close()


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


def test_get_schema_reports_no_data_when_empty(con) -> None:
    description = tools.get_schema_impl(con)

    assert "(no data ingested yet)" in description


def test_get_latest_forecast_impl_returns_data_on_success() -> None:
    with patch(
        "eaa.mcp.tools.fetch_latest_forecast",
        return_value=[{"date_heure": "2026-01-02T00:00:00", "q50_pred": 55000.0}],
    ):
        result = tools.get_latest_forecast_impl("http://localhost:8000")

    assert result == [{"date_heure": "2026-01-02T00:00:00", "q50_pred": 55000.0}]


def test_get_latest_forecast_impl_returns_error_dict_on_failure() -> None:
    with patch(
        "eaa.mcp.tools.fetch_latest_forecast",
        side_effect=ForecastAPIError("forecast API unreachable: down"),
    ):
        result = tools.get_latest_forecast_impl("http://localhost:8000")

    assert result == {"error": "forecast API unreachable: down"}


def test_get_forecast_history_impl_rejects_invalid_date() -> None:
    result = tools.get_forecast_history_impl("http://localhost:8000", "not-a-date", None)
    assert "error" in result


def test_get_forecast_history_impl_returns_data_on_success() -> None:
    with patch(
        "eaa.mcp.tools.fetch_forecast_history", return_value=[{"date_heure": "2026-01-01T00:00:00"}]
    ):
        result = tools.get_forecast_history_impl(
            "http://localhost:8000", "2026-01-01", "2026-01-02"
        )

    assert result == [{"date_heure": "2026-01-01T00:00:00"}]
