from __future__ import annotations

import csv
import io
import json
import random
import re
import uuid
import zipfile
from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="Raw Material Dataset Generator", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
GENERATED: dict[str, bytes] = {}
SCENARIOS = ["balanced", "deficit_a", "deficit_b", "deficit_c", "high_rework", "high_rejection", "fifo_conflict", "boundary_values", "invalid_rows", "large_dataset"]


class GenerateIn(BaseModel):
    scenario: str = "balanced"
    count: int = Field(100, ge=1, le=100000)
    seed: int = 42
    materials: list[str] = Field(default_factory=lambda: ["A", "B", "C"], min_length=1, max_length=30)

    @field_validator("materials")
    @classmethod
    def material_codes_ok(cls, value: list[str]) -> list[str]:
        codes = [code.strip().upper() for code in value]
        if len(set(codes)) != len(codes) or any(not re.fullmatch(r"[A-Z][A-Z0-9_-]{0,15}", code) for code in codes):
            raise ValueError("materials must contain unique codes like A, D or PHOS-1")
        return codes


def csv_bytes(headers: list[str], rows: list[dict]) -> bytes:
    out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=headers); writer.writeheader(); writer.writerows(rows); return out.getvalue().encode("utf-8-sig")


@app.get("/health")
def health(): return {"status": "ok"}


@app.get("/api/v1/scenarios")
def scenarios(): return {"scenarios": SCENARIOS}


@app.post("/api/v1/validate-config")
def validate_config(payload: GenerateIn): return {"valid": payload.scenario in SCENARIOS, "errors": [] if payload.scenario in SCENARIOS else ["unknown scenario"]}


@app.post("/api/v1/generate")
def generate(payload: GenerateIn):
    if payload.scenario not in SCENARIOS: return {"valid": False, "errors": ["unknown scenario"]}
    rng = random.Random(payload.seed); count = 10000 if payload.scenario == "large_dataset" else payload.count; start = date(2026, 1, 1); generation_id = str(uuid.uuid4()); materials = payload.materials
    rows = []
    for i in range(count):
        material = materials[i % len(materials)] if payload.scenario != "balanced" else rng.choice(materials)
        if payload.scenario in ("deficit_a", "deficit_b", "deficit_c") and material == payload.scenario.rsplit("_", 1)[-1].upper():
            if i % 2: continue
        status = rng.random()
        if payload.scenario == "high_rejection": concentration = rng.uniform(10, 22.9)
        elif payload.scenario == "high_rework": concentration = rng.uniform(23, 27.9)
        elif payload.scenario == "boundary_values": concentration = [22.99, 23.0, 27.99, 28.0][i % 4]
        elif payload.scenario == "fifo_conflict": concentration = rng.uniform(23, 26) if i < count / 2 else rng.uniform(29, 40)
        else: concentration = rng.uniform(20, 40)
        rows.append({"batch_id": f"{material}-{generation_id[:8]}-{i+1:04d}", "material_type": material, "raw_mass_kg": round(rng.uniform(500, 10000), 3), "concentration_percent": round(concentration, 3), "arrival_date": (start + timedelta(days=rng.randrange(220))).isoformat(), "supplier": f"Поставщик-{rng.randint(1, 5)}", "warehouse": f"Зона-{material}"})
    if payload.scenario == "invalid_rows" and rows:
        rows[0]["raw_mass_kg"] = -1; rows[1]["concentration_percent"] = 101; rows[2]["batch_id"] = rows[1]["batch_id"]
    thresholds = {"A": (28, 23), "B": (30, 25), "C": (35, 25)}
    rules = [{"material_type": m, "good_threshold_percent": thresholds.get(m, thresholds["A"])[0], "rework_threshold_percent": thresholds.get(m, thresholds["A"])[1], "good_recovery_factor": 1, "rework_recovery_factor": 0.9, "reject_recovery_factor": 0} for m in materials]
    req = [{"material_type": m, "required_active_mass_kg": 3000} for m in materials]
    manifest = {"seed": payload.seed, "scenario": payload.scenario, "materials": materials, "rows": len(rows), "synthetic": True, "generated_at": date.today().isoformat(), "warning": "Данные синтетические и не являются нормативами производства."}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("batches.csv", csv_bytes(list(rows[0]), rows) if rows else b"")
        z.writestr("quality_rules.csv", csv_bytes(list(rules[0]), rules)); z.writestr("weekly_requirements.csv", csv_bytes(list(req[0]), req)); z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    GENERATED[generation_id] = out.getvalue(); return {"generation_id": generation_id, "manifest": manifest, "download_url": f"/api/v1/download/{generation_id}"}


@app.get("/api/v1/download/{generation_id}")
def download(generation_id: str):
    data = GENERATED.get(generation_id)
    if not data: return {"error": "generation not found"}
    return StreamingResponse(iter([data]), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=generated_dataset.zip"})
