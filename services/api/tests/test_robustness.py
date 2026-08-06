import asyncio
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import app


def test_1000_extreme_rows_and_report_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "robust.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///robust.db")
    app.init_db()
    con = app.db(); con.execute("DELETE FROM batches"); con.commit(); con.close()
    materials = ["A", "B", "C", "D", "E", "PHOS", "K", "ZN", "MN", "X1"]
    concentrations = [0.0, 22.99, 23.0, 28.0, 100.0]
    rows = [{"batch_id": f"{materials[i % len(materials)]}-R-{i:04d}", "material_type": materials[i % len(materials)], "raw_mass_kg": 0.001 if i % 5 == 0 else 1000.0, "concentration_percent": concentrations[i % len(concentrations)], "arrival_date": f"2026-01-{i % 28 + 1:02d}", "remaining_raw_mass_kg": 0.001 if i % 5 == 0 else 1000.0, "source": "robustness"} for i in range(1000)]
    valid, errors = app.validate_rows(rows)
    assert len(valid) == 1000 and not errors
    assert app.save_batches(valid) == 1000

    classified = app.tool("classify_batches", {"material_type": None, "only_unclassified": False})
    assert classified["checked"] == 1000
    assert classified["GOOD"] + classified["REWORK"] + classified["REJECTED"] == 1000
    inventory = app.tool("get_inventory_summary", {"material_type": None, "group_by": "material_and_status"})
    assert sum(item["batch_count"] for item in inventory["groups"]) == 1000
    chart = app.tool("build_chart", {"chart_type": "inventory", "material_type": None})
    assert set(chart["labels"]) == set(materials)
    assert all(value >= 0 for series in chart["series"] for value in series["values"])
    plan = app.build_plan({material: 1.0 for material in materials}, "strict_fifo", True)
    assert all(item["status"] != "REJECTED" for material in plan["materials"].values() for item in material["items"])

    report = app.tool("generate_rejection_report", {"material_type": None, "include_rework": True, "include_rejected": True})
    assert report["batches"]
    assert all({"batch_id", "material_type", "concentration_percent", "remaining_raw_mass_kg", "quality"} <= set(row) for row in report["batches"])
    monkeypatch.setattr(app, "current_user", lambda request: {})
    response = app.report_download("robustness", app.Request({"type": "http", "headers": []}))
    body = asyncio.run(_read_stream(response.body_iterator))
    header = next(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
    assert header == ["batch_id", "material_type", "concentration_percent", "status", "remaining_raw_mass_kg"]

    invalid, invalid_errors = app.validate_rows([{**rows[0], "batch_id": "ZERO", "raw_mass_kg": 0, "remaining_raw_mass_kg": 0}])
    assert not invalid and invalid_errors


async def _read_stream(iterator):
    return b"".join([chunk async for chunk in iterator])
