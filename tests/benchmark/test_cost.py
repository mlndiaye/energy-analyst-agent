from eaa.benchmark import cost


class _FakeMessage:
    def __init__(self, usage_metadata: dict | None) -> None:
        self.usage_metadata = usage_metadata


def test_compute_cost_for_claude_sonnet() -> None:
    messages = [
        _FakeMessage(None),  # human message, no usage
        _FakeMessage({"input_tokens": 1_000_000, "output_tokens": 1_000_000}),
    ]
    result = cost.compute_cost("claude-sonnet-5-5", messages)
    assert result == 2.00 + 10.00


def test_compute_cost_sums_across_multiple_ai_messages() -> None:
    messages = [
        _FakeMessage({"input_tokens": 500_000, "output_tokens": 0}),
        _FakeMessage({"input_tokens": 500_000, "output_tokens": 1_000_000}),
    ]
    result = cost.compute_cost("claude-sonnet-5-5", messages)
    assert result == 2.00 + 10.00


def test_compute_cost_for_ollama_models_is_zero() -> None:
    messages = [_FakeMessage({"input_tokens": 1_000_000, "output_tokens": 1_000_000})]
    assert cost.compute_cost("ollama:llama3.2", messages) == 0.0
    assert cost.compute_cost("ollama:llama3.1:8b", messages) == 0.0


def test_compute_cost_for_unknown_model_defaults_to_zero() -> None:
    messages = [_FakeMessage({"input_tokens": 1_000_000, "output_tokens": 1_000_000})]
    assert cost.compute_cost("some-unlisted-model", messages) == 0.0
