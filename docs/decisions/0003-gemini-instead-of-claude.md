# ADR 0003: Gemini instead of Claude as the agent's and benchmark's cloud LLM

## Context
Phase 2's agent and Phase 3's benchmark were designed around Claude Sonnet 5.5 as
the cloud LLM, benchmarked against two local Ollama models. No working
`ANTHROPIC_API_KEY` was available to actually run either: the key configured in
this environment turned out to be in the wrong format for Anthropic's API
(confirmed empirically — `anthropic.AuthenticationError: invalid x-api-key`), and
obtaining a real one requires a paid top-up (typically a $5 minimum) on
console.anthropic.com, which was not something the project owner was willing to
spend at this point.

A free Google AI Studio API key (`GOOGLE_API_KEY`, for Gemini) was available
instead, confirmed working.

## Decision
Replace Claude with Gemini (`gemini-3.5-flash`, via `langchain-google-genai`) as
the cloud LLM everywhere Claude was previously hardcoded:
- `src/eaa/agent/graph.py`'s `default_model()` — Phase 2's production agent.
- `src/eaa/benchmark/cli.py`'s model dict — Phase 3's benchmark comparison arm.

Chosen over the alternative of keeping Claude and dropping the cloud-vs-local
comparison down to Ollama-vs-Ollama (see below), to preserve the benchmark's
original question — "does a paid cloud model's accuracy gain justify its cost
over free local models?" — rather than changing what's being measured.

## Alternatives considered
- **Pay for Anthropic credits and keep Claude.** Rejected per the project
  owner's explicit budget preference; revisit if the project needs Claude
  specifically for some other reason later (e.g. a feature only Claude supports).
- **Drop the cloud model entirely, compare Ollama models to each other.**
  Rejected: this is a weaker, less interesting story for the portfolio — "which
  local model is less bad" says less about engineering judgment than "is the
  accuracy gain of a cloud model worth its cost for this task," and the project
  owner is specifically building toward roles where that build-vs-buy tradeoff
  is a real skill to demonstrate.

## Consequences
- `pyproject.toml`: `langchain-anthropic` → `langchain-google-genai`.
- `.env`/`.env.example`: `ANTHROPIC_API_KEY` → `GOOGLE_API_KEY`.
- `src/eaa/benchmark/cost.py`'s pricing table now prices `gemini-3.5-flash` at
  its paid-tier rate (~$1.50/M input, $9.00/M output tokens — close to what
  Claude Sonnet cost), **not** the $0 the benchmark will actually pay on a
  free-tier key. This is deliberate: pricing it at $0 would collapse the cost
  axis to "$0 vs $0" next to Ollama, making it vacuous. The report should be
  read as "what the Gemini arm would cost at paid-tier rates," not as the
  benchmark's real spend.
- All tests and docs referencing `claude-sonnet-5-5` / `anthropic:...` were
  renamed to `gemini-3.5-flash` / `google_genai:...`.
- Closed, for free, a pre-existing Phase 2 gap: with a working key, the agent
  could finally be run end-to-end for the first time, which surfaced two real
  bugs the mocked test suite couldn't see (see
  [ADR 0004](0004-async-agent-invocation.md)).
