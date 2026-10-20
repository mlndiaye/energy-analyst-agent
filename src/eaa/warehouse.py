"""DuckDB warehouse: connection, schema, and upsert helpers."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_DB_PATH = Path("warehouse.duckdb")

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS consumption_hourly (
        datetime TIMESTAMP PRIMARY KEY,
        consumption_mw DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS production_by_source_hourly (
        datetime TIMESTAMP,
        source VARCHAR,
        production_mw DOUBLE,
        PRIMARY KEY (datetime, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS day_ahead_prices_hourly (
        datetime TIMESTAMP PRIMARY KEY,
        price_eur_mwh DOUBLE
    )
    """,
]


def get_connection(
    db_path: Path = DEFAULT_DB_PATH, *, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """Open the warehouse. Creates the schema on first write-mode connection."""
    con = duckdb.connect(str(db_path), read_only=read_only)
    if not read_only:
        create_schema(con)
    return con


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    for statement in _SCHEMA_STATEMENTS:
        con.execute(statement)


def upsert_consumption(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    df = df[["datetime", "consumption_mw"]].drop_duplicates(subset=["datetime"], keep="last")
    con.register("_df_consumption", df)
    con.execute(
        """
        INSERT INTO consumption_hourly
        SELECT datetime, consumption_mw FROM _df_consumption
        ON CONFLICT (datetime) DO UPDATE SET consumption_mw = EXCLUDED.consumption_mw
        """
    )
    con.unregister("_df_consumption")


def upsert_production_mix(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    df = df[["datetime", "source", "production_mw"]].drop_duplicates(
        subset=["datetime", "source"], keep="last"
    )
    con.register("_df_production", df)
    con.execute(
        """
        INSERT INTO production_by_source_hourly
        SELECT datetime, source, production_mw FROM _df_production
        ON CONFLICT (datetime, source) DO UPDATE SET production_mw = EXCLUDED.production_mw
        """
    )
    con.unregister("_df_production")


def upsert_prices(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    df = df[["datetime", "price_eur_mwh"]].drop_duplicates(subset=["datetime"], keep="last")
    con.register("_df_prices", df)
    con.execute(
        """
        INSERT INTO day_ahead_prices_hourly
        SELECT datetime, price_eur_mwh FROM _df_prices
        ON CONFLICT (datetime) DO UPDATE SET price_eur_mwh = EXCLUDED.price_eur_mwh
        """
    )
    con.unregister("_df_prices")
