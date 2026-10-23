"""Pure scoring functions: answer-text accuracy and tool-use recall.
No model, warehouse, or network dependency -- fully unit-testable.
"""

from __future__ import annotations

import re

import duckdb

# Matches the first number-looking substring: optional sign, digits, optional
# decimal part. Does not special-case thousands separators (",") -- a comma is
# read as a decimal point, same as "." -- because the benchmark's own questions
# never produce thousands-separated answers at the scale this warehouse's
# values reach (consumption/production in MW, prices in EUR/MWh are all well
# under 1,000,000 and rarely written with a thousands separator by the model).
_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def extract_last_number(text: str) -> float | None:
    """Return the last number found in free text, or None if there isn't one.

    The last number, not the first: a small local model often restates part
    of the question (e.g. "over the most recent 7 days...") before giving its
    actual answer, and taking the first number then extracts "7" instead of
    the real value.
    """
    matches = list(_NUMBER_RE.finditer(text))
    if not matches:
        return None
    return float(matches[-1].group().replace(",", "."))


def score_accuracy(question, con: duckdb.DuckDBPyConnection | None, answer_text: str) -> dict:
    """Compare the agent's extracted numeric answer to the question's live
    ground truth, within its tolerance."""
    expected = question.ground_truth_fn(con)
    extracted = extract_last_number(answer_text)
    correct = extracted is not None and abs(extracted - expected) <= question.tolerance
    return {"expected": expected, "extracted": extracted, "correct": correct}


def score_tool_use(question, tool_calls: list[dict]) -> dict:
    """Check that every tool the question expects was called at least once.
    An extra, unexpected call doesn't fail this check -- only a missing
    expected one does."""
    called_names = {call["name"] for call in tool_calls}
    missing = [name for name in question.expected_tools if name not in called_names]
    return {
        "called_tools": sorted(called_names),
        "missing_tools": missing,
        "all_expected_called": len(missing) == 0,
    }
