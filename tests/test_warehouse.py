from pathlib import Path

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
