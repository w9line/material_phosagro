from __future__ import annotations

import json
import os
from typing import Any, Iterator

from .contracts import TOOL_REGISTRY, validate_tool_call
from .guard import out_of_scope_answer, trusted_history
from .llm import OpenAICompatibleClient
from .router import route


class AgentService:
    def __init__(self, gateway: Any, llm: Any | None = None):
        self.gateway = gateway
        self.llm = llm or (OpenAICompatibleClient() if os.getenv("LLM_API_KEY") else None)

    def _fallback(self, message: str, data: Any = None) -> str:
        if data is None:
            return "Я помогаю с партиями, качеством сырья, остатками, дефицитом, планом и отчётами."
        return "Расчёт выполнен. Подробности доступны в результате инструмента."

    def handle(self, message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        history = trusted_history(history or [])
        refused = out_of_scope_answer(message)
        if refused:
            return {"mode": "assistant", "answer": refused, "tool_calls": [], "needs_clarification": False}
        intent = route(message, self.gateway.materials())
        if intent["intent"] == "CLARIFY":
            return {"mode": "assistant", "answer": intent["question"], "question": intent["question"], "choices": intent.get("choices", []), "needs_clarification": True, "tool_calls": []}
        if intent["intent"] == "EXPLAIN_TOOL":
            return {"mode": "assistant", "answer": self._explain(intent["tool_name"]), "tool_calls": []}
        if intent["intent"] == "EXECUTE_TOOL":
            name = intent["tool_name"]
            arguments = validate_tool_call(name, intent["arguments"])
            data = self.gateway.call(name, arguments)
            trace = [{"tool": name, "arguments": arguments, "status": "success"}]
            answer = self._explain_result(message, name, data, history)
            return {"mode": "llm" if self.llm else "offline", "answer": answer, "result": data, "tool_calls": trace}
        answer, data, trace = self._general(message, history)
        return {"mode": "llm" if self.llm else "offline", "answer": answer, "result": data, "tool_calls": trace}

    def stream(self, message: str, history: list[dict[str, str]] | None = None) -> Iterator[dict[str, Any]]:
        result = self.handle(message, history)
        for call in result.get("tool_calls", []):
            yield {"type": "tool", "tool": call["tool"], "status": call["status"]}
        answer = result["answer"]
        if self.llm and result.get("mode") == "llm" and not result.get("result"):
            for chunk in self.llm.stream_text([{"role": "system", "content": "Отвечай по-русски только в области контроля сырья. Не придумывай числа."}, {"role": "user", "content": message}]):
                yield {"type": "token", "text": chunk}
        else:
            yield {"type": "token", "text": answer}
        yield {"type": "done", "response": result}

    def _explain(self, tool_name: str) -> str:
        spec = TOOL_REGISTRY[tool_name]
        return f"{tool_name} — {spec['description']} Параметры: {', '.join(spec['parameters']) or 'нет обязательных параметров'}. Инструмент выполняет расчёт на backend, агент только объясняет результат."

    def _explain_result(self, message: str, name: str, data: Any, history: list[dict[str, str]]) -> str:
        if not self.llm:
            return self._fallback(message, data)
        prompt = [{"role": "system", "content": "Ты AI-технолог контроля сырья. Объясни результат backend-инструмента по-русски. Используй только факты и числа из JSON. Не выполняй новые расчёты и не меняй данные."}, *history[-6:], {"role": "user", "content": message}, {"role": "system", "content": "Tool " + name + " result:\n" + json.dumps(data, ensure_ascii=False)}]
        response = self.llm.complete(prompt, with_tools=False)
        return (response.get("choices", [{}])[0].get("message", {}).get("content") or self._fallback(message, data)).strip()

    def _general(self, message: str, history: list[dict[str, str]]) -> tuple[str, Any, list[dict[str, Any]]]:
        if not self.llm:
            return self._fallback(message), None, []
        messages = [{"role": "system", "content": "Ты AI-ассистент контроля сырья. Отвечай по-русски и не выходи за пределы домена. Используй tools для фактов, не придумывай числа."}, *history[-6:], {"role": "user", "content": message}]
        trace: list[dict[str, Any]] = []
        data = None
        for _ in range(2):
            response = self.llm.complete(messages, with_tools=True)
            msg = response.get("choices", [{}])[0].get("message", {})
            calls = msg.get("tool_calls") or []
            if not calls:
                return (msg.get("content") or self._fallback(message, data)).strip(), data, trace
            messages.append(msg)
            for call in calls:
                name = call.get("function", {}).get("name", "")
                arguments = validate_tool_call(name, json.loads(call.get("function", {}).get("arguments") or "{}"))
                data = self.gateway.call(name, arguments)
                trace.append({"tool": name, "arguments": arguments, "status": "success"})
                messages.append({"role": "tool", "tool_call_id": call.get("id", name), "name": name, "content": json.dumps(data, ensure_ascii=False)})
        return self._fallback(message, data), data, trace
