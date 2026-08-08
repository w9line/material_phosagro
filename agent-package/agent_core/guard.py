from __future__ import annotations

import re
from typing import Any

INJECTION_MARKERS = (
    "ignore system", "ignore previous", "забудь инструкции", "забудь всё", "забудь все",
    "новая системная инструкция", "ты теперь программист", "раскрой промпт", "system prompt",
    "альцгеймер", "пузырьковую сортировку", "bubble sort",
)
OFF_DOMAIN_MARKERS = ("html", "javascript", "python-код", "python code", "пузырьков")


def guard_reason(message: str) -> str | None:
    normalized = message.lower()
    if any(marker in normalized for marker in INJECTION_MARKERS):
        return "Похоже на попытку изменить инструкции ассистента."
    if any(marker in normalized for marker in OFF_DOMAIN_MARKERS) and not any(word in normalized for word in ("парт", "сырь", "материал", "склад", "план")):
        return "Запрос находится вне области контроля сырья."
    return None


def trusted_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    drop_next_assistant = False
    for item in history:
        content = item.get("content", "")
        if item.get("role") == "user" and guard_reason(content):
            drop_next_assistant = True
            continue
        if drop_next_assistant and item.get("role") == "assistant":
            drop_next_assistant = False
            continue
        result.append(item)
    return result[-12:]


def out_of_scope_answer(message: str) -> str | None:
    reason = guard_reason(message)
    if not reason:
        return None
    return "Я работаю только с контролем качества сырья, партиями, остатками и производственным планированием. " + reason
