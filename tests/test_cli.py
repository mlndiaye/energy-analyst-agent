from unittest.mock import patch

import pytest

from eaa import cli


def test_backfill_calls_both_connectors() -> None:
    with (
        patch("eaa.cli.warehouse.get_connection") as mock_get_connection,
        patch("eaa.cli.eco2mix.backfill") as mock_eco2mix_backfill,
        patch("eaa.cli.entsoe.backfill_into") as mock_entsoe_backfill,
    ):
        cli.backfill()

    mock_eco2mix_backfill.assert_called_once()
    mock_entsoe_backfill.assert_called_once()
    mock_get_connection.return_value.close.assert_called_once()


def test_refresh_calls_both_connectors() -> None:
    with (
        patch("eaa.cli.warehouse.get_connection") as mock_get_connection,
        patch("eaa.cli.eco2mix.refresh") as mock_eco2mix_refresh,
        patch("eaa.cli.entsoe.refresh_into") as mock_entsoe_refresh,
    ):
        cli.refresh()

    mock_eco2mix_refresh.assert_called_once()
    mock_entsoe_refresh.assert_called_once()
    mock_get_connection.return_value.close.assert_called_once()


def test_main_exits_when_entsoe_token_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENTSOE_API_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv", ["warehouse", "backfill"])

    with patch("eaa.cli.backfill") as mock_backfill, pytest.raises(SystemExit):
        cli.main()

    mock_backfill.assert_not_called()


def test_main_proceeds_when_entsoe_token_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTSOE_API_TOKEN", "fake-token")
    monkeypatch.setattr("sys.argv", ["warehouse", "backfill"])

    with patch("eaa.cli.backfill") as mock_backfill:
        cli.main()

    mock_backfill.assert_called_once()
