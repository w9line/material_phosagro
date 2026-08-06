from __future__ import annotations

import inspect
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Literal

import uvicorn
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.types import ASGIApp, Receive, Scope, Send

sys.path.insert(0, "/app/services/api")
import app


logging.basicConfig(level=os.getenv("MCP_LOG_LEVEL", "INFO"), stream=sys.stderr)
logger = logging.getLogger("raw-material-mcp")

MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http").lower()
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8011"))
MCP_BEARER_TOKEN = os.getenv("MCP_BEARER_TOKEN", "")
SERVICE_USER_ID = os.getenv("MCP_SERVICE_USER_ID", "mcp-service")
_RESERVED_KEYS = {"user_id", "admin", "role", "confirmed", "data_version", "raw_sql", "path", "session_id", "token"}

SAFE_TOOLS = {name: spec for name, spec in app.TOOL_REGISTRY.items() if spec.get("mutating", True) is False}
mcp = FastMCP("Raw Material AI MCP", host=MCP_HOST, port=MCP_PORT, streamable_http_path="/mcp", stateless_http=True)


def _schema(spec: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": spec.get("parameters", {}), "required": spec.get("required", []), "additionalProperties": False}


def _annotation(parameter: dict[str, Any]) -> Any:
    kind = parameter.get("type")
    if isinstance(kind, list):
        return str | None
    return {"string": str, "integer": int, "boolean": bool, "object": dict[str, Any], "array": list[Any]}.get(kind, Any)


def _wrapper(name: str, spec: dict[str, Any]):
    parameters = []
    ordered = sorted(spec.get("parameters", {}).items(), key=lambda item: item[0] not in spec.get("required", []))
    for parameter_name, parameter in ordered:
        default = inspect.Parameter.empty if parameter_name in spec.get("required", []) else None
        parameters.append(inspect.Parameter(parameter_name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=_annotation(parameter), default=default))

    async def invoke(**kwargs: Any) -> dict[str, Any]:
        return execute(name, kwargs)

    invoke.__name__ = name
    invoke.__signature__ = inspect.Signature(parameters, return_annotation=dict[str, Any])
    return invoke


def _contains_reserved(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key.lower() in _RESERVED_KEYS or _contains_reserved(item) for key, item in value.items())
    return any(_contains_reserved(item) for item in value) if isinstance(value, list) else False


def _meta(name: str, spec: dict[str, Any], data: Any) -> dict[str, Any]:
    source_meta = data.get("meta", {}) if isinstance(data, dict) else {}
    return {"source": "mcp", "calculated_at": source_meta.get("calculated_at", datetime.now(timezone.utc).isoformat()), "data_version": source_meta.get("data_version"), "units": spec.get("units", {})}


def _error(name: str, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": False, "tool": name, "error": {"code": code, "message": message, "details": details or {}}, "meta": {"source": "mcp"}}


def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    spec = SAFE_TOOLS.get(name)
    if not spec:
        return _error(name, "VALIDATION_ERROR", "Unknown or unavailable MCP tool")
    if _contains_reserved(arguments):
        return _error(name, "VALIDATION_ERROR", "Reserved control fields are not accepted")
    unknown = sorted(set(arguments) - set(spec.get("parameters", {})))
    if unknown:
        return _error(name, "VALIDATION_ERROR", "Unknown input fields", {"fields": unknown})
    try:
        data = app.tool(name, arguments)
        return {"ok": True, "tool": name, "data": data, "meta": _meta(name, spec, data)}
    except (KeyError, TypeError, ValueError) as exc:
        return _error(name, "VALIDATION_ERROR", str(exc)[:200])
    except Exception:
        logger.exception("MCP tool failed: %s", name)
        return _error(name, "TOOL_ERROR", "Tool execution failed")


for _name, _spec in SAFE_TOOLS.items():
    mcp.add_tool(
        _wrapper(_name, _spec),
        name=_name,
        title=_spec.get("title"),
        description=_spec.get("description", "Read-only raw material operation"),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
        structured_output=True,
    )
    mcp._tool_manager.get_tool(_name).parameters = _schema(_spec)


@mcp.resource("system://info")
def system_info() -> str:
    return json.dumps({"name": "Raw Material AI MCP", "version": "0.1.0", "service_user_id": SERVICE_USER_ID, "transport": MCP_TRANSPORT, "safe_tool_count": len(SAFE_TOOLS)}, ensure_ascii=False)


@mcp.resource("schemas://tools")
def schemas() -> str:
    return json.dumps({name: _schema(spec) for name, spec in SAFE_TOOLS.items()}, ensure_ascii=False)


@mcp.resource("quality://rules")
def quality_rules() -> str:
    return json.dumps(app.rules(), ensure_ascii=False)


class BearerMiddleware:
    def __init__(self, app_: ASGIApp):
        self.app = app_

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return
        if MCP_BEARER_TOKEN:
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            expected = f"Bearer {MCP_BEARER_TOKEN}".encode()
            if headers.get(b"authorization") != expected:
                response = JSONResponse({"detail": "authentication required"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Any) -> JSONResponse:
    return JSONResponse({"status": "ok", "transport": MCP_TRANSPORT, "tools": len(SAFE_TOOLS)})


def main() -> None:
    app.init_db()
    if MCP_TRANSPORT == "stdio":
        mcp.run(transport="stdio")
        return
    if MCP_TRANSPORT != "streamable-http":
        raise SystemExit("MCP_TRANSPORT must be stdio or streamable-http")
    uvicorn.run(BearerMiddleware(mcp.streamable_http_app()), host=MCP_HOST, port=MCP_PORT, log_level=os.getenv("MCP_LOG_LEVEL", "info").lower())


if __name__ == "__main__":
    main()
