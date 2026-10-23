# ADR 0005: Fixes from the benchmark's first real (partial) run

## Context
With Phase 1's ENTSO-E token still pending, the warehouse was backfilled from
éCO2mix only (consumption + production mix; no day-ahead prices), and the
benchmark was run for the first time against real data, the real MCP server,
real Gemini, and real Ollama -- with `FORECAST_API_URL` deliberately pointed
at an unreachable host, since project 1's forecasting API wasn't running and
something else was squatting on its usual port. This first run surfaced three
problems the mocked test suite couldn't see:

1. **No resilience to provider rate limits.** `gemini-3.5-flash` on a
   free-tier key hit Google's 5 requests/minute quota partway through the
   15-question run. `run_one`/`run_benchmark` had no retry and no per-run
   error isolation, so the first `429 RESOURCE_EXHAUSTED` crashed the entire
   45-run benchmark (all three models), not just the Gemini arm.
2. **A ground-truth bug for "most recently recorded" questions.**
   `eco2mix.py`'s hourly resample fills a not-yet-reported ("gap") hour with
   NULL rather than omitting the row. `lookup-1/2/3`'s ground-truth SQL did
   `ORDER BY datetime DESC LIMIT 1` with no NULL filter, so it could pick up
   that placeholder row -- making the *ground truth itself* `NULL` while the
   agent's "data wasn't available" answer was actually correct.
3. **A scoring bug in numeric extraction.** `extract_first_number` took the
   first number-looking substring in the agent's answer text. A small local
   model restating part of the question before answering ("Over the most
   recent 7 days, the average was...") caused the scorer to extract the "7"
   instead of the real answer, producing false negatives independent of
   whether the agent was actually right.

After fixing all three, accuracy was still 0% across all three models --
but for two distinct, now-diagnosed reasons, not because the fixes didn't
work:

- **Gemini**: still quota-exhausted (185s average latency, 0% tool-use) --
  the free tier's 5 req/min is too tight for even one model's 15-question
  run with retries, so most "answers" are actually
  `ModelRetryMiddleware`'s own failure message, not a real attempt.
- **Ollama (`llama3.2`, `llama3.1:8b`)**: a genuine capability gap, confirmed
  by replaying a single question outside the benchmark. The model calls
  `run_sql_query` directly with a guessed schema (e.g. `SELECT value FROM
  consumption_hourly ORDER BY timestamp DESC LIMIT 1`) instead of calling
  `get_schema` first, the query fails with a DuckDB binder error, and the
  model then does exactly what its system prompt asks: reports the data as
  unavailable rather than inventing a number. Tool use is high (60-100%, it
  does call `run_sql_query`) but accuracy stays 0%.

## Decision
- `src/eaa/benchmark/runner.py`: give each benchmark agent a
  `langchain.agents.middleware.ModelRetryMiddleware` (reused, not
  hand-rolled -- it already does exponential backoff + jitter and classifies
  provider errors via `langchain_core.exceptions.ModelError.is_retryable`,
  which covers `GoogleRateLimitError` generically rather than hardcoding a
  Gemini-specific exception type). Wrap `run_one`'s body in a `try/except`
  that turns any exception surviving the middleware into a failed
  `RunResult` (new `error: str | None` field) instead of raising, so one bad
  (model, question) pair can't abort the rest of the run.
- `src/eaa/benchmark/questions.py`: `lookup-1/2/3/4`'s ground-truth SQL now
  filters `IS NOT NULL` before `ORDER BY datetime DESC LIMIT 1`.
- `src/eaa/benchmark/scoring.py`: renamed `extract_first_number` to
  `extract_last_number` and changed it to return the *last* number-looking
  match, not the first.
- `src/eaa/benchmark/report.py`: `render_markdown` now always appends an
  "Interpreting this report" section explaining that a 0%/low accuracy row
  can mean either "never really tested" (provider error) or "genuinely
  failed" (real capability gap), and pointing readers at the per-run `error`
  field and tool-call trace in `benchmark_results.json` rather than reading
  a bare percentage as a capability score.

## Alternatives considered
- **Throttle Gemini calls with a fixed `time.sleep` between questions**,
  instead of retry middleware. Rejected: `ModelRetryMiddleware` already
  solves this generically (any `ModelError` with `is_retryable=True`, any
  provider) with backoff and jitter; a hand-rolled sleep would be
  provider-specific and reinvent something the framework already does well.
- **Add `get_schema` to `lookup`/`aggregation` questions'
  `expected_tools`, or add schema info to the system prompt, to make Ollama
  "pass."** Rejected for this ADR's fixes: that would change what the
  benchmark measures (whether a model explores before querying) rather than
  fix a bug in how it's measured. Worth considering as a deliberate,
  separate design change later if the goal shifts to "can a nudged small
  model match Gemini," but not folded in silently here.

## Consequences
- The benchmark can no longer be taken down by a single rate-limited call;
  partial results (and per-run error detail) survive even when one arm is
  badly throttled.
- `docs/benchmark_report.md`/`benchmark_results.json` reflect this first
  partial run: éCO2mix-only data (no day-ahead prices -- `lookup-4` and
  `aggregation-3` fail cleanly on the still-missing ENTSO-E table), and
  `FORECAST_API_URL` pointed at an unreachable host (all 5 `multi_tool`
  questions fail cleanly, 0% tool-use, since project 1's forecasting API
  wasn't running this round either). Neither is a benchmark bug; both are
  tracked pre-existing gaps (ADR 0001; project 1's API).
- The real, interesting finding from this first run is Ollama's schema-guessing
  behavior, not a number: it is evidence for the exact build-vs-buy question
  this benchmark exists to ask (see ADR 0003), even though no model currently
  "wins" on accuracy in this partial run.
- A full, fair accuracy comparison still needs: the ENTSO-E token (price
  questions), project 1's forecasting API actually running (multi-tool
  questions), and either a paid Gemini key or spacing the Gemini arm's calls
  across more than 3 minutes to clear free-tier quota windows.
