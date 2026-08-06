import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "api"))
sys.path.insert(0, str(Path(__file__).parents[1]))
import server


def test_only_read_only_registry_tools_are_exposed():
    expected = {name for name, spec in server.app.TOOL_REGISTRY.items() if spec.get("mutating", True) is False}
    assert set(server.SAFE_TOOLS) == expected
    assert all(spec.get("mutating") is False for spec in server.SAFE_TOOLS.values())


def test_mcp_schema_matches_registry_and_forbids_extra_fields():
    for name, spec in server.SAFE_TOOLS.items():
        tool = server.mcp._tool_manager.get_tool(name)
        assert tool is not None
        assert tool.parameters == server._schema(spec)
        assert tool.parameters["additionalProperties"] is False
        assert not any(key in json.dumps(tool.parameters) for key in ("user_id", "admin", "raw_sql", "session_id"))


def test_success_envelope_keeps_domain_result(monkeypatch):
    monkeypatch.setattr(server.app, "tool", lambda name, args: {"value": 42, "meta": {"data_version": 7, "calculated_at": "now"}})
    result = server.execute("get_inventory_summary", {"material_type": None, "group_by": "material_and_status"})
    assert result["ok"] is True
    assert result["tool"] == "get_inventory_summary"
    assert result["data"]["value"] == 42
    assert result["meta"]["data_version"] == 7
    assert result["meta"]["source"] == "mcp"


@pytest.mark.parametrize("arguments", [{"user_id": "x"}, {"admin": True}, {"raw_sql": "DROP TABLE batches"}, {"requirements": {"user_id": 1}}])
def test_reserved_inputs_are_rejected_without_execution(monkeypatch, arguments):
    called = False

    def fail(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("domain tool must not run")

    monkeypatch.setattr(server.app, "tool", fail)
    result = server.execute("get_inventory_summary", arguments)
    assert result["ok"] is False
    assert result["error"]["code"] == "VALIDATION_ERROR"
    assert called is False


def test_unknown_tool_and_tool_errors_are_safe(monkeypatch):
    assert server.execute("delete_everything", {})["error"]["code"] == "VALIDATION_ERROR"
    monkeypatch.setattr(server.app, "tool", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret DSN / path")))
    result = server.execute("get_inventory_summary", {})
    assert result["error"]["code"] == "TOOL_ERROR"
    assert "secret" not in json.dumps(result).lower()
    assert "dsn" not in json.dumps(result).lower()


def test_planning_result_preserves_backend_invariants(monkeypatch, tmp_path):
    monkeypatch.setattr(server.app, "DB_PATH", str(tmp_path / "mcp.db"))
    monkeypatch.setattr(server.app, "DATABASE_URL", "sqlite:///mcp.db")
    server.app.init_db()
    result = server.execute("build_weekly_plan", {"requirements": {"A": 3000}, "policy": "strict_fifo", "allow_rework": True})
    assert result["ok"] is True
    item = result["data"]["materials"]["A"]
    assert item["covered_active_mass_kg"] + item["deficit_active_mass_kg"] == item["required_active_mass_kg"]


def test_health_route_is_available():
    from starlette.testclient import TestClient

    client = TestClient(server.BearerMiddleware(server.mcp.streamable_http_app()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_http_bearer_guard(monkeypatch):
    from starlette.testclient import TestClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    monkeypatch.setattr(server, "MCP_BEARER_TOKEN", "secret")
    async def endpoint(_request):
        return PlainTextResponse("ok")

    with TestClient(server.BearerMiddleware(Starlette(routes=[Route("/mcp", endpoint)]))) as client:
        assert client.get("/mcp").status_code == 401
        assert client.get("/mcp", headers={"Authorization": "Bearer secret"}).status_code == 200
