from core import *

def llm_agent(message: str, history: list[dict[str, str]]) -> tuple[str, str, Any, list[dict[str, Any]]] | None:
    key = os.getenv("LLM_API_KEY")
    if not key: raise RuntimeError("VseLLM не подключён: отсутствует LLM_API_KEY")
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    intent = route_intent(message, history)
    if intent["intent"] == "CLARIFY": return "assistant", clarification_text(intent), {"choices": intent.get("choices", [])}, []
    routed = routed_tool_result(message, history)
    if routed or intent["intent"] == "EXPLAIN_TOOL" or (intent["intent"] == "GENERAL_HELP" and not llm_may_select_tool(message)):
        name, data, trace = routed or (intent.get("tool_name"), None, [])
        _, messages = explanation_prompt(message, history, name, data)
        body = {"model": os.getenv("LLM_MODEL", "openai/gpt-5-nano"), "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")), "max_tokens": int(os.getenv("LLM_EXPLAIN_MAX_TOKENS", "1200")), "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "low"), "messages": messages}
        req = URLRequest(base + "/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))) as response: result = json.load(response)
        except Exception as exc:
            raise RuntimeError(f"VseLLM не ответил: {exc}") from exc
        content = (result["choices"][0]["message"].get("content") or "").strip()
        if not content: raise RuntimeError("VseLLM вернул пустой ответ")
        if content == "Расчёт завершён. Подробности доступны в результате инструмента.": raise RuntimeError("VseLLM вернул технический fallback вместо объяснения")
        if data and not answer_numbers_are_grounded(content, data): raise RuntimeError("Ответ VseLLM не прошёл проверку чисел")
        return "llm", content, data, trace
    explanation_tool = explanation_tool_for_message(message)
    system = """Ты — AI-технолог системы контроля качества сырья. Отвечай по-русски. Все данные и расчёты получай только через инструменты. Не придумывай партии и числа. После tool call объясни результат простыми словами, отделяй массу сырья от массы активного вещества. Используй только числа, явно присутствующие в JSON результата; новые суммы и производные показатели не рассчитывай. Preview-план не подтверждай сам. Всегда заверши ответ коротким понятным текстом; пустой ответ запрещён."""
    if explanation_tool: system += f" Пользователь просит объяснить инструмент {explanation_tool}. {registry_explanation(explanation_tool)} Расскажи назначение, когда он нужен, параметры и результат. Не запускай инструмент и не выдумывай поля. Ответ краткий — до 120 слов."
    messages = [{"role": "system", "content": system + "\nСжатый контекст: " + llm_context(history)}]
    messages.extend(compact_history(history))
    messages.append({"role": "user", "content": message})
    trace: list[dict[str, Any]] = []
    last_data: Any = None
    forced_used = False
    retry_used = False
    for _ in range(int(os.getenv("LLM_MAX_TOOL_ROUNDS", "4"))):
        body = {"model": os.getenv("LLM_MODEL", "openai/gpt-5-nano"), "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")), "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2000")), "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "low"), "messages": messages, "tools": tool_specs(), "tool_choice": "auto"}
        req = URLRequest(base + "/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))) as response: result = json.load(response)
        msg = result["choices"][0]["message"]
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if calls and intent["intent"] == "EXPLAIN_TOOL":
            content = (msg.get("content") or "").strip() or (registry_explanation(explanation_tool) if explanation_tool else "Я могу показать фактические данные через инструменты, но для этого нужна явная команда на расчёт.")
            return "llm", content, None, trace
        if not calls:
            forced = forced_tool_for_message(message, history) if not forced_used else None
            if forced:
                forced_used = True
                name, args = forced; call_id = "forced-" + uuid.uuid4().hex
                try:
                    last_data = tool(name, args); trace.append({"tool": name, "arguments": args, "status": "success", "source": "forced"}); tool_result = last_data
                except Exception as exc:
                    trace.append({"tool": name, "arguments": args, "status": "error", "message": str(exc), "source": "forced"}); tool_result = {"error": str(exc)}
                messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
                messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": json.dumps(tool_result, ensure_ascii=False)})
                continue
            content = (msg.get("content") or "").strip()
            if not content and not retry_used:
                retry_used = True
                messages.append({"role": "user", "content": "Сформулируй короткий содержательный ответ на исходный вопрос. Не возвращай пустой ответ."})
                continue
            if not content: raise RuntimeError("VseLLM вернул пустой ответ")
            if content == "Расчёт завершён. Подробности доступны в результате инструмента.": raise RuntimeError("VseLLM вернул технический fallback вместо объяснения")
            if last_data and not answer_numbers_are_grounded(content, last_data): raise RuntimeError("Ответ VseLLM не прошёл проверку чисел")
            return "llm", content, last_data, trace
        for call in calls:
            name = call["function"]["name"]
            if name not in TOOLS: raise ValueError("unknown tool")
            args = json.loads(call["function"].get("arguments") or "{}")
            try:
                last_data = tool(name, args); trace.append({"tool": name, "arguments": args, "status": "success", "source": "model"})
                tool_result = last_data
            except Exception as exc:
                trace.append({"tool": name, "arguments": args, "status": "error", "message": str(exc), "source": "model"}); tool_result = {"error": str(exc)}
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": json.dumps(tool_result, ensure_ascii=False)})
    raise RuntimeError("VseLLM не завершил агентский цикл за допустимое число шагов")

def llm_agent_stream(message: str, history: list[dict[str, str]]):
    intent = route_intent(message, history)
    if intent["intent"] == "CLARIFY":
        answer = clarification_text(intent)
        yield {"type": "token", "text": answer}
        yield {"type": "done", "response": {"mode": "assistant", "answer": answer, "result": {"choices": intent.get("choices", [])}, "choices": intent.get("choices", []), "needs_clarification": True, "tool_calls": []}}
        return
    key = os.getenv("LLM_API_KEY")
    if not key: raise RuntimeError("VseLLM не подключён: отсутствует LLM_API_KEY")
    base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    routed = routed_tool_result(message, history)
    if routed or intent["intent"] == "EXPLAIN_TOOL" or (intent["intent"] == "GENERAL_HELP" and not llm_may_select_tool(message)):
        name, data, trace = routed or (intent.get("tool_name"), None, [])
        if trace:
            yield {"type": "tool", "tool": trace[-1]["tool"], "status": trace[-1]["status"]}
        _, messages = explanation_prompt(message, history, name, data)
        body = {"model": os.getenv("LLM_MODEL", "openai/gpt-5-nano"), "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")), "max_tokens": int(os.getenv("LLM_EXPLAIN_MAX_TOKENS", "1200")), "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "low"), "messages": messages, "stream": True}
        req = URLRequest(base + "/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        answer_parts: list[str] = []
        try:
            with urlopen(req, timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line.startswith("data:"): continue
                    payload = line[5:].strip()
                    if payload == "[DONE]": break
                    delta = json.loads(payload).get("choices", [{}])[0].get("delta", {}).get("content") or ""
                    if delta: answer_parts.append(delta)
        except Exception as exc:
            raise RuntimeError(f"VseLLM не ответил: {exc}") from exc
        answer = "".join(answer_parts).strip()
        if not answer: raise RuntimeError("VseLLM вернул пустой ответ")
        if answer == "Расчёт завершён. Подробности доступны в результате инструмента.": raise RuntimeError("VseLLM вернул технический fallback вместо объяснения")
        if data and not answer_numbers_are_grounded(answer, data): raise RuntimeError("Ответ VseLLM не прошёл проверку чисел")
        yield {"type": "done", "response": {"mode": "llm", "answer": answer, "result": data, "tool_calls": trace}}
        return
    explanation_tool = explanation_tool_for_message(message)
    system = """Ты — AI-технолог системы контроля качества сырья. Отвечай по-русски. Все данные и расчёты получай только через инструменты. Не придумывай партии и числа. После tool call объясни результат простыми словами, отделяй массу сырья от массы активного вещества. Используй только числа, явно присутствующие в JSON результата; новые суммы и производные показатели не рассчитывай. Preview-план не подтверждай сам. Всегда заверши ответ коротким понятным текстом; пустой ответ запрещён."""
    if explanation_tool: system += f" Пользователь просит объяснить инструмент {explanation_tool}. {registry_explanation(explanation_tool)} Расскажи назначение, когда он нужен, параметры и результат. Не запускай инструмент и не выдумывай поля. Ответ краткий — до 120 слов."
    messages = [{"role": "system", "content": system + "\nСжатый контекст: " + llm_context(history)}]
    messages.extend(compact_history(history))
    messages.append({"role": "user", "content": message})
    trace: list[dict[str, Any]] = []
    last_data: Any = None
    forced_used = False
    retry_used = False
    max_rounds = int(os.getenv("LLM_MAX_TOOL_ROUNDS", "2"))
    for round_index in range(max_rounds):
        body = {"model": os.getenv("LLM_MODEL", "openai/gpt-5-nano"), "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")), "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "2000")), "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "low"), "messages": messages, "tools": tool_specs(), "tool_choice": "auto"}
        streaming = round_index > 0
        if streaming:
            body["stream"] = True
            body["tool_choice"] = "auto" if explanation_tool else "none"
        req = URLRequest(base + "/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))) as response:
            if not streaming:
                result = json.load(response)
                msg = result["choices"][0]["message"]
                messages.append(msg)
                calls = msg.get("tool_calls") or []
                if calls and intent["intent"] == "EXPLAIN_TOOL":
                    answer = (msg.get("content") or "").strip() or (registry_explanation(explanation_tool) if explanation_tool else "Я могу показать фактические данные через инструменты, но для этого нужна явная команда на расчёт.")
                    yield {"type": "token", "text": answer}
                    yield {"type": "done", "response": {"mode": "llm", "answer": answer, "result": None, "tool_calls": []}}
                    return
                if not calls:
                    forced = forced_tool_for_message(message, history) if not forced_used else None
                    if forced:
                        forced_used = True
                        name, args = forced; call_id = "forced-" + uuid.uuid4().hex
                        try:
                            last_data = tool(name, args); trace.append({"tool": name, "arguments": args, "status": "success", "source": "forced"}); tool_result = last_data
                        except Exception as exc:
                            trace.append({"tool": name, "arguments": args, "status": "error", "message": str(exc), "source": "forced"}); tool_result = {"error": str(exc)}
                        messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
                        messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": json.dumps(tool_result, ensure_ascii=False)})
                        yield {"type": "tool", "tool": name, "status": trace[-1]["status"]}
                        continue
                    content = (msg.get("content") or "").strip()
                    if not content and not retry_used:
                        retry_used = True
                        messages.append({"role": "user", "content": "Сформулируй короткий содержательный ответ на исходный вопрос. Не возвращай пустой ответ."})
                        continue
                    if not content: raise RuntimeError("VseLLM вернул пустой ответ")
                    if content == "Расчёт завершён. Подробности доступны в результате инструмента.": raise RuntimeError("VseLLM вернул технический fallback вместо объяснения")
                    if last_data and not answer_numbers_are_grounded(content, last_data): raise RuntimeError("Ответ VseLLM не прошёл проверку чисел")
                    answer = content
                    yield {"type": "token", "text": answer}
                    yield {"type": "done", "response": {"mode": "llm", "answer": answer, "result": last_data, "tool_calls": trace}}
                    return
                for call in calls:
                    name = call["function"]["name"]
                    if name not in TOOLS: raise ValueError("unknown tool")
                    args = json.loads(call["function"].get("arguments") or "{}")
                    try:
                        last_data = tool(name, args); trace.append({"tool": name, "arguments": args, "status": "success", "source": "model"}); tool_result = last_data
                    except Exception as exc:
                        trace.append({"tool": name, "arguments": args, "status": "error", "message": str(exc), "source": "model"}); tool_result = {"error": str(exc)}
                    yield {"type": "tool", "tool": name, "status": trace[-1]["status"]}
                    messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": json.dumps(tool_result, ensure_ascii=False)})
                continue
            answer_parts: list[str] = []
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data:"): continue
                payload = line[5:].strip()
                if payload == "[DONE]": break
                chunk = json.loads(payload)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                text = delta.get("content") or ""
                if text:
                    answer_parts.append(text)
                    yield {"type": "token", "text": text}
            answer = "".join(answer_parts).strip()
            if not answer: raise RuntimeError("VseLLM вернул пустой ответ")
            if answer == "Расчёт завершён. Подробности доступны в результате инструмента.": raise RuntimeError("VseLLM вернул технический fallback вместо объяснения")
            if last_data and not answer_numbers_are_grounded(answer, last_data): raise RuntimeError("Ответ VseLLM не прошёл проверку чисел")
            yield {"type": "done", "response": {"mode": "llm", "answer": answer, "result": last_data, "tool_calls": trace}}
            return
    raise RuntimeError("VseLLM не завершил агентский цикл за допустимое число шагов")
