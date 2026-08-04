# Live VseLLM evaluation

The opt-in evaluation uses 41 difficult requests, including conversational follow-ups, ambiguous units, prompt injection, reports, plans and natural Russian phrasing. It runs through the real `llm_agent()` path and records whether a tool was selected by the model (`source=model`) or by the safety fallback.

Latest run on the deployed Compose image:

```text
cases: 41
tool_accuracy: 0.8485
model_tool_selection: 0.8485
answer_non_empty: 1.0
numeric_grounding: 1.0
avg_latency_seconds: 14.509
```

The 84.85% tool-selection result is the honest current model quality signal. The deterministic safety layer still prevents unauthorized execution; the live score shows where natural-language understanding needs more prompt/training work. Numeric grounding was 100% because ungrounded final answers fall back to the structured tool summary.

Run only when provider quota is available:

```bash
RUN_LIVE_LLM_EVAL=1 make eval-agent-live
```
