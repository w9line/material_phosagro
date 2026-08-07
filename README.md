# Raw Material AI

Минимальный запускаемый сервис контроля качества сырья и планирования. API слушает `8009`, генератор синтетических данных — `8010`.

## Запуск

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:8009/health
```

Открыть `http://localhost:8009`. На хосте `pm_rtx` сервис доступен по `http://192.168.0.51:8009`.

## Что работает

- CSV/XLSX/ZIP preview и импорт с построчными ошибками;
- ручной REST API партий, правил и потребностей;
- классификация GOOD/REWORK/REJECTED;
- активное вещество, остатки, FIFO/max concentration/hybrid;
- preview/confirm плана с частичным использованием и экспортом производственного недельного плана в CSV;
- сравнение стратегий, сценарный анализ, CSV-отчёт;
- 9 backend-инструментов, offline AI-router без ключа и SSE-стриминг ответа ассистента;
- отдельный генератор ZIP с пресетами и seed;
- health/ready, Docker Compose, PostgreSQL persistence (SQLite остаётся для локальных тестов).
- регистрация/авторизация, история чатов, мобильная вёрстка и админка: закрытие регистрации, блокировка пользователей и просмотр их чатов.

## LLM

Задайте `LLM_API_KEY` и при необходимости `LLM_BASE_URL`, затем перезапустите API. Для VseLLM используется `https://api.vsellm.ru/v1`; ключ не попадает во frontend. Без ключа чат работает в offline-режиме через тот же backend. `LLM_MAX_TOOL_ROUNDS=2`, `LLM_MAX_TOKENS=2000` и `LLM_EXPLAIN_MAX_TOKENS=650` удерживают reasoning-модель в пределах разумной задержки без пустых ответов. Очевидные команды сначала проходят через детерминированный backend-router, затем VseLLM объясняет проверенный результат.

Администратор создаётся из `ADMIN_USERNAME`/`ADMIN_PASSWORD` при первом запуске. На `pm_rtx` заданы креды из ТЗ; в репозитории пароль не хранится.

## Проверка

```bash
pip install -r services/api/requirements.txt
PYTHONPATH=services/api pytest -q services/api/tests/test_domain.py
```

Ограничения и условные значения: [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).
