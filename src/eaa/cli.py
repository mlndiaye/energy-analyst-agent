"""Command-line entry points for warehouse ingestion."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, date, datetime

from dotenv import load_dotenv

from eaa import warehouse
from eaa.ingestion import eco2mix, entsoe

STUDY_WINDOW_START = date(2024, 2, 1)

REQUIRED_ENV_VARS = ["ENTSOE_API_TOKEN"]


def _check_required_env_vars() -> None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise SystemExit(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Copy .env.example to .env and fill them in."
        )


def backfill() -> None:
    today = datetime.now(UTC).date()
    con = warehouse.get_connection()
    try:
        eco2mix.backfill(con, STUDY_WINDOW_START, today)
        entsoe.backfill_into(con, STUDY_WINDOW_START, today)
    finally:
        con.close()


def refresh() -> None:
    con = warehouse.get_connection()
    try:
        eco2mix.refresh(con)
        entsoe.refresh_into(con)
    finally:
        con.close()


def main() -> None:
    load_dotenv()
    _check_required_env_vars()
    parser = argparse.ArgumentParser(prog="warehouse")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backfill")
    subparsers.add_parser("refresh")
    args = parser.parse_args()

    if args.command == "backfill":
        backfill()
    elif args.command == "refresh":
        refresh()


if __name__ == "__main__":
    main()
