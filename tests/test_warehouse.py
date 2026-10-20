from pathlib import Path

import pandas as pd

from eaa import warehouse


def test_get_connection_creates_the_three_tables(tmp_path: Path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    con.close()
    assert tables == {
        "consumption_hourly",
        "production_by_source_hourly",
        "day_ahead_prices_hourly",
    }


def test_upsert_consumption_is_idempotent_and_updates(tmp_path: Path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 01:00"]),
            "consumption_mw": [100.0, 110.0],
        }
    )
    warehouse.upsert_consumption(con, df)
    warehouse.upsert_consumption(con, df)  # re-running must not duplicate rows

    rows = con.execute("SELECT COUNT(*) FROM consumption_hourly").fetchone()
    assert rows[0] == 2

    update = pd.DataFrame(
        {"datetime": pd.to_datetime(["2026-01-01 00:00"]), "consumption_mw": [999.0]}
    )
    warehouse.upsert_consumption(con, update)
    value = con.execute(
        "SELECT consumption_mw FROM consumption_hourly WHERE datetime = '2026-01-01 00:00'"
    ).fetchone()
    con.close()
    assert value[0] == 999.0


def test_upsert_production_mix_is_idempotent_and_updates(tmp_path: Path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:00"]),
            "source": ["nuclear", "wind"],
            "production_mw": [40000.0, 3000.0],
        }
    )
    warehouse.upsert_production_mix(con, df)
    warehouse.upsert_production_mix(con, df)

    rows = con.execute("SELECT COUNT(*) FROM production_by_source_hourly").fetchone()
    assert rows[0] == 2

    update = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00"]),
            "source": ["wind"],
            "production_mw": [3500.0],
        }
    )
    warehouse.upsert_production_mix(con, update)
    value = con.execute(
        "SELECT production_mw FROM production_by_source_hourly "
        "WHERE datetime = '2026-01-01 00:00' AND source = 'wind'"
    ).fetchone()
    con.close()
    assert value[0] == 3500.0


def test_upsert_prices_is_idempotent_and_updates(tmp_path: Path) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    df = pd.DataFrame({"datetime": pd.to_datetime(["2026-01-01 00:00"]), "price_eur_mwh": [45.0]})
    warehouse.upsert_prices(con, df)
    warehouse.upsert_prices(con, df)

    rows = con.execute("SELECT COUNT(*) FROM day_ahead_prices_hourly").fetchone()
    assert rows[0] == 1

    update = pd.DataFrame(
        {"datetime": pd.to_datetime(["2026-01-01 00:00"]), "price_eur_mwh": [50.0]}
    )
    warehouse.upsert_prices(con, update)
    value = con.execute(
        "SELECT price_eur_mwh FROM day_ahead_prices_hourly WHERE datetime = '2026-01-01 00:00'"
    ).fetchone()
    con.close()
    assert value[0] == 50.0


def test_upsert_consumption_keeps_last_value_on_intra_batch_duplicate_key(
    tmp_path: Path,
) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:00"]),
            "consumption_mw": [100.0, 200.0],
        }
    )
    warehouse.upsert_consumption(con, df)
    rows = con.execute("SELECT COUNT(*) FROM consumption_hourly").fetchone()
    value = con.execute(
        "SELECT consumption_mw FROM consumption_hourly WHERE datetime = '2026-01-01 00:00'"
    ).fetchone()
    con.close()
    assert rows[0] == 1
    assert value[0] == 200.0


def test_upsert_production_mix_keeps_last_value_on_intra_batch_duplicate_key(
    tmp_path: Path,
) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:00"]),
            "source": ["wind", "wind"],
            "production_mw": [3000.0, 3500.0],
        }
    )
    warehouse.upsert_production_mix(con, df)
    rows = con.execute("SELECT COUNT(*) FROM production_by_source_hourly").fetchone()
    value = con.execute(
        "SELECT production_mw FROM production_by_source_hourly "
        "WHERE datetime = '2026-01-01 00:00' AND source = 'wind'"
    ).fetchone()
    con.close()
    assert rows[0] == 1
    assert value[0] == 3500.0


def test_upsert_prices_keeps_last_value_on_intra_batch_duplicate_key(
    tmp_path: Path,
) -> None:
    con = warehouse.get_connection(tmp_path / "test.duckdb")
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:00"]),
            "price_eur_mwh": [45.0, 50.0],
        }
    )
    warehouse.upsert_prices(con, df)
    rows = con.execute("SELECT COUNT(*) FROM day_ahead_prices_hourly").fetchone()
    value = con.execute(
        "SELECT price_eur_mwh FROM day_ahead_prices_hourly WHERE datetime = '2026-01-01 00:00'"
    ).fetchone()
    con.close()
    assert rows[0] == 1
    assert value[0] == 50.0
