from __future__ import annotations

import json
from urllib.request import Request, urlopen
from typing import Any


class HttpToolGateway:
    def __init__(self, base_url: str, token: str = "", timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        request = Request(self.base_url + "/internal/tools/" + name, data=json.dumps(arguments).encode(), method="POST", headers={"Content-Type": "application/json", "X-Agent-Token": self.token})
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response)
        return payload.get("result", payload)

    def materials(self) -> list[str]:
        try:
            request = Request(self.base_url + "/internal/materials", headers={"X-Agent-Token": self.token})
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
            return [row["material_type"] for row in payload]
        except Exception:
            return ["A", "B", "C"]


class MockToolGateway:
    def __init__(self, results: dict[str, Any] | None = None, materials: list[str] | None = None):
        self.results = results or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._materials = materials or ["A", "B", "C"]

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return self.results.get(name, {"tool": name, "arguments": arguments, "meta": {"units": {}}})

    def materials(self) -> list[str]:
        return self._materials
