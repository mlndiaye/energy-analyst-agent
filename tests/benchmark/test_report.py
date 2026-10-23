from dataclasses import dataclass

from eaa.benchmark import report


@dataclass
class _FakeRunResult:
    question_id: str
    category: str
    model_key: str
    correct: bool
    all_expected_tools_called: bool
    cost_usd: float
    latency_seconds: float


def _results() -> list[_FakeRunResult]:
    return [
        _FakeRunResult("lookup-1", "lookup", "gemini-3.5-flash", True, True, 0.01, 1.2),
        _FakeRunResult("lookup-2", "lookup", "gemini-3.5-flash", False, True, 0.01, 1.1),
        _FakeRunResult("lookup-1", "lookup", "ollama:llama3.2", False, False, 0.0, 2.5),
        _FakeRunResult("lookup-2", "lookup", "ollama:llama3.2", True, True, 0.0, 2.1),
    ]


def test_render_markdown_includes_a_row_per_model() -> None:
    markdown = report.render_markdown(_results())
    assert "gemini-3.5-flash" in markdown
    assert "ollama:llama3.2" in markdown


def test_render_markdown_reports_correct_accuracy_percentage() -> None:
    markdown = report.render_markdown(_results())
    # gemini-3.5-flash: 1/2 correct = 50%
    assert "50.0%" in markdown


def test_render_markdown_reports_average_cost_and_latency() -> None:
    markdown = report.render_markdown(_results())
    # gemini-3.5-flash average cost: (0.01 + 0.01) / 2 = 0.01
    assert "0.0100" in markdown or "$0.01" in markdown


def test_render_markdown_includes_an_interpretation_note() -> None:
    # A 0% accuracy row can mean two very different things -- a provider
    # quota exhausting a model's retries, or a model genuinely failing the
    # task (e.g. guessing a wrong SQL schema instead of calling get_schema
    # first) -- and this table alone can't tell them apart. The report must
    # point readers at the per-run `error` field (in benchmark_results.json)
    # instead of letting a bare percentage be read as a capability score.
    markdown = report.render_markdown(_results())
    assert "error" in markdown.lower()
    assert "benchmark_results.json" in markdown
