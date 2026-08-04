#!/usr/bin/env python3
"""Small opt-in VseLLM evaluation for difficult agent conversations."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "services" / "api"
if not API_DIR.exists():
    ROOT = Path("/app")
    API_DIR = ROOT
sys.path.insert(0, str(API_DIR))
import app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "tests" / "evals" / "live_queries.jsonl"))
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts" / "evals"))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not os.getenv("LLM_API_KEY"):
        print("LLM_API_KEY is required for live eval", file=sys.stderr)
        return 2
    cases = [json.loads(line) for line in Path(args.input).read_text().splitlines() if line.strip()]
    def evaluate(case: dict[str, object]) -> dict[str, object]:
        started = time.monotonic()
        try:
            result = app.llm_agent(case["query"], case.get("history", []))
            if result is None:
                raise RuntimeError("LLM agent returned no result")
            name, answer, data, trace = result
            expected_tool = case.get("expected_tool")
            actual_tools = [item.get("tool") for item in trace]
            model_tools = [item.get("tool") for item in trace if item.get("source") == "model"]
            return {"query": case["query"], "expected_tool": expected_tool, "actual_tools": actual_tools, "model_tools": model_tools, "answer": answer, "grounded": app.answer_numbers_are_grounded(answer, data), "non_empty": bool((answer or "").strip()), "tool_ok": expected_tool is None or expected_tool in actual_tools, "model_tool_ok": expected_tool is None or expected_tool in model_tools, "elapsed_seconds": round(time.monotonic() - started, 3)}
        except Exception as exc:
            return {"query": case["query"], "expected_tool": case.get("expected_tool"), "error": str(exc), "grounded": False, "non_empty": False, "tool_ok": False, "model_tool_ok": False, "elapsed_seconds": round(time.monotonic() - started, 3)}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        rows = list(executor.map(evaluate, cases))
    expected = [row for row in rows if row.get("expected_tool")]
    metrics = {"cases": len(rows), "tool_accuracy": round(sum(row["tool_ok"] for row in expected) / max(1, len(expected)), 4), "model_tool_selection": round(sum(row["model_tool_ok"] for row in expected) / max(1, len(expected)), 4), "answer_non_empty": round(sum(row["non_empty"] for row in rows) / max(1, len(rows)), 4), "numeric_grounding": round(sum(row["grounded"] for row in rows) / max(1, len(rows)), 4), "avg_latency_seconds": round(sum(row["elapsed_seconds"] for row in rows) / max(1, len(rows)), 3)}
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "mode": "live-vsellm", "metrics": metrics, "rows": rows}
    output_dir = Path(args.output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "live_latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if metrics["numeric_grounding"] == 1.0 and metrics["answer_non_empty"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
