#!/usr/bin/env python3
"""Deterministic agent-router evaluation; no network and no database writes."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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
    parser.add_argument("--input", default=str(ROOT / "tests" / "evals" / "agent_queries.jsonl"))
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts" / "evals"))
    args = parser.parse_args()
    cases = [json.loads(line) for line in Path(args.input).read_text().splitlines() if line.strip()]
    rows = []
    for case in cases:
        result = app.route_intent(case["query"])
        rows.append({"query": case["query"], "expected": case, "actual": result, "intent_ok": result["intent"] == case["expected_intent"], "tool_ok": result.get("tool_name") == case.get("expected_tool")})
    intent_accuracy = sum(row["intent_ok"] for row in rows) / len(rows) if rows else 0
    tool_accuracy = sum(row["tool_ok"] for row in rows if row["expected"].get("expected_tool")) / max(1, sum(bool(row["expected"].get("expected_tool")) for row in rows))
    clarification_precision = sum(row["actual"]["intent"] == "CLARIFY" and row["expected"]["expected_intent"] == "CLARIFY" for row in rows) / max(1, sum(row["actual"]["intent"] == "CLARIFY" for row in rows))
    metrics = {"cases": len(rows), "intent_accuracy": round(intent_accuracy, 4), "tool_accuracy": round(tool_accuracy, 4), "clarification_precision": round(clarification_precision, 4), "intent_distribution": dict(Counter(row["actual"]["intent"] for row in rows))}
    output_dir = Path(args.output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {"generated_at": stamp, "mode": "mocked-router", "metrics": metrics, "failures": [row for row in rows if not row["intent_ok"] or (row["expected"].get("expected_tool") and not row["tool_ok"])]}
    (output_dir / f"agent_eval_{stamp}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (output_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0 if not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
