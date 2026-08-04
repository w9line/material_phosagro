.PHONY: test eval-agent-mocked eval-agent-live format-check

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
	python3 -m py_compile services/api/app.py scripts/run_agent_eval.py
	git diff --check
