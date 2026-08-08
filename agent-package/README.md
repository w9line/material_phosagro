# Raw Material Agent Package

Самостоятельная агентская часть для системы контроля сырья. Пакет не знает о PostgreSQL и не импортирует backend: все расчёты выполняются через HTTP `ToolGateway`.

## Быстрый запуск

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8012
```

Проверка:

```bash
curl http://localhost:8012/health
```

## Контракт backend

Агент вызывает:

```http
POST {BACKEND_URL}/internal/tools/{tool_name}
X-Agent-Token: {AGENT_SERVICE_TOKEN}
Content-Type: application/json
```

Тело запроса — аргументы конкретного tool. Ответ backend должен быть JSON с расчётом и желательно блоком `meta`:

```json
{
  "result": {},
  "meta": {
    "data_version": 12,
    "units": {"raw_mass": "kg_raw", "active_mass": "kg_active"}
  }
}
```

Для уточняющих вопросов агент пытается получить материалы через:

```http
GET {BACKEND_URL}/internal/materials
```

Ответ: `[{"material_type":"A"}]`. Если endpoint недоступен, используются A/B/C.

## Tools

`check_batch_quality`, `get_batch_details`, `get_oldest_batches`, `build_chart`, `classify_batches`, `get_inventory_summary`, `build_weekly_plan`, `check_material_deficit`, `compare_allocation_policies`, `generate_rejection_report`, `simulate_requirement_change`.

## Интеграция

Backend должен реализовать только описанный gateway-контракт. Frontend может использовать агентские endpoints:

```http
POST /v1/chat
POST /v1/chat/stream
```

SSE-события: `status`, `clarify`, `tool`, `token`, `done`, `error`.

LLM-ключ хранится только в окружении агента. Агент не принимает решение о правах, не подтверждает production-план и не считает доменные показатели самостоятельно.
