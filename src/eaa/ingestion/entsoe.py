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
