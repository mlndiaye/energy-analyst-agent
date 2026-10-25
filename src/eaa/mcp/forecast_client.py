"""Thin HTTP client for france-electricity-forecasting's serving API."""

from __future__ import annotations

import json
from datetime import date

import requests


class ForecastAPIError(RuntimeError):
    """Raised when the forecasting API is unreachable or returns an error."""


def fetch_latest_forecast(base_url: str) -> list[dict]:
    """Fetch the most recent day-ahead forecast from GET /forecast/latest."""
    try:
        response = requests.get(f"{base_url}/forecast/latest", timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        raise ForecastAPIError(f"forecast API error: {exc}") from exc


def fetch_forecast_history(
    base_url: str, start: date | None = None, end: date | None = None
) -> list[dict]:
    """Fetch past forecasts from GET /forecast/history, optionally bounded by [start, end]."""
    params: dict[str, str] = {}
    if start is not None:
        params["start"] = start.isoformat()
    if end is not None:
        params["end"] = end.isoformat()
    try:
        response = requests.get(f"{base_url}/forecast/history", params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        raise ForecastAPIError(f"forecast API error: {exc}") from exc
