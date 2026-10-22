"""Per-model pricing and cost calculation from LangChain usage_metadata.

Ollama models are priced at $0/token -- this is an honest simplification, not
an estimate of the real cost: running a local model costs compute/hardware
time, not a per-token price, and this benchmark doesn't attempt to put a
dollar figure on that. The report should be read as "the Claude arm's real
API cost" next to "the local arms' $0 API cost", not as a full TCO comparison.
"""

from __future__ import annotations

PRICING_USD_PER_MILLION_TOKENS = {
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
}


def compute_cost(model_key: str, messages: list) -> float:
    """Sum usage_metadata across messages and price it for the given model.
    Unlisted models (including every Ollama model) cost $0."""
    pricing = PRICING_USD_PER_MILLION_TOKENS.get(model_key)
    if pricing is None:
        return 0.0

    input_tokens = 0
    output_tokens = 0
    for message in messages:
        usage = getattr(message, "usage_metadata", None)
        if usage:
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)

    return (input_tokens / 1_000_000) * pricing["input"] + (
        output_tokens / 1_000_000
    ) * pricing["output"]
