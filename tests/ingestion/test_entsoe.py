from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eaa import warehouse
from eaa.ingestion import entsoe

FIXTURE = Path(__file__).parent.parent / "fixtures" / "entsoe_sample.xml"


def test_parse_day_ahead_prices_reads_hourly_points() -> None:
    xml_text = FIXTURE.read_text()
    df = entsoe.parse_day_ahead_prices(xml_text)

    assert len(df) == 3
    assert df.loc[0, "datetime"] == datetime(2026, 1, 1, 23, 0, tzinfo=UTC).replace(tzinfo=None)
    assert df.loc[0, "price_eur_mwh"] == 45.67
    assert df.loc[2, "datetime"] == datetime(2026, 1, 2, 1, 0, tzinfo=UTC).replace(tzinfo=None)


def test_parse_day_ahead_prices_aggregates_quarter_hourly_points_to_hourly_mean() -> None:
    # ENTSO-E switched French day-ahead prices from PT60M to PT15M resolution
    # on 2025-10-01 (EU-wide 15-minute Market Time Unit rollout). The warehouse
    # stays hourly, so four PT15M points in the same clock hour must average
    # into one row.
    xml_text = (
        '<?xml version="1.0"?>'
        '<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">'
        "<TimeSeries><Period>"
        "<timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T00:00Z</end></timeInterval>"
        "<resolution>PT15M</resolution>"
        "<Point><position>1</position><price.amount>40.0</price.amount></Point>"
        "<Point><position>2</position><price.amount>42.0</price.amount></Point>"
        "<Point><position>3</position><price.amount>44.0</price.amount></Point>"
        "<Point><position>4</position><price.amount>46.0</price.amount></Point>"
        "</Period></TimeSeries>"
        "</Publication_MarketDocument>"
    )
    df = entsoe.parse_day_ahead_prices(xml_text)

    assert len(df) == 1
    assert df.loc[0, "datetime"] == datetime(2026, 1, 1, 23, 0, tzinfo=UTC).replace(tzinfo=None)
    assert df.loc[0, "price_eur_mwh"] == pytest.approx(43.0)


def test_parse_day_ahead_prices_raises_on_empty_response() -> None:
    empty = (
        '<?xml version="1.0"?>'
        '<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">'
        "</Publication_MarketDocument>"
    )
    with pytest.raises(entsoe.EntsoeError):
        entsoe.parse_day_ahead_prices(empty)


def test_parse_day_ahead_prices_wraps_malformed_point_error() -> None:
    malformed = (
        '<?xml version="1.0"?>'
        '<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">'
        "<TimeSeries><Period>"
        "<timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T23:00Z</end></timeInterval>"
        "<resolution>PT60M</resolution>"
        "<Point><position>1</position><price.amount>N/A</price.amount></Point>"
        "</Period></TimeSeries>"
        "</Publication_MarketDocument>"
    )
    with pytest.raises(entsoe.EntsoeError):
        entsoe.parse_day_ahead_prices(malformed)


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

    with patch(
        "eaa.ingestion.entsoe.fetch_day_ahead_prices", return_value=fixture_df
    ) as mock_fetch:
        entsoe.backfill_into(con, date(2024, 1, 1), date(2026, 6, 1), token="test-token")

    assert mock_fetch.call_count >= 2  # more than 1 year of range -> chunked
    rows = con.execute("SELECT COUNT(*) FROM day_ahead_prices_hourly").fetchone()[0]
    con.close()
    assert rows == 3
