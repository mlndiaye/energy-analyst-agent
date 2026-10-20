"""RTE éCO2mix connector (via the ODRÉ Explore v2.1 API) — consumption and
production mix by source. Independent of france-electricity-forecasting's own
rte.py connector (same public API, rewritten here so this project stays
self-contained — see the design spec's "why a new connector" section).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import requests

RECORDS_URL = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/{dataset}/records"

CONS_DEF_DATASET = "eco2mix-national-cons-def"
TR_DATASET = "eco2mix-national-tr"

# French éCO2mix field name -> English warehouse source name.
SOURCE_FIELDS = {
    "nucleaire": "nuclear",
    "eolien": "wind",
    "solaire": "solar",
    "hydraulique": "hydro",
    "gaz": "gas",
}
FIELDS = ["date_heure", "consommation", *SOURCE_FIELDS]
PAGE_SIZE = 100

# eco2mix-national-tr only keeps a rolling window (~3 months, per the ODRÉ
# dataset description); anything older must come from cons-def instead. Computed
# relative to "today" rather than hardcoded, so this connector doesn't need a
# manually-updated boundary date as time passes.
TR_WINDOW_DAYS = 90


def fetch_records(dataset: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch every record of `dataset` with date_heure in [start_date, end_date], inclusive.

    Paginates by cursoring on date_heure (not offset: the API hard-caps
    offset + limit at 10,000). The cursor is inclusive, so the last row of a
    page is re-requested as the first row of the next page; rows already seen
    (by date_heure) are dropped to deduplicate.
    """
    end_exclusive = end_date + timedelta(days=1)
    cursor = start_date.isoformat()
    rows: list[dict] = []
    seen: set[str] = set()

    while True:
        where = f"date_heure >= '{cursor}' AND date_heure < '{end_exclusive.isoformat()}'"
        response = requests.get(
            RECORDS_URL.format(dataset=dataset),
            params={
                "select": ",".join(FIELDS),
                "where": where,
                "order_by": "date_heure",
                "limit": PAGE_SIZE,
            },
            timeout=30,
        )
        response.raise_for_status()
        page = response.json()["results"]
        if not page:
            break

        new_rows = []
        for r in page:
            if r["date_heure"] not in seen:
                new_rows.append(r)
                seen.add(r["date_heure"])

        if not new_rows and len(page) == PAGE_SIZE:
            raise RuntimeError(
                f"éCO2mix pagination made no progress at cursor {cursor!r} -- more "
                f"than {PAGE_SIZE} records appear to share one date_heure."
            )
        rows.extend(new_rows)

        if len(page) < PAGE_SIZE:
            break
        cursor = page[-1]["date_heure"]

    return pd.DataFrame(rows, columns=FIELDS)
