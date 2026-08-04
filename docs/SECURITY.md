# Security notes

- Business endpoints require a live session; health and readiness are public.
- Chat history is scoped by `user_id`; admin chat inspection is explicit and admin-only.
- LLM output is not an authorization boundary and cannot execute a tool when the router says `CLARIFY` or `EXPLAIN_TOOL`.
- API keys stay in the deployment environment and are not committed.
- Plan previews are owned in `plan_owners`; another account cannot confirm a foreign preview by guessing its id.
