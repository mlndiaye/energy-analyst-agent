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
