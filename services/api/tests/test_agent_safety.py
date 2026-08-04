import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import app
from fastapi import HTTPException
from starlette.requests import Request


def test_registry_drives_all_schemas():
    assert set(app.TOOLS) == set(app.TOOL_REGISTRY)
    specs = {item["function"]["name"]: item["function"] for item in app.tool_specs()}
    for name, registry in app.TOOL_REGISTRY.items():
        assert specs[name]["description"] == registry["description"]
        assert specs[name]["parameters"]["required"] == registry["required"]


def test_explanations_never_route_to_execution():
    cases = {
        "Как работает недельный план?": "build_weekly_plan",
        "Расскажи про остатки.": "get_inventory_summary",
        "Зачем нужен отчёт по браку?": "generate_rejection_report",
        "Какие параметры принимает сравнение стратегий?": "compare_allocation_policies",
        "Не запускай ничего, просто объясни FIFO.": "compare_allocation_policies",
    }
    for message, tool_name in cases.items():
        intent = app.route_intent(message)
        assert intent["intent"] == "EXPLAIN_TOOL"
        assert intent["tool_name"] == tool_name
        assert app.forced_tool_for_message(message) is None


def test_contextual_followups_keep_the_business_intent():
    inventory_history = [{"role": "user", "content": "Покажи остатки по A"}, {"role": "assistant", "content": "Сводка по остаткам"}]
    followup = app.route_intent("А теперь по B", inventory_history)
    assert followup["intent"] == "EXECUTE_TOOL"
    assert followup["tool_name"] == "get_inventory_summary"
    assert followup["arguments"]["material_type"] == "B"
    plan_history = [{"role": "user", "content": "Построй план A 3000 кг активного вещества B 2500 кг активного вещества C 1800 кг активного вещества hybrid"}]
    same_plan = app.route_intent("Сделай такой же, но FIFO", plan_history)
    assert same_plan["tool_name"] == "build_weekly_plan"
    assert same_plan["arguments"]["policy"] == "strict_fifo"
    changed = app.route_intent("Увеличь A на 20%", plan_history)
    assert changed["tool_name"] == "simulate_requirement_change"
    assert changed["arguments"]["changes_percent"] == {"A": 20.0}


def test_conversational_inventory_and_planning_phrases_are_understood():
    assert app.route_intent("че по сырью б")["tool_name"] == "get_inventory_summary"
    assert app.route_intent("сколько у нас вообще осталось ашки")["arguments"]["material_type"] == "A"
    assert app.route_intent("мы неделю вытянем по A 3000 кг активного вещества?")["tool_name"] == "check_material_deficit"
    assert app.route_intent("где больше всего потерь")["tool_name"] == "get_inventory_summary"
    assert app.route_intent("Сделай отчёт по отклонениям B")["tool_name"] == "generate_rejection_report"
    assert app.route_intent("Хватит ли B на потребность 2500 кг активного вещества")["tool_name"] == "check_material_deficit"
    assert app.route_intent("Что будет, если потребность C вырастет на 15% hybrid")["tool_name"] == "simulate_requirement_change"
    assert app.route_intent("Построй план A 1200 кг активного вещества B 900 кг активного вещества C 700 кг активного вещества max concentration")["arguments"]["policy"] == "max_concentration"


def test_final_answer_numbers_must_be_grounded():
    result = {"available_active_mass_kg": 2800.0, "deficit_active_mass_kg": 200.0}
    assert app.answer_numbers_are_grounded("Доступно 2800 кг, дефицит 200 кг.", result)
    assert not app.answer_numbers_are_grounded("Доступно 3000 кг, дефицита нет.", result)
    assert app.answer_numbers_are_grounded("Партия A-002: концентрация 30.1%.", {"concentration_percent": 30.1})
    assert app.answer_numbers_are_grounded("Итого 7012.7 кг.", {"available_active_mass_kg": 7012.718})


def test_obvious_requests_use_backend_router_before_llm(monkeypatch):
    monkeypatch.setattr(app, "tool", lambda name, args: {"groups": [], "meta": {"tool": name, "args": args}})
    routed = app.routed_tool_result("Покажи остатки по B", [])
    assert routed[0] == "get_inventory_summary"
    assert routed[2][0]["source"] == "router"


def test_llm_context_is_compact():
    history = [{"role": "user", "content": "x" * 2000}, {"role": "assistant", "content": "y" * 2000}]
    assert len(app.compact_history(history)[0]["content"]) == 700
    assert '"last_user_request"' in app.llm_context(history)


