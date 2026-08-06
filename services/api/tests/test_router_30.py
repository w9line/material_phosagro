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


@pytest.mark.parametrize("query, metric, group_by", [
    ("Построй график сырья по материалам", "raw_mass", "material"),
    ("Построй график активного вещества по партиям", "active_mass", "batch"),
    ("Построй график теоретического активного вещества", "theoretical_active_mass", "material"),
    ("Построй график потерь восстановления", "recovery_loss", "material"),
    ("Построй график возраста партий", "age_days", "material"),
    ("Построй график доли партий по качеству", "status_share", "material"),
    ("Построй график количества партий по статусам", "status_count", "status"),
    ("Построй график массы брака", "rejection_raw_mass", "material"),
    ("Построй график активного вещества в браке", "rejection_active_mass", "material"),
])
def test_chart_router_covers_registry_metrics(monkeypatch, tmp_path, query, metric, group_by):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "universal-chart.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///universal-chart.db")
    app.init_db()
    intent = app.route_intent(query)
    assert intent["tool_name"] == "build_chart"
    assert intent["arguments"]["metric"] == metric
    assert intent["arguments"]["group_by"] == group_by
    data = app.tool("build_chart", intent["arguments"])
    assert data["labels"]
    assert all(len(series["values"]) == len(data["labels"]) for series in data["series"])


def test_plan_and_scenario_chart_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "plan-chart.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///plan-chart.db")
    app.init_db()
    requirements = {"A": 1000, "B": 1000}
    for metric in ("required_active_mass", "plan_available_active_mass", "planned_batch_count", "covered_active_mass", "deficit_active_mass", "coverage_percent", "raw_mass_used", "loss"):
        data = app.tool("build_chart", {"chart_type": "metric", "metric": metric, "group_by": "material", "requirements": requirements, "policy": "hybrid"})
        assert data["labels"]
    for metric in ("safe_growth_percent", "deficit_delta", "base_deficit_active_mass", "new_deficit_active_mass", "base_rework_batch_count", "new_rework_batch_count"):
        data = app.tool("build_chart", {"chart_type": "metric", "metric": metric, "group_by": "material", "requirements": requirements, "changes_percent": {"A": 20}, "policy": "hybrid"})
        assert data["labels"]
