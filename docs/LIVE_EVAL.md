# Live VseLLM evaluation

The opt-in evaluation uses 41 difficult requests, including conversational follow-ups, ambiguous units, prompt injection, reports, plans and natural Russian phrasing. It runs through the real `llm_agent()` path and records router/model selection, execution, grounding and latency percentiles.

Latest run on the deployed Compose image:

```text
cases: 42
tool_accuracy: 0.9706
route_accuracy: 1.0
model_tool_selection: 1.0
model_selection_cases: 1
clarification_cases: 1
unexpected_tool_count: 0
answer_non_empty: 1.0
numeric_grounding: 1.0
avg_latency_seconds: 6.204
p50_latency_seconds: 6.121
p95_latency_seconds: 8.958
max_latency_seconds: 20.678
```

Classification metrics over 10 classes (`9 tools + NO_TOOL`):

```text
final macro_f1: 0.9798
final micro_f1: 0.9762
router macro_f1: 0.9125
router micro_f1: 0.8810
```

The final F1 uses the actual executed tool, so it measures user-visible behavior. The lower raw-router F1 includes requests that should be explanations or clarifications; the safety guard correctly prevents those suggested tool calls from executing. Per-class final F1 is 1.0 for every tool except `generate_rejection_report` (0.8571); `NO_TOOL` is 0.9412.

The router handles explicit and context-complete requests before VseLLM; the model remains the fallback for ambiguous natural language. The execution score is 97.06% because one case intentionally returns a clarification instead of executing without a material. The deterministic safety layer prevents unauthorized execution; numeric grounding is enforced after the model response and was 100% in this run.

The fast path also sends a compact conversation window and a structured last-request state. The model receives no tool schemas for already-routed requests, so it only explains the verified result instead of spending a round choosing a tool.

Run only when provider quota is available:

```bash
RUN_LIVE_LLM_EVAL=1 make eval-agent-live
```
