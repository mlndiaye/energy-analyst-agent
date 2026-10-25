from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from eaa.benchmark import cli


@dataclass
class _FakeRunResult:
    model_key: str


def test_main_builds_three_models_and_runs_the_benchmark(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake_results = [_FakeRunResult(model_key="gemini-3.5-flash")]

    with (
        patch("eaa.benchmark.cli.get_mcp_tools", AsyncMock(return_value=[])),
        patch("eaa.benchmark.cli.warehouse.get_connection", return_value=MagicMock()),
        patch("eaa.benchmark.cli.init_chat_model", return_value=MagicMock()),
        patch("eaa.benchmark.cli.build_langfuse_callbacks", return_value=None),
        patch("eaa.benchmark.cli.run_benchmark", AsyncMock(return_value=fake_results)) as mock_run,
        patch("eaa.benchmark.cli.render_markdown", return_value="# report") as mock_render,
    ):
        cli.main()

    mock_run.assert_called_once()
    models_arg = mock_run.call_args.args[0]
    assert set(models_arg.keys()) == {"gemini-3.5-flash", "ollama:llama3.2", "ollama:llama3.1:8b"}
    mock_render.assert_called_once_with(fake_results)
    assert (tmp_path / "docs" / "benchmark_report.md").exists()
    assert (tmp_path / "benchmark_results.json").exists()


def test_build_langfuse_callbacks_returns_none_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert cli.build_langfuse_callbacks() is None


def test_main_caps_ollama_output_tokens(tmp_path, monkeypatch) -> None:
    # A local model with no output cap can fall into a degenerate generation
    # loop and never stop -- seen for real as a single llama3.2 call that ran
    # for 2h17m and emitted 327k tokens before Ollama's own safety limit cut
    # it off. num_predict bounds the damage from a future recurrence to a
    # bounded number of tokens instead of hours of wall-clock time.
    monkeypatch.chdir(tmp_path)
    fake_results = [_FakeRunResult(model_key="gemini-3.5-flash")]

    with (
        patch("eaa.benchmark.cli.get_mcp_tools", AsyncMock(return_value=[])),
        patch("eaa.benchmark.cli.warehouse.get_connection", return_value=MagicMock()),
        patch("eaa.benchmark.cli.init_chat_model", return_value=MagicMock()) as mock_init,
        patch("eaa.benchmark.cli.build_langfuse_callbacks", return_value=None),
        patch("eaa.benchmark.cli.run_benchmark", AsyncMock(return_value=fake_results)),
        patch("eaa.benchmark.cli.render_markdown", return_value="# report"),
    ):
        cli.main()

    ollama_calls = {
        call.args[0]: call.kwargs for call in mock_init.call_args_list if "ollama" in call.args[0]
    }
    assert set(ollama_calls.keys()) == {"ollama:llama3.2", "ollama:llama3.1:8b"}
    for kwargs in ollama_calls.values():
        assert kwargs.get("num_predict") is not None
