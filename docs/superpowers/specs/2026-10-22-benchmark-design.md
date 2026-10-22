# Design: Phase 3 — Custom benchmark (Claude vs. Ollama)

## Context

Phases 1 (DuckDB warehouse + MCP server) and 2 (LangGraph agent, FastAPI, CLI) are
complete, merged, and pushed. Phase 3 is the AI Engineering payoff: a custom benchmark
evaluating the agent on accuracy, tool use, cost, and latency, comparing an API-based
model (Claude) against two local models (Ollama), with Langfuse tracing.

Two real-world prerequisites for actually *running* the benchmark are not yet in
place, and are deliberately not blockers for designing or building it:

- **`ANTHROPIC_API_KEY`**: the Anthropic API is pay-per-token (confirmed: Claude
  Sonnet 5.5 is $2.00/$10.00 per 1M input/output tokens; Claude Haiku 5.5 is
  $0.10/$0.50), no free tier. For a benchmark of this size (45 runs), real cost is at
  most a few dollars — but it is still a deliberate, paid action the user takes when
  ready, not something this phase pays for itself.
- **A populated `warehouse.duckdb`**: no real backfill has been run in the main
  checkout yet (ENTSO-E's token is still pending per ADR 0001; éCO2mix alone could be
  backfilled without it).

Both gaps get the same treatment Phases 1 and 2 already established: build and test
everything now against mocks, and treat the real, paid/data-dependent run as an
explicitly documented, manually-triggered step.

A third, incidental finding from this session: `src/eaa/agent/graph.py`'s
`default_model()` hardcodes `claude-sonnet-4-5-20250929`, a stale model ID. This is
fixed as part of this phase (a real bug, independent of the benchmark itself), since
Phase 3 needs an accurate, current default to designate as the benchmark's "API model"
anyway.

## Decision

### Models compared

- **API-based**: Claude Sonnet 5.5 (`init_chat_model("anthropic:claude-sonnet-5-5")`)
  — the same model this fixes as the agent's own default, so the benchmark tests the
  agent "as normally used," not a separately-chosen model.
- **Local (small)**: `llama3.2` via Ollama (`init_chat_model("ollama:llama3.2")`) —
  already pulled locally (2 GB).
- **Local (large)**: `llama3.1:8b` via Ollama (`init_chat_model("ollama:llama3.1:8b")`)
  — already pulled locally (4.9 GB).

Both already-downloaded Llama 3.x models are reused rather than pulling new ones
(e.g. Qwen2.5) — zero extra download, and Llama 3.x handles tool calling adequately
via Ollama's native tool-call support. New dependency: `langchain-ollama` (needed for
`init_chat_model`'s `"ollama:"` provider prefix).

### Invocation: direct Python, not through `/ask`

The benchmark runner calls `build_agent(tools=..., model=<model under test>)` directly
in-process for each of the 45 (3 models × 15 questions) runs, rather than going through
Phase 2's FastAPI `/ask` endpoint. `/ask` builds one `AGENT` singleton at import time
with a fixed model — swapping models per request isn't something that API supports or
should be extended to support just for this. The benchmark does still need the MCP
server (Phase 1) running, since tools come from there; it does not need the FastAPI
app running at all.

### Dataset: 15 questions, 5 per category, as Python dataclasses

```python
@dataclass
class BenchmarkQuestion:
    id: str
    category: Literal["lookup", "aggregation", "multi_tool"]
    question: str
    ground_truth_sql: str  # run against the real warehouse to compute the expected value
    tolerance: float
    expected_tools: list[str]
```

