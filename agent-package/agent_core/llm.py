from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen
from typing import Any, Iterator

from .contracts import tool_specs, validate_tool_call


class OpenAICompatibleClient:
    def __init__(self):
        self.key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "openai/gpt-5-nano")
        self.timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

    def complete(self, messages: list[dict[str, Any]], with_tools: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, "temperature": 0.1, "max_tokens": 1800, "messages": messages}
        if with_tools:
            body.update({"tools": tool_specs(), "tool_choice": "auto"})
        request = Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(), method="POST", headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def stream_text(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        body = {"model": self.model, "temperature": 0.1, "max_tokens": 1800, "messages": messages, "stream": True}
        request = Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(), method="POST", headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                choices = json.loads(payload).get("choices") or []
                if choices:
                    text = choices[0].get("delta", {}).get("content") or ""
                    if text:
                        yield text
