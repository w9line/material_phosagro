import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import app


def test_quality_boundaries():
    assert app.classify({"material_type": "A", "concentration_percent": 28})["status"] == "GOOD"
    assert app.classify({"material_type": "A", "concentration_percent": 27.99})["status"] == "REWORK"
    assert app.classify({"material_type": "A", "concentration_percent": 23})["status"] == "REWORK"
    assert app.classify({"material_type": "A", "concentration_percent": 22.99})["status"] == "REJECTED"


def test_partial_plan_never_uses_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(app, "DATABASE_URL", "sqlite:///test.db")
    app.init_db()
    app.save_batches([
        {"batch_id": "A-OLD", "material_type": "A", "raw_mass_kg": 100, "concentration_percent": 22, "arrival_date": "2026-01-01", "supplier": None, "warehouse": None, "certificate_number": None, "notes": None, "remaining_raw_mass_kg": 100, "source": "test"},
        {"batch_id": "A-GOOD", "material_type": "A", "raw_mass_kg": 100, "concentration_percent": 30, "arrival_date": "2026-01-02", "supplier": None, "warehouse": None, "certificate_number": None, "notes": None, "remaining_raw_mass_kg": 100, "source": "test"},
    ])
    plan = app.build_plan({"A": 20}, "strict_fifo", True)
    assert [x["batch_id"] for x in plan["materials"]["A"]["items"]] == ["A-GOOD"]
    assert plan["materials"]["A"]["covered_active_mass_kg"] == 20
