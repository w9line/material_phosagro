from __future__ import annotations

import re
from typing import Any

from .contracts import POLICIES


def material_from(message: str, materials: list[str]) -> str | None:
    match = re.search(r"(?:материал\s*)?\b([A-Z][A-Z0-9_-]{0,15})\b", message.upper())
    return match.group(1) if match and match.group(1) in set(materials) else None


def requirements_from(message: str, materials: list[str]) -> dict[str, float]:
    result = {}
    for material, value in re.findall(r"\b([A-Z][A-Z0-9_-]{0,15})\s*(?:=|:)?\s*(\d+(?:[.,]\d+)?)", message.upper()):
        if material in set(materials):
            result[material] = float(value.replace(",", "."))
    return result


def policy_from(message: str) -> str | None:
    normalized = message.lower()
    if "fifo" in normalized:
        return "strict_fifo"
    if "hybrid" in normalized:
        return "hybrid"
    if "концентрац" in normalized or "max_concentration" in normalized:
        return "max_concentration"
    return None


def explain_tool(message: str) -> str | None:
    normalized = message.lower()
    if not any(word in normalized for word in ("как работает", "что делает", "объясни", "расскажи про", "зачем нужен", "не запускай")):
        return None
    aliases = {
        "остат": "get_inventory_summary", "дефицит": "check_material_deficit", "план": "build_weekly_plan",
        "брак": "generate_rejection_report", "график": "build_chart", "классифиц": "classify_batches",
        "качество": "check_batch_quality", "стратег": "compare_allocation_policies",
    }
    return next((tool for alias, tool in aliases.items() if alias in normalized), None)


def route(message: str, materials: list[str]) -> dict[str, Any]:
    normalized = message.lower()
    material = material_from(message, materials)
    explained = explain_tool(message)
    if explained:
        return {"intent": "EXPLAIN_TOOL", "tool_name": explained, "arguments": {}, "missing_fields": []}
    if any(word in normalized for word in ("проверь качество", "статус партии")):
        match = re.search(r"\b([A-Z][A-Z0-9_-]{1,30}-[A-Z0-9_-]+)\b", message.upper())
        if not match:
            return {"intent": "CLARIFY", "tool_name": "check_batch_quality", "arguments": {}, "missing_fields": ["batch_id"], "question": "Какую партию проверить?", "choices": []}
        return {"intent": "EXECUTE_TOOL", "tool_name": "check_batch_quality", "arguments": {"batch_id": match.group(1)}, "missing_fields": []}
    if any(word in normalized for word in ("остат", "склад", "запас")):
        if not material and not any(word in normalized for word in ("все", "всем", "общ")):
            return {"intent": "CLARIFY", "tool_name": "get_inventory_summary", "arguments": {}, "missing_fields": ["material_type"], "question": "По какому материалу показать остатки?", "choices": [{"label": "Все материалы", "value": "Покажи остатки по всем материалам"}] + [{"label": code, "value": f"Покажи остатки по {code}"} for code in materials]}
        return {"intent": "EXECUTE_TOOL", "tool_name": "get_inventory_summary", "arguments": {"material_type": material, "group_by": "material_and_status"}, "missing_fields": []}
    if any(word in normalized for word in ("недельный план", "план производства", "построй план", "составь план")):
        requirements = requirements_from(message, materials)
        missing = [code for code in materials if code not in requirements]
        if missing:
            return {"intent": "CLARIFY", "tool_name": "build_weekly_plan", "arguments": {"requirements": requirements}, "missing_fields": [f"requirements.{code}" for code in missing], "question": f"Укажите потребность по активному веществу для: {', '.join(missing)}.", "choices": []}
        return {"intent": "EXECUTE_TOOL", "tool_name": "build_weekly_plan", "arguments": {"requirements": requirements, "policy": policy_from(message) or "hybrid", "allow_rework": True}, "missing_fields": []}
    if any(word in normalized for word in ("дефицит", "хватит", "вытян")):
        requirements = requirements_from(message, materials)
        if not requirements:
            return {"intent": "CLARIFY", "tool_name": "check_material_deficit", "arguments": {}, "missing_fields": ["requirements"], "question": "Укажите потребность в кг активного вещества, например: A 3000, B 2500, C 1800.", "choices": []}
        return {"intent": "EXECUTE_TOOL", "tool_name": "check_material_deficit", "arguments": {"requirements": requirements, "include_rework": True}, "missing_fields": []}
    if any(word in normalized for word in ("брак", "отклон", "доработ")):
        if "график" in normalized or "диаграм" in normalized:
            return {"intent": "EXECUTE_TOOL", "tool_name": "build_chart", "arguments": {"chart_type": "quality", "metric": "rejection_batch_count", "group_by": "material", "material_type": material}, "missing_fields": []}
        return {"intent": "EXECUTE_TOOL", "tool_name": "generate_rejection_report", "arguments": {"material_type": material, "include_rework": True, "include_rejected": True}, "missing_fields": []}
    if any(word in normalized for word in ("старые партии", "старейшие партии", "самую старую")):
        return {"intent": "EXECUTE_TOOL", "tool_name": "get_oldest_batches", "arguments": {"material_type": material, "limit": 5}, "missing_fields": []}
    if "классифиц" in normalized:
        return {"intent": "EXECUTE_TOOL", "tool_name": "classify_batches", "arguments": {"material_type": material, "only_unclassified": False}, "missing_fields": []}
    return {"intent": "GENERAL_HELP", "tool_name": None, "arguments": {}, "missing_fields": []}
