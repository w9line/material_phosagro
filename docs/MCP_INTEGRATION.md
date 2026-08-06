# MCP integration

The project includes a small MCP wrapper based on the official Python SDK `mcp>=1.28,<2`.
It reuses the existing `TOOL_REGISTRY` and `app.tool()` functions, so REST, Function Calling, VseLLM, PostgreSQL and the UI remain unchanged.

## Start

```bash
MCP_BEARER_TOKEN=change-this make mcp-up
curl http://127.0.0.1:8011/health
```

The service is in the Compose `mcp` profile and is not publicly bound. MCP clients use Streamable HTTP at `/mcp`; stdio is available with `make mcp-run-stdio`.

## Configuration

`MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `MCP_BEARER_TOKEN`, `MCP_SERVICE_USER_ID`, and `MCP_LOG_LEVEL` are read from the environment.

The wrapper exposes read-only quality, inventory, planning preview, report, chart and scenario tools. It rejects unknown fields and reserved control fields (`user_id`, admin flags, confirmation, data version, raw SQL, paths, tokens and session IDs). Errors return a stable envelope without tracebacks, DSNs, paths or secrets.

Resources are limited to `system://info`, `schemas://tools`, and `quality://rules`.

## Testing

```bash
make test-mcp
make mcp-smoke
```
