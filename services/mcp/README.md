# Raw Material AI MCP

Thin official MCP SDK adapter over the existing `services/api/app.py` registry and DAL.
It exposes only registry tools marked `mutating: false`; it does not duplicate domain calculations.

Transports:

- stdio: `MCP_TRANSPORT=stdio python services/mcp/server.py`
- Streamable HTTP: `MCP_TRANSPORT=streamable-http` on `http://127.0.0.1:8011/mcp`

Set `MCP_BEARER_TOKEN` for HTTP bearer authentication. The Compose profile binds port 8011 to localhost only.
