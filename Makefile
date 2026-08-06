.PHONY: test eval-agent-mocked eval-agent-live format-check mcp-run-stdio mcp-up mcp-down mcp-logs test-mcp mcp-smoke

test:
	docker compose build api
	docker compose run --rm api pytest -q /app/tests

eval-agent-mocked:
	docker compose build api
	docker compose run --rm api python /app/scripts/run_agent_eval.py

eval-agent-live:
	@test "$${RUN_LIVE_LLM_EVAL:-}" = 1 || (echo 'Set RUN_LIVE_LLM_EVAL=1 to spend provider quota' && exit 1)
	docker compose build api
	docker compose run --rm api python /app/scripts/run_live_eval.py

format-check:
	python3 -m py_compile services/api/app.py services/mcp/server.py scripts/run_agent_eval.py
	git diff --check

mcp-run-stdio:
	MCP_TRANSPORT=stdio python services/mcp/server.py

mcp-up:
	docker compose --profile mcp up -d --build mcp

mcp-down:
	docker compose --profile mcp stop mcp

mcp-logs:
	docker compose --profile mcp logs -f mcp

test-mcp:
	docker compose --profile mcp build mcp
	docker compose --profile mcp run --rm mcp python -m pytest -q /app/services/mcp/tests

mcp-smoke:
	@curl -fsS http://127.0.0.1:$${MCP_PORT:-8011}/health
