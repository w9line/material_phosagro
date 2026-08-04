import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import app


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
