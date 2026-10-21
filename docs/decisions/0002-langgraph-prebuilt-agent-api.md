# ADR 0002: `create_agent` instead of `create_react_agent` for the LangGraph agent

## Context
The Phase 2 plan assumed `langgraph.prebuilt.create_react_agent(model, tools,
prompt=SYSTEM_PROMPT, checkpointer=...)` for `src/eaa/agent/graph.py`. Against the
installed `langgraph==1.2.16` / `langchain==1.4.6`, that function still exists and
accepts `prompt=` exactly as assumed, but it is deprecated as of LangGraph v1.0
(`LangGraphDeprecatedSinceV10`, logged on every call) in favor of
`langchain.agents.create_agent`, scheduled for removal in v2.0.

While verifying this, direct inspection of
`langgraph/prebuilt/chat_agent_executor.py` surfaced a second, non-obvious fact
that holds for *both* functions: the injected system prompt (`prompt=` on the old
function, `system_prompt=` on the new one) is applied only to the message list
sent to the model for a given turn, via a `RunnableSequence(prompt_runnable |
model)`. The agent node's actual state update is `{"messages": [response]}` —
the system message is never merged into the graph's persisted `messages` state.
Confirmed empirically: a `GenericFakeChatModel` plus a `BaseCallbackHandler` on
`on_chat_model_start` shows the system message reaching the model, but
`result["messages"]` from `.invoke()` never contains a message with
`type == "system"`.

## Decision
Use `langchain.agents.create_agent` with `system_prompt=` instead of
`langgraph.prebuilt.create_react_agent` with `prompt=`. Behavior is otherwise
identical (same `tools`/`model`/`checkpointer` wiring, same compiled-graph
`.invoke()` interface), and it emits no deprecation warning.

## Alternatives considered
- **Stay on `create_react_agent`.** Works today and matches the plan's snippet
  verbatim, but defers a forced migration (removal in LangGraph v2.0) to a less
  convenient time, for no benefit — `create_agent` is a drop-in rename plus one
  parameter rename (`prompt` → `system_prompt`).
- **Force the system message into persisted state via a `pre_model_hook`**
  that returns `{"messages": [system_message_with_fixed_id]}`. Rejected: traced
  through `langgraph.graph.message.add_messages`'s append-only, id-keyed merge
  semantics and confirmed the system message would land *after* the first human
  message on turn one (new messages are appended, not prepended), not before it.
  `langchain_anthropic._format_messages` detects a non-leading `SystemMessage`
  and hoists it into the top-level `system` field with a runtime warning on every
  real call. Functionally correct but noisy and non-idiomatic for the Claude
  model this agent will actually run against from Task 5 onward.

## Consequences
- `src/eaa/agent/graph.py` imports `create_agent` from `langchain.agents`, not
  `create_react_agent` from `langgraph.prebuilt`.
- `tests/agent/test_graph.py::test_build_agent_uses_the_system_prompt` verifies
  system-prompt injection by registering a `BaseCallbackHandler` and asserting
  on the messages passed to `on_chat_model_start`, **not** by inspecting
  `result["messages"]` — the latter will never contain the system prompt with
  this LangGraph version, for any prebuilt agent construction. Any future test
  (Tasks 5+) that wants to assert "the model saw X" must use this same
  callback-based pattern rather than reading persisted graph state.
- This also matters for Phase 3's evaluation code, if it inspects agent message
  history to check what instructions were in play for a given run: the system
  prompt will not show up there. It must be read from the agent's static
  configuration (`SYSTEM_PROMPT` in `graph.py`) instead, or captured via the same
  callback mechanism at run time.
