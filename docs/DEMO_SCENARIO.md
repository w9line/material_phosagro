# Fixed demo scenario

1. Sign in as the demo operator.
2. Open **Партии и данные** and show the PostgreSQL source, current version and classifications.
3. Open **Ассистент** and ask: `Покажи остатки по A`.
4. Ask: `А теперь по B` to demonstrate contextual follow-up.
5. Ask: `Построй недельный план A 3000 кг активного вещества B 2500 кг активного вещества C 1800 кг активного вещества hybrid`.
6. Explain one selected batch and point to `selection_rank` and `selection_reason`.
7. Open the preview, then change data or confirm another plan and show the stale-preview conflict.
8. Open **Отчёты по браку**, generate the report and download the authenticated CSV.

The demo deliberately shows both a successful calculation and a safe refusal/clarification. It does not confirm a plan against production data without an explicit operator action.
