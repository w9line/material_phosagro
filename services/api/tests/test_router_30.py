import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import app


EVAL_PATH = next(parent / "tests/evals/agent_queries_30.jsonl" for parent in Path(__file__).parents if (parent / "tests/evals/agent_queries_30.jsonl").exists())
CASES = [json.loads(line) for line in EVAL_PATH.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["query"][:32])
def test_router_30(case, monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "router.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///router.db")
    app.init_db()
    intent = app.route_intent(case["query"], case.get("history"))
    assert intent["intent"] == case["expected_intent"]
    assert intent.get("tool_name") == case.get("expected_tool")


def test_chart_router_and_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "chart.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///chart.db")
    app.init_db()
    intent = app.route_intent("Построй график концентрации по материалам")
    assert intent["tool_name"] == "build_chart"
    data = app.tool("build_chart", intent["arguments"])
    assert {"chart_type", "labels", "series", "meta"} <= set(data)
    assert data["chart_type"] == "concentration"


def test_material_quality_chart_groups_statuses_by_material(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "material-quality.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///material-quality.db")
    app.init_db()
    intent = app.route_intent("Сделай график по количеству каждого материала и его качеству")
    assert intent["tool_name"] == "build_chart"
    assert intent["arguments"]["chart_type"] == "material_quality"
    data = app.tool("build_chart", intent["arguments"])
    assert data["title"] == "Количество партий по материалам и качеству"
    assert data["labels"]
    assert {item["name"] for item in data["series"]} == {"GOOD", "REWORK", "REJECTED"}
    assert all(len(item["values"]) == len(data["labels"]) for item in data["series"])