Defined as a Python list (`src/eaa/benchmark/questions.py`), not an external JSON/YAML
file — no parser needed, directly type-checked, and consistent with how other fixed
project metadata already lives in code (e.g. `eco2mix.py`'s `SOURCE_FIELDS`). 5
questions each for: **lookup** (single-tool, simple `run_sql_query`/`get_schema` fact),
**aggregation/comparison** (single-tool, `GROUP BY`/`ORDER BY`-shaped), **multi-tool**
(combines a warehouse query with `get_latest_forecast`/`get_forecast_history`).

`ground_truth_sql` is a real query executed against the live warehouse at benchmark
run time — not a value hand-computed once and hardcoded — so the ground truth stays
correct even as the warehouse is re-backfilled later with more data.

### Scoring

**Accuracy** (`src/eaa/benchmark/scoring.py`): run `ground_truth_sql` against the
warehouse to get the expected number; extract the first number found in the agent's
final `answer` text via regex; compare within `tolerance`. A pure, directly-testable
function — no model or network dependency.

**Tool use**: recall-style, not exact-set — did the agent call every tool in
`expected_tools` at least once, using the `tool_calls` trace Phase 2's `/ask` response
already produces (the same extraction, `extract_tool_calls`, works directly on
`agent.invoke()`'s raw message list). An extra, unexpected tool call doesn't fail this
check — only a missing expected one does — since an exploratory extra call isn't
necessarily wrong, while a real tool-use mistake is specifically "didn't use the tool
that was needed."

**Cost** (`src/eaa/benchmark/cost.py`): sum each `AIMessage.usage_metadata`
(`input_tokens`/`output_tokens`) across the run's messages, multiply by a hardcoded
pricing table (Claude Sonnet 5.5's real published rates; Ollama models at a hardcoded
$0 per token, with the report noting that the real local "cost" is compute/hardware,
not a per-token price — reported honestly as $0 rather than estimated, since
estimating local compute cost in dollars isn't a need this benchmark has).

**Latency**: wall-clock time around each `agent.invoke()` call.

### Instrumentation: Langfuse

Official `langfuse` LangChain `CallbackHandler`, passed via
`config={"callbacks": [handler]}` on every `agent.invoke()` call, tagged with metadata
(model name, question id, category) so individual runs are filterable in the Langfuse
dashboard. Cloud-hosted, free tier — no self-hosted Docker service, consistent with
the reasoning already recorded for this decision during Phase 1's brainstorming (not
worth standing up infrastructure for a secondary observability need). New env vars:
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.

### Report

`src/eaa/benchmark/runner.py` executes all 45 runs; `cli.py` (`uv run eaa-benchmark`)
is the entry point. Raw results go to a local `benchmark_results.json` (gitignored,
like `warehouse.duckdb`/`agent_memory.sqlite` — reconstructible by re-running, not a
source artifact). A markdown summary table (accuracy %, tool-use %, avg cost, avg
latency — overall and broken down by category, per model) is both printed to stdout
and written to `docs/benchmark_report.md`, so a real run's output can be committed and
cited in the portfolio once the user has actually executed it.

### Testing

Same mocked-everything approach as Phases 1 and 2: `scoring.py`/`cost.py` are pure
functions tested directly with fixture data (no model, no warehouse, no network);
`runner.py` is tested with a mocked `build_agent`/`agent.invoke`, proving the
orchestration logic (iterating models × questions, calling scoring/cost, assembling
the report) without needing Claude, Ollama, or Langfuse credentials to run `pytest`.

## Alternatives considered

- **Forcing structured (JSON) agent output for easier answer extraction**: rejected —
  would require a benchmark-specific mode in the agent's own prompt/behavior, risking
  evaluating a different agent than the one actually used via the CLI/API. Regex
  extraction of the first number keeps the agent's normal behavior untouched.
- **Claude Haiku 5.5 as the "API" representative** (cheapest): rejected in favor of
  Sonnet 5.5 — the benchmark should test the agent as it's actually configured/used by
  default, not a separately-chosen cheap model picked only to make the cost comparison
  look more dramatic.
- **Downloading Qwen2.5 for more reliable tool-calling**: rejected for now — the two
  already-installed Llama 3.x models require no extra download and are adequate for
  this benchmark's scope; revisit only if their tool-calling proves unusably unreliable
  during the real run.
- **Running the benchmark through `/ask`**: rejected — `/ask`'s single `AGENT` global
  doesn't support swapping models per request, and extending it to do so isn't
  justified for a need only this benchmark has.

## Consequences

- `graph.py`'s `default_model()` changes from `claude-sonnet-4-5-20250929` to
  `claude-sonnet-5-5` — a real, independent bug fix landing as part of this phase's
  first task.
- Running the benchmark for real requires: `ANTHROPIC_API_KEY` set (paid, user's
  choice, ~a few dollars for 45 runs), a running `eaa-mcp-server`, a populated
  `warehouse.duckdb` (at least via éCO2mix backfill), Ollama running locally with
  `llama3.2`/`llama3.1:8b` pulled, and `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` set.
  None of this is required to build, test, or review this phase's code.
- `docs/benchmark_report.md` stays absent/stale until a real run happens — the README
  should note this the same way it notes the ENTSO-E and live-Claude-verification gaps.

## Out of scope for Phase 3

- A web UI for results (the markdown table + Langfuse dashboard are enough).
- A "trap"/out-of-scope-question category (already explicitly rejected in Phase 1's
  brainstorming).
- Automatic/CI-triggered benchmark runs — this stays a manual, deliberately-triggered
  command.