def test_plan_requires_explicit_inputs_and_policy():
    incomplete = app.route_intent("Построй недельный план")
    assert incomplete["intent"] == "CLARIFY"
    assert "requirements.A" in incomplete["missing_fields"]
    incomplete_units = app.route_intent("Построй план A 3000 B 2500 C 1800 hybrid")
    assert incomplete_units["intent"] == "CLARIFY"
    assert "mass_basis" in incomplete_units["missing_fields"]
    complete = app.route_intent("Построй план A 3 т B 2500 кг C 1800 кг активного вещества hybrid")
    assert complete["intent"] == "EXECUTE_TOOL"
    assert complete["arguments"]["requirements"] == {"A": 3000.0, "B": 2500.0, "C": 1800.0}
    assert app.parse_requirements("A 3 т B 2500 кг") == {"A": 3000.0, "B": 2500.0}


def test_domain_plan_invariants(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "audit.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///audit.db")
    app.init_db()
    con = app.db(); con.execute("DELETE FROM batches"); con.commit(); con.close()
    app.save_batches([
        {"batch_id": "A-GOOD", "material_type": "A", "raw_mass_kg": 100, "concentration_percent": 30, "arrival_date": "2026-01-01", "supplier": None, "warehouse": None, "certificate_number": None, "notes": None, "remaining_raw_mass_kg": 100, "source": "test"},
        {"batch_id": "A-REJECTED", "material_type": "A", "raw_mass_kg": 100, "concentration_percent": 10, "arrival_date": "2026-01-01", "supplier": None, "warehouse": None, "certificate_number": None, "notes": None, "remaining_raw_mass_kg": 100, "source": "test"},
    ])
    plan = app.build_plan({"A": 25}, "strict_fifo", True)
    item = plan["materials"]["A"]
    assert [row["batch_id"] for row in item["items"]] == ["A-GOOD"]
    assert item["covered_active_mass_kg"] + item["deficit_active_mass_kg"] == item["required_active_mass_kg"]
    assert all(row["batch_id"] != "A-REJECTED" for row in item["items"])
    assert plan["meta"]["units"]["active_mass"] == "kg_active"


def test_rejection_report_matches_derived_quality(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "report.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///report.db")
    app.init_db()
    con = app.db(); con.execute("DELETE FROM batches"); con.commit(); con.close()
    app.save_batches([
        {"batch_id": "A-GOOD", "material_type": "A", "raw_mass_kg": 100, "concentration_percent": 30, "arrival_date": "2026-01-01", "supplier": None, "warehouse": None, "certificate_number": None, "notes": None, "remaining_raw_mass_kg": 100, "source": "test"},
        {"batch_id": "A-REWORK", "material_type": "A", "raw_mass_kg": 100, "concentration_percent": 25, "arrival_date": "2026-01-02", "supplier": None, "warehouse": None, "certificate_number": None, "notes": None, "remaining_raw_mass_kg": 100, "source": "test"},
    ])
    report = app.tool("generate_rejection_report", {"material_type": "A", "include_rework": True, "include_rejected": True})
    assert {row["batch_id"] for row in report["batches"]} == {"A-REWORK"}
    assert report["meta"]["units"]["mass"] == "kg_raw"


def _auth_request(user_id: str, token: str) -> Request:
    return Request({"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())], "method": "POST", "path": "/"})


def test_preview_explains_selection_and_rejects_stale_confirmation(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "stale.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///stale.db")
    app.init_db()
    user_id = "audit-user"
    con = app.db(); con.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (user_id, "audit", app.hash_password("password"), 0, 0, "2026-08-05T00:00:00")); token = app.session_token(con, user_id); con.commit(); con.close()
    request = _auth_request(user_id, token)
    payload = app.RequirementIn(requirements={"A": 100}, policy="hybrid", allow_rework=True)
    first = app.plan_preview(payload, request)
    item = first["materials"]["A"]["items"][0]
    assert {"selection_rank", "selection_reason", "arrival_date", "concentration_percent", "active_mass_received_kg"} <= set(item)
    second = app.plan_preview(payload, request)
    assert app.plan_confirm(first["plan_id"], payload, request)["status"] == "confirmed"
    with pytest.raises(HTTPException) as error:
        app.plan_confirm(second["plan_id"], payload, request)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "STALE_PLAN"
