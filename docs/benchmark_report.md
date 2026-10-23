| Model | Accuracy | Tool use | Avg cost (USD) | Avg latency (s) | N |
|---|---|---|---|---|---|
| gemini-3.5-flash | 0.0% | 0.0% | $0.0001 | 185.05 | 15 |
| ollama:llama3.1:8b | 0.0% | 60.0% | $0.0000 | 2.10 | 15 |
| ollama:llama3.2 | 0.0% | 60.0% | $0.0000 | 1.07 | 15 |

### By category

| Model | Category | Accuracy | Tool use | N |
|---|---|---|---|---|
| gemini-3.5-flash | aggregation | 0.0% | 0.0% | 5 |
| gemini-3.5-flash | lookup | 0.0% | 0.0% | 5 |
| gemini-3.5-flash | multi_tool | 0.0% | 0.0% | 5 |
| ollama:llama3.1:8b | aggregation | 0.0% | 100.0% | 5 |
| ollama:llama3.1:8b | lookup | 0.0% | 80.0% | 5 |
| ollama:llama3.1:8b | multi_tool | 0.0% | 0.0% | 5 |
| ollama:llama3.2 | aggregation | 0.0% | 100.0% | 5 |
| ollama:llama3.2 | lookup | 0.0% | 80.0% | 5 |
| ollama:llama3.2 | multi_tool | 0.0% | 0.0% | 5 |

### Interpreting this report

A low or 0% accuracy row does not by itself mean the model failed the task. Two very different situations both show up as "incorrect" here and this table cannot tell them apart:
- **The model was never really tested** -- e.g. a cloud provider's rate limit was hit repeatedly enough to exhaust retries, so the "answer" is actually an error message, not a real attempt.
- **The model genuinely failed the task** -- e.g. it guessed at a table/column name instead of calling `get_schema` first, got a SQL error back, and (correctly, per its instructions) reported the data as unavailable rather than inventing a number.
Before reading a percentage as a capability score, check the `error` field and the tool-call trace for the relevant rows in `benchmark_results.json` (one JSON object per question/model run).