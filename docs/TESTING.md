# Testing

```bash
make test
make eval-agent-mocked
```

`test` runs the API tests inside the Compose image. The mocked eval checks 200 deterministic natural-language requests and writes `artifacts/evals/latest.json`. Live LLM testing is opt-in because it spends provider quota and is timing-sensitive.
