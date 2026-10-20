"""RTE éCO2mix connector (via the ODRÉ Explore v2.1 API) — consumption and
production mix by source. Independent of france-electricity-forecasting's own
rte.py connector (same public API, rewritten here so this project stays
self-contained — see the design spec's "why a new connector" section).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import requests

from eaa import warehouse

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
        body = response.json()
        if "results" not in body:
            raise RuntimeError(
                f"éCO2mix response for dataset={dataset!r} cursor={cursor!r} missing "
                f"'results' key (HTTP {response.status_code}): {body!r}"
            )
        page = body["results"]
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


def _to_hourly(df: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    working = df.copy()
    working["datetime"] = pd.to_datetime(working["date_heure"], utc=True).dt.tz_localize(None)
    for col in value_cols:
        working[col] = pd.to_numeric(working[col], errors="coerce")
    hourly = working.set_index("datetime")[value_cols].resample("1h").mean()
    return hourly.reset_index()


def consumption_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw (sub-hourly) éCO2mix consumption rows to hourly means."""
    hourly = _to_hourly(df, ["consommation"])
    return hourly.rename(columns={"consommation": "consumption_mw"})


def production_mix_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw (sub-hourly) éCO2mix production-by-source rows to hourly
    means, reshaped from wide (one column per French source) to long format
    with English source names.
    """
    source_cols = list(SOURCE_FIELDS)
    hourly = _to_hourly(df, source_cols)
    long_df = hourly.melt(
        id_vars="datetime", value_vars=source_cols, var_name="source_fr", value_name="production_mw"
    )
    long_df["source"] = long_df["source_fr"].map(SOURCE_FIELDS)
    # Keep NaN-valued rows for gap hours (symmetric with consumption_hourly):
    # a NaN row means "no data reported for this hour", a missing row would
    # wrongly mean "this timestamp doesn't exist", breaking joins/counts
    # across the warehouse's hourly tables.
    return long_df[["datetime", "source", "production_mw"]]


def _today() -> date:
    return datetime.now(UTC).date()


def _upsert_all(con, raw_df: pd.DataFrame) -> None:
    warehouse.upsert_consumption(con, consumption_hourly(raw_df))
    warehouse.upsert_production_mix(con, production_mix_hourly(raw_df))


def backfill(con, start_date: date, end_date: date) -> None:
    """Fetch and upsert [start_date, end_date], chaining cons-def (older data)
    and tr (data within TR_WINDOW_DAYS of today).
    """
    tr_start = max(start_date, _today() - timedelta(days=TR_WINDOW_DAYS))

    if start_date < tr_start:
        df = fetch_records(CONS_DEF_DATASET, start_date, tr_start - timedelta(days=1))
        if not df.empty:
            _upsert_all(con, df)

    if end_date >= tr_start:
        df = fetch_records(TR_DATASET, max(start_date, tr_start), end_date)
        if not df.empty:
            _upsert_all(con, df)


def refresh(con) -> None:
    """Re-fetch the last 5 days through today from the tr dataset."""
    today = _today()
    df = fetch_records(TR_DATASET, today - timedelta(days=5), today)
    if not df.empty:
        _upsert_all(con, df)
