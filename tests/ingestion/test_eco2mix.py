from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from eaa import warehouse
from eaa.ingestion import eco2mix


def _page(rows: list[dict], status_code: int = 200) -> object:
    class _Response:
        def __init__(self) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"results": rows}

    return _Response()


def _bad_page(body: dict, status_code: int = 429) -> object:
    class _Response:
        def __init__(self) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return body

    return _Response()


def test_fetch_records_paginates_and_dedups_on_cursor() -> None:
    page1 = [
        {"date_heure": f"2026-01-01T0{i}:00:00+00:00", "consommation": str(1000 + i)}
        for i in range(3)
    ]
    # Last row of page1 (hour 2) is re-sent as the first row of page2 (inclusive cursor).
    page2 = [{"date_heure": "2026-01-01T02:00:00+00:00", "consommation": "1002"}]

    with patch("eaa.ingestion.eco2mix.requests.get") as mock_get:
        mock_get.side_effect = [_page(page1), _page(page2)]
        with patch("eaa.ingestion.eco2mix.PAGE_SIZE", 3):
            df = eco2mix.fetch_records(eco2mix.TR_DATASET, date(2026, 1, 1), date(2026, 1, 1))

    assert len(df) == 3
    assert mock_get.call_count == 2
    assert list(df["date_heure"]) == [row["date_heure"] for row in page1]


def test_fetch_records_raises_on_no_progress_at_full_page() -> None:
    same_timestamp_rows = [{"date_heure": "2026-01-01T00:00:00+00:00", "consommation": "1000"}] * 2

    with patch("eaa.ingestion.eco2mix.requests.get") as mock_get:
        mock_get.return_value = _page(same_timestamp_rows)
        with (
            patch("eaa.ingestion.eco2mix.PAGE_SIZE", 2),
            pytest.raises(eco2mix.Eco2mixError, match="no progress"),
        ):
            eco2mix.fetch_records(eco2mix.TR_DATASET, date(2026, 1, 1), date(2026, 1, 1))


def test_fetch_records_returns_empty_dataframe_with_correct_columns_for_empty_range() -> None:
    with patch("eaa.ingestion.eco2mix.requests.get") as mock_get:
        mock_get.return_value = _page([])
        df = eco2mix.fetch_records(eco2mix.TR_DATASET, date(2026, 1, 1), date(2026, 1, 1))

    assert df.empty
    assert list(df.columns) == eco2mix.FIELDS


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


def test_consumption_hourly_keeps_nan_row_for_a_gap_hour() -> None:
    raw = pd.DataFrame(
        {
            "date_heure": [
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:30:00+00:00",
                # no data at all for the 01:00 hour
                "2026-01-01T02:00:00+00:00",
                "2026-01-01T02:30:00+00:00",
            ],
            "consommation": ["100", "120", "200", "220"],
        }
    )
    result = eco2mix.consumption_hourly(raw)
    assert len(result) == 3
    gap_row = result[result["datetime"] == pd.Timestamp("2026-01-01 01:00:00")].iloc[0]
    assert pd.isna(gap_row["consumption_mw"])


def test_production_mix_hourly_keeps_nan_row_for_a_gap_hour() -> None:
    raw = pd.DataFrame(
        {
            "date_heure": [
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:30:00+00:00",
                # no data at all for the 01:00 hour
                "2026-01-01T02:00:00+00:00",
                "2026-01-01T02:30:00+00:00",
            ],
            "nucleaire": ["40000", "42000", "41000", "41500"],
            "eolien": ["3000", "3200", "3100", "3150"],
            "solaire": ["0", "0", "0", "0"],
            "hydraulique": ["5000", "5100", "5050", "5075"],
            "gaz": ["2000", "2100", "2050", "2075"],
        }
    )
    result = eco2mix.production_mix_hourly(raw)
    gap_rows = result[result["datetime"] == pd.Timestamp("2026-01-01 01:00:00")]
    # The gap hour must still be present, as a NaN-valued row, for every source --
    # not silently dropped. A dropped row would be indistinguishable from "this
    # timestamp doesn't exist", breaking symmetry with consumption_hourly.
    assert set(gap_rows["source"]) == {"nuclear", "wind", "solar", "hydro", "gas"}
    assert gap_rows["production_mw"].isna().all()


def test_fetch_records_raises_runtime_error_on_missing_results_key() -> None:
    with patch("eaa.ingestion.eco2mix.requests.get") as mock_get:
        mock_get.return_value = _bad_page({"error": "rate limited"})
        with pytest.raises(eco2mix.Eco2mixError, match=eco2mix.TR_DATASET):
            eco2mix.fetch_records(eco2mix.TR_DATASET, date(2026, 1, 1), date(2026, 1, 1))


def test_backfill_chains_cons_def_and_tr_and_upserts(tmp_path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    today = date(2026, 6, 1)

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


def test_backfill_bounds_cons_def_fetch_by_end_date_when_entirely_before_tr_window(
    tmp_path,
) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    today = date(2026, 6, 1)

    with (
        patch("eaa.ingestion.eco2mix.fetch_records", return_value=pd.DataFrame()) as mock_fetch,
        patch("eaa.ingestion.eco2mix._today", return_value=today),
    ):
        eco2mix.backfill(con, date(2024, 1, 1), date(2024, 6, 1))
    con.close()

    calls_by_dataset = {call.args[0]: call.args for call in mock_fetch.call_args_list}
    # The whole requested range is older than the TR window, so only cons-def
    # should be fetched -- and its end date must not run past the caller's
    # requested end_date.
    assert eco2mix.TR_DATASET not in calls_by_dataset
    assert calls_by_dataset[eco2mix.CONS_DEF_DATASET] == (
        eco2mix.CONS_DEF_DATASET,
        date(2024, 1, 1),
        date(2024, 6, 1),
    )


def test_backfill_raises_value_error_when_start_after_end() -> None:
    con = warehouse.get_connection(":memory:")
    with (
        patch("eaa.ingestion.eco2mix.fetch_records") as mock_fetch,
        pytest.raises(ValueError, match="must not be after"),
    ):
        eco2mix.backfill(con, date(2026, 6, 1), date(2026, 1, 1))
    con.close()
    mock_fetch.assert_not_called()


def test_refresh_fetches_tr_window_and_upserts(tmp_path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    today = date(2026, 6, 1)

    raw = pd.DataFrame(
        {
            "date_heure": ["2026-05-30T00:00:00+00:00"],
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
        eco2mix.refresh(con)

    mock_fetch.assert_called_once_with(
        eco2mix.TR_DATASET,
        today - timedelta(days=eco2mix.REFRESH_WINDOW_DAYS),
        today,
    )

    consumption_rows = con.execute("SELECT COUNT(*) FROM consumption_hourly").fetchone()[0]
    mix_rows = con.execute("SELECT COUNT(*) FROM production_by_source_hourly").fetchone()[0]
    con.close()
    assert consumption_rows > 0
    assert mix_rows > 0
