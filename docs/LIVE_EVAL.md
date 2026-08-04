# Live VseLLM evaluation

The opt-in evaluation uses 41 difficult requests, including conversational follow-ups, ambiguous units, prompt injection, reports, plans and natural Russian phrasing. It runs through the real `llm_agent()` path and records router/model selection, execution, grounding and latency percentiles.

Latest run on the deployed Compose image:

```text
cases: 41
tool_accuracy: 0.9697
route_accuracy: 1.0
model_tool_selection: null
model_selection_cases: 0
clarification_cases: 1
unexpected_tool_count: 0
answer_non_empty: 1.0
numeric_grounding: 1.0
avg_latency_seconds: 5.209
p50_latency_seconds: 5.501
p95_latency_seconds: 7.642
max_latency_seconds: 8.625
```

The router handles explicit and context-complete requests before VseLLM; the model remains the fallback for ambiguous natural language. The execution score is 96.97% because one case intentionally returns a clarification instead of executing without a material. The deterministic safety layer prevents unauthorized execution; numeric grounding is enforced after the model response and was 100% in this run.

The fast path also sends a compact conversation window and a structured last-request state. The model receives no tool schemas for already-routed requests, so it only explains the verified result instead of spending a round choosing a tool.

Run only when provider quota is available:

```bash
RUN_LIVE_LLM_EVAL=1 make eval-agent-live
```
