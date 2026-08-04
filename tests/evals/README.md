# Agent evaluation set

`agent_queries.jsonl` is a deterministic routing set. It never calls VseLLM and never mutates the database. Each row contains `query`, `expected_intent` and, for tool cases, `expected_tool`.

Run it with:

```bash
make eval-agent-mocked
```

The live model evaluation is intentionally opt-in and is not part of the safe default test command.
