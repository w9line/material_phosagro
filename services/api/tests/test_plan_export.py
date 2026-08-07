import asyncio
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import app


async def read_body(iterator):
    return b"".join([chunk async for chunk in iterator])


def test_production_plan_export_contains_selection_and_deficit(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "export.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///export.db")
    app.init_db()
    con = app.db(); con.execute("DELETE FROM batches"); con.commit(); con.close()
    app.save_batches([{"batch_id": "A-GOOD", "material_type": "A", "raw_mass_kg": 100, "concentration_percent": 30, "arrival_date": "2026-01-01", "remaining_raw_mass_kg": 100, "source": "test"}])
    monkeypatch.setattr(app, "current_user", lambda request: {})
    response = app.production_plan_download(app.RequirementIn(requirements={"A": 40}), app.Request({"type": "http", "headers": []}))
    rows = list(csv.DictReader(io.StringIO(asyncio.run(read_body(response.body_iterator)).decode("utf-8-sig"))))
    assert rows[0]["plan_type"] == "production_weekly"
    assert rows[0]["policy"] == "hybrid"
    assert rows[0]["batch_id"] == "A-GOOD"
    assert rows[0]["deficit_active_mass_kg"] == "10.0"
    assert {"material_type", "selection_rank", "raw_mass_used_kg", "active_mass_kg", "deficit_active_mass_kg"} <= set(rows[0])
