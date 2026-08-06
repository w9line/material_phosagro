import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import app


@pytest.fixture
def demo_db(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "scenarios.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///scenarios.db")
    app.init_db()


@pytest.mark.parametrize(
    ("query", "tool"),
    [
        ("Покажи остатки по A", "get_inventory_summary"),
        ("Какие самые старые партии?", "get_oldest_batches"),
        ("Проверь качество партии A-001", "check_batch_quality"),
        ("Покажи детали партии A-001", "get_batch_details"),
        ("Построй график остатков", "build_chart"),
        ("Сделай график по количеству каждого материала и его качеству", "build_chart"),
        ("Классифицируй все партии", "classify_batches"),
        ("Сформируй отчёт по браку A", "generate_rejection_report"),
        ("Построй недельный план A 3000 кг активного вещества B 2500 кг активного вещества C 1800 кг активного вещества hybrid", "build_weekly_plan"),
        ("Проверь дефицит A 3000 кг активного вещества", "check_material_deficit"),
        ("Сравни стратегии FIFO и hybrid для A 3000 кг активного вещества", "compare_allocation_policies"),
        ("Смоделируй сценарий A на 20% hybrid", "simulate_requirement_change"),
    ],
)
def test_each_tool_has_a_happy_path(demo_db, query, tool):
    intent = app.route_intent(query)
    assert intent["intent"] == "EXECUTE_TOOL"
    assert intent["tool_name"] == tool


@pytest.mark.parametrize(
    ("query", "tool", "field"),
    [
        ("Покажи остатки", "get_inventory_summary", "material_type"),
        ("Проверь статус партии", "check_batch_quality", "batch_id"),
        ("Построй недельный план", "build_weekly_plan", "requirements.A"),
        ("Проверь дефицит материалов", "check_material_deficit", "requirements"),
        ("Сравни стратегии", "compare_allocation_policies", "requirements"),
        ("Смоделируй сценарий", "simulate_requirement_change", "changes_percent"),
    ],
)
def test_missing_inputs_never_execute(demo_db, query, tool, field):
    intent = app.route_intent(query)
    assert intent["intent"] == "CLARIFY"
    assert intent["tool_name"] == tool
    assert field in intent["missing_fields"]


@pytest.mark.parametrize("query", [
    "Как работает инструмент остатков?",
    "Объясни недельный план, ничего не запускай",
    "Расскажи про классификацию",
    "Зачем нужен отчёт по браку?",
    "Какие параметры принимает сценарий?",
])
def test_explanation_requests_are_read_only(demo_db, query):
    intent = app.route_intent(query)
    assert intent["intent"] == "EXPLAIN_TOOL"
    assert app.forced_tool_for_message(query) is None


def test_material_quality_chart_contract(demo_db):
    data = app.tool("build_chart", {"chart_type": "material_quality", "material_type": None})
    assert data["chart_type"] == "material_quality"
    assert data["title"] == "Количество партий по материалам и качеству"
    assert [series["name"] for series in data["series"]] == ["GOOD", "REWORK", "REJECTED"]
    assert all(len(series["values"]) == len(data["labels"]) for series in data["series"])


@pytest.mark.parametrize(
    ("query", "expected_tools"),
    [
        ("Покажи остатки и построй график", ["get_inventory_summary", "build_chart"]),
        ("Создай отчёт по браку по всем материалам и построй график брака", ["generate_rejection_report", "build_chart"]),
        ("Классифицируй партии A и сделай отчёт по браку A", ["classify_batches", "generate_rejection_report"]),
        ("Проверь качество партии A-001 и покажи её детали", ["check_batch_quality", "get_batch_details"]),
        ("Построй план A 3000 кг активного вещества B 2500 кг активного вещества C 1800 кг активного вещества hybrid и проверь дефицит", ["build_weekly_plan", "check_material_deficit"]),
        ("Построй план A 3000 кг активного вещества B 2500 кг активного вещества C 1800 кг активного вещества hybrid и сравни стратегии", ["build_weekly_plan", "compare_allocation_policies"]),
    ],
)
def test_composed_workflows_execute_in_declared_order(demo_db, monkeypatch, query, expected_tools):
    calls = []

    def fake_tool(name, args):
        calls.append(name)
        return {"tool": name, "args": args, "batches": [], "groups": [], "materials": {}, "chart_type": "inventory"} if name == "build_chart" else {"tool": name}

    monkeypatch.setattr(app, "tool", fake_tool)
    routed = app.routed_tool_result(query, [])
    assert routed is not None
    assert calls == expected_tools
    assert [item["tool"] for item in routed[2]] == expected_tools


def test_context_followups_cover_material_policy_and_change(demo_db):
    inventory_history = [{"role": "user", "content": "Покажи остатки по A"}]
    assert app.route_intent("А теперь по B", inventory_history)["arguments"]["material_type"] == "B"
    plan_history = [{"role": "user", "content": "Построй план A 3000 кг активного вещества B 2500 кг активного вещества C 1800 кг активного вещества hybrid"}]
    assert app.route_intent("Сделай такой же, но FIFO", plan_history)["tool_name"] == "build_weekly_plan"
    changed = app.route_intent("Увеличь A на 20%", plan_history)
    assert changed["tool_name"] == "simulate_requirement_change"
    assert changed["arguments"]["changes_percent"] == {"A": 20.0}
