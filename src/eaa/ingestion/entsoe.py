"""ENTSO-E Transparency Platform connector for French day-ahead spot prices.

Targets the A44 (price) document schema as publicly documented. `{*}` wildcard
namespace matching is used throughout so a minor schema-version change in
ENTSO-E's namespace URI doesn't silently break parsing. Not yet verified against
a real response — see Task 8 / docs/decisions/0001-entsoe-day-ahead-prices.md.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from xml.etree import ElementTree as ET

import pandas as pd
import requests

from eaa import warehouse

FRANCE_DOMAIN = "10YFR-RTE------C"  # EIC code for the French bidding zone
API_URL = "https://web-api.tp.entsoe.eu/api"


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
                try:
                    position = int(point.findtext("{*}position"))
                    price = float(point.findtext("{*}price.amount"))
                except (TypeError, ValueError) as exc:
                    raise EntsoeError(
                        f"Malformed Point in ENTSO-E response at period starting {start_str}: {exc}"
                    ) from exc
                rows.append(
                    {
                        # naive UTC: warehouse.upsert_prices requires one consistent
                        # datetime dtype across the batch
                        "datetime": (period_start + timedelta(hours=position - 1)).replace(
                            tzinfo=None
                        ),
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
    """Re-fetch the last 5 days through today (ENTSO-E day-ahead prices can be
    revised shortly after initial publication)."""
    today = datetime.now(UTC).date()
    df = fetch_day_ahead_prices(today - timedelta(days=5), today, token=token)
    warehouse.upsert_prices(con, df)
