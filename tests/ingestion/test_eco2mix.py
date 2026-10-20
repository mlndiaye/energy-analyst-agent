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
