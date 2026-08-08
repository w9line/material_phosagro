from __future__ import annotations

from typing import Any

POLICIES = ("strict_fifo", "max_concentration", "hybrid")

TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "check_batch_quality": {"description": "Проверяет качество одной партии.", "parameters": {"batch_id": {"type": "string"}}, "required": ["batch_id"]},
    "get_batch_details": {"description": "Возвращает детали одной партии.", "parameters": {"batch_id": {"type": "string"}}, "required": ["batch_id"]},
    "get_oldest_batches": {"description": "Показывает самые ранние партии.", "parameters": {"material_type": {"type": ["string", "null"]}, "limit": {"type": "integer"}}, "required": []},
    "build_chart": {"description": "Строит график доступной измеримой метрики.", "parameters": {"chart_type": {"type": "string"}, "metric": {"type": ["string", "null"]}, "group_by": {"type": ["string", "null"]}, "material_type": {"type": ["string", "null"]}, "requirements": {"type": ["object", "null"]}, "policy": {"type": ["string", "null"]}}, "required": []},
    "classify_batches": {"description": "Классифицирует партии по quality rules.", "parameters": {"material_type": {"type": ["string", "null"]}, "only_unclassified": {"type": "boolean"}}, "required": []},
    "get_inventory_summary": {"description": "Показывает остатки и доступное активное вещество.", "parameters": {"material_type": {"type": ["string", "null"]}, "group_by": {"type": "string"}}, "required": []},
    "build_weekly_plan": {"description": "Строит preview недельного плана без списания.", "parameters": {"requirements": {"type": "object"}, "policy": {"type": "string", "enum": list(POLICIES)}, "allow_rework": {"type": "boolean"}}, "required": ["requirements", "policy"]},
    "check_material_deficit": {"description": "Сравнивает потребность с доступным активным веществом.", "parameters": {"requirements": {"type": "object"}, "include_rework": {"type": "boolean"}}, "required": ["requirements"]},
    "compare_allocation_policies": {"description": "Сравнивает политики распределения сырья.", "parameters": {"requirements": {"type": "object"}, "policies": {"type": "array"}}, "required": ["requirements", "policies"]},
    "generate_rejection_report": {"description": "Формирует отчёт по REWORK и REJECTED.", "parameters": {"material_type": {"type": ["string", "null"]}, "include_rework": {"type": "boolean"}, "include_rejected": {"type": "boolean"}}, "required": []},
    "simulate_requirement_change": {"description": "Сравнивает базовую и изменённую потребность.", "parameters": {"base_requirements": {"type": "object"}, "changes_percent": {"type": "object"}, "policy": {"type": "string", "enum": list(POLICIES)}}, "required": ["changes_percent", "policy"]},
}


def tool_specs() -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": name, "description": spec["description"], "parameters": {"type": "object", "properties": spec["parameters"], "required": spec["required"], "additionalProperties": False}}} for name, spec in TOOL_REGISTRY.items()]


def validate_tool_call(name: str, arguments: Any) -> dict[str, Any]:
    if name not in TOOL_REGISTRY or not isinstance(arguments, dict):
        raise ValueError("unknown or malformed tool call")
    spec = TOOL_REGISTRY[name]
    missing = [field for field in spec["required"] if field not in arguments]
    unknown = set(arguments) - set(spec["parameters"])
    if missing or unknown:
        raise ValueError(f"invalid arguments for {name}")
    return arguments
