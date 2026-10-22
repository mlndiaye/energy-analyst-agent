"""Per-model pricing and cost calculation from LangChain usage_metadata.

Ollama models are priced at $0/token -- this is an honest simplification, not
an estimate of the real cost: running a local model costs compute/hardware
time, not a per-token price, and this benchmark doesn't attempt to put a
dollar figure on that. The report should be read as "the Gemini arm's cost at
paid-tier rates" next to "the local arms' $0 API cost", not as a full TCO
comparison.

The Gemini pricing below is the paid-tier rate, not what this benchmark
actually paid: the benchmark runs against a free-tier Google AI Studio key,
so the real spend is $0. Pricing it at the paid rate keeps the cost column
meaningful (what it would cost at scale) instead of flattening it to $0 next
to Ollama's $0, which would make the cost axis vacuous.
"""

from __future__ import annotations

PRICING_USD_PER_MILLION_TOKENS = {
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
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

    return (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing[
        "output"
    ]
