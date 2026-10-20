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

    with patch(
        "eaa.mcp.forecast_client.requests.get", side_effect=requests.ConnectionError("down")
    ):
        try:
            forecast_client.fetch_latest_forecast("http://localhost:8000")
            raised = False
        except forecast_client.ForecastAPIError:
            raised = True
    assert raised


def test_fetch_latest_forecast_wraps_http_errors() -> None:
    import requests

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("404 Client Error: Not Found")

    with patch("eaa.mcp.forecast_client.requests.get", return_value=mock_response):
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
