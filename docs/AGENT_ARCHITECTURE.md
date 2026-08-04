# AI-agent architecture

The request path is deterministic at the trust boundary:

1. `route_intent()` classifies the message as `EXPLAIN_TOOL`, `EXECUTE_TOOL`, `CLARIFY`, `GENERAL_HELP` or `NAVIGATE`.
2. `TOOL_REGISTRY` is the single source for tool names, descriptions, schemas, examples, units and mutation flags.
3. Only an unambiguous `EXECUTE_TOOL` can reach a calculation. Missing material, requirements, policy or mass basis produces a web choice/question.
4. Tools return preview data only. Plan confirmation is a separate authenticated API action with ownership and a transaction.
5. VseLLM explains tool results but cannot override the deterministic execution gate.

Every calculation result carries `meta.data_version`, `meta.calculated_at`, `meta.parameters` and `meta.units`.
