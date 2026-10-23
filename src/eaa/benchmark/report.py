"""Renders a markdown summary table from a list of benchmark RunResults."""

from __future__ import annotations

from collections import defaultdict


def _percentage(count: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{100 * count / total:.1f}%"


def render_markdown(results: list) -> str:
    """One row per model: overall accuracy %, tool-use %, avg cost, avg latency."""
    by_model: dict[str, list] = defaultdict(list)
    for r in results:
        by_model[r.model_key].append(r)

    lines = [
        "| Model | Accuracy | Tool use | Avg cost (USD) | Avg latency (s) | N |",
        "|---|---|---|---|---|---|",
    ]
    for model_key, rows in sorted(by_model.items()):
        n = len(rows)
        correct = sum(1 for r in rows if r.correct)
        tool_ok = sum(1 for r in rows if r.all_expected_tools_called)
        avg_cost = sum(r.cost_usd for r in rows) / n
        avg_latency = sum(r.latency_seconds for r in rows) / n
        lines.append(
            f"| {model_key} | {_percentage(correct, n)} | {_percentage(tool_ok, n)} "
            f"| ${avg_cost:.4f} | {avg_latency:.2f} | {n} |"
        )

    lines.append("")
    lines.append("### By category")
    lines.append("")
    lines.append("| Model | Category | Accuracy | Tool use | N |")
    lines.append("|---|---|---|---|---|")
    by_model_category: dict[tuple[str, str], list] = defaultdict(list)
    for r in results:
        by_model_category[(r.model_key, r.category)].append(r)
    for (model_key, category), rows in sorted(by_model_category.items()):
        n = len(rows)
        correct = sum(1 for r in rows if r.correct)
        tool_ok = sum(1 for r in rows if r.all_expected_tools_called)
        lines.append(
            f"| {model_key} | {category} | {_percentage(correct, n)} "
            f"| {_percentage(tool_ok, n)} | {n} |"
        )

    lines.append("")
    lines.append("### Interpreting this report")
    lines.append("")
    lines.append(
        "A low or 0% accuracy row does not by itself mean the model failed the "
        'task. Two very different situations both show up as "incorrect" here '
        "and this table cannot tell them apart:"
    )
    lines.append(
        "- **The model was never really tested** -- e.g. a cloud provider's "
        "rate limit was hit repeatedly enough to exhaust retries, so the "
        '"answer" is actually an error message, not a real attempt.'
    )
    lines.append(
        "- **The model genuinely failed the task** -- e.g. it guessed at a "
        "table/column name instead of calling `get_schema` first, got a SQL "
        "error back, and (correctly, per its instructions) reported the data "
        "as unavailable rather than inventing a number."
    )
    lines.append(
        "Before reading a percentage as a capability score, check the `error` "
        "field and the tool-call trace for the relevant rows in "
        "`benchmark_results.json` (one JSON object per question/model run)."
    )

    return "\n".join(lines)
