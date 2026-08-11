from core import *
from agent import llm_agent, llm_agent_stream
from urllib.parse import quote

def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


app = FastAPI(title="Raw Material AI", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None: init_db()


@app.get("/", include_in_schema=False)
def index() -> FileResponse: return FileResponse(Path(__file__).parent / "web" / "index.html")


@app.get("/styles.css", include_in_schema=False)
def styles() -> FileResponse: return FileResponse(Path(__file__).parent / "web" / "styles.css", media_type="text/css")


@app.get("/observatory.css", include_in_schema=False)
def observatory_styles() -> FileResponse: return FileResponse(Path(__file__).parent / "web" / "observatory.css", media_type="text/css")


@app.get("/app.js", include_in_schema=False)
def javascript() -> FileResponse: return FileResponse(Path(__file__).parent / "web" / "app.js", media_type="application/javascript")


@app.get("/chart-ui.js", include_in_schema=False)
def chart_javascript() -> FileResponse: return FileResponse(Path(__file__).parent / "web" / "chart-ui.js", media_type="application/javascript")


@app.post("/api/v1/generator/generate")
def generator_generate(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    current_user(request)
    endpoint = os.getenv("DATA_GENERATOR_URL", "http://data-generator:8010").rstrip("/") + "/api/v1/generate"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        with urlopen(URLRequest(endpoint, data=body, headers={"Content-Type": "application/json"}), timeout=45) as response:
            return json.loads(response.read())
    except Exception as exc:
        raise HTTPException(502, f"Генератор недоступен: {exc}") from exc


@app.get("/api/v1/generator/download/{generation_id}")
def generator_download(generation_id: str, request: Request) -> StreamingResponse:
    current_user(request)
    endpoint = os.getenv("DATA_GENERATOR_URL", "http://data-generator:8010").rstrip("/") + "/api/v1/download/" + quote(generation_id, safe="")
    try:
        with urlopen(endpoint, timeout=45) as response:
            return StreamingResponse(iter([response.read()]), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=generated_dataset.zip"})
    except Exception as exc:
        raise HTTPException(502, f"Архив генератора недоступен: {exc}") from exc


@app.post("/api/v1/auth/register")
def register(payload: AuthIn) -> dict[str, Any]:
    username = payload.username.strip()
    if not re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9_.-]{3,32}", username):
        raise HTTPException(422, "username contains unsupported characters")
    con = db()
    if con.execute("SELECT value FROM settings WHERE key='registration_open'").fetchone()[0] != "1":
        con.close(); raise HTTPException(403, "registration is closed")
    if con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        con.close(); raise HTTPException(409, "username already exists")
    user_id = str(uuid.uuid4())
    con.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (user_id, username, hash_password(payload.password), 0, 0, datetime.utcnow().isoformat()))
    token = session_token(con, user_id); con.commit(); row = con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone(); con.close()
    return {"token": token, "user": public_user(row)}


@app.post("/api/v1/auth/login")
def login(payload: AuthIn) -> dict[str, Any]:
    con = db(); row = con.execute("SELECT * FROM users WHERE username=?", (payload.username.strip(),)).fetchone()
    if not row or not verify_password(payload.password, row["password_hash"]):
        con.close(); raise HTTPException(401, "invalid username or password")
    if row["is_blocked"]:
        con.close(); raise HTTPException(403, "account is blocked")
    token = session_token(con, row["user_id"]); con.commit(); con.close()
    return {"token": token, "user": public_user(row)}


@app.post("/api/v1/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    header = request.headers.get("authorization", ""); token = header[7:] if header.lower().startswith("bearer ") else request.headers.get("x-session-token", "")
    con = db(); con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)); con.commit(); con.close(); return {"ok": True}


@app.get("/api/v1/auth/me")
def me(request: Request) -> dict[str, Any]: return {"user": public_user(current_user(request))}


@app.get("/api/v1/chats")
def chats(request: Request) -> list[dict[str, Any]]:
    user = current_user(request); con = db(); rows = con.execute("SELECT chat_id, title, created_at, updated_at FROM chats WHERE user_id=? ORDER BY updated_at DESC", (user["user_id"],)).fetchall(); con.close(); return [dict(r) for r in rows]


@app.post("/api/v1/chats")
def create_chat(request: Request, title: str = "Новый чат") -> dict[str, Any]:
    user = current_user(request); now = datetime.utcnow().isoformat(); item = {"chat_id": str(uuid.uuid4()), "title": title[:80] or "Новый чат", "created_at": now, "updated_at": now}; con = db(); con.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (item["chat_id"], user["user_id"], item["title"], now, now)); con.commit(); con.close(); return item


@app.get("/api/v1/chats/{chat_id}/messages")
def chat_messages(request: Request, chat_id: str) -> list[dict[str, Any]]:
    user = current_user(request); con = db(); chat_for_user(con, chat_id, user["user_id"]); rows = con.execute("SELECT role, content, tool_calls, created_at FROM chat_messages WHERE chat_id=? ORDER BY created_at", (chat_id,)).fetchall(); con.close(); return [{**dict(r), "tool_calls": json.loads(r["tool_calls"] or "[]")} for r in rows]


@app.get("/api/v1/admin/settings")
def admin_settings(request: Request) -> dict[str, bool]:
    current_user(request, admin=True); con = db(); value = con.execute("SELECT value FROM settings WHERE key='registration_open'").fetchone()[0] == "1"; con.close(); return {"registration_open": value}


@app.put("/api/v1/admin/settings")
def admin_settings_update(payload: RegistrationSetting, request: Request) -> dict[str, bool]:
    current_user(request, admin=True); con = db(); con.execute("UPDATE settings SET value=? WHERE key='registration_open'", ("1" if payload.registration_open else "0",)); con.commit(); con.close(); return {"registration_open": payload.registration_open}


@app.get("/api/v1/admin/users")
def admin_users(request: Request) -> list[dict[str, Any]]:
    current_user(request, admin=True); con = db(); rows = con.execute("SELECT user_id, username, is_admin, is_blocked, created_at FROM users ORDER BY created_at").fetchall(); con.close(); return [public_user(r) for r in rows]


@app.patch("/api/v1/admin/users/{user_id}")
def admin_user_update(user_id: str, payload: UserPatch, request: Request) -> dict[str, Any]:
    admin = current_user(request, admin=True); con = db(); row = con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row: con.close(); raise HTTPException(404, "user not found")
    if user_id == admin["user_id"] and payload.is_blocked:
        con.close(); raise HTTPException(400, "cannot block current admin")
    if payload.is_blocked is not None: con.execute("UPDATE users SET is_blocked=? WHERE user_id=?", (int(payload.is_blocked), user_id))
    if payload.is_admin is not None: con.execute("UPDATE users SET is_admin=? WHERE user_id=?", (int(payload.is_admin), user_id))
    if payload.is_blocked: con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    con.commit(); row = con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone(); con.close(); return public_user(row)


@app.get("/api/v1/admin/chats")
def admin_chats(request: Request) -> list[dict[str, Any]]:
    current_user(request, admin=True); con = db(); rows = con.execute("SELECT c.chat_id, c.title, c.created_at, c.updated_at, u.username FROM chats c JOIN users u ON u.user_id=c.user_id ORDER BY c.updated_at DESC").fetchall(); con.close(); return [dict(r) for r in rows]


@app.get("/api/v1/admin/chats/{chat_id}/messages")
def admin_chat_messages(chat_id: str, request: Request) -> list[dict[str, Any]]:
    current_user(request, admin=True); con = db(); rows = con.execute("SELECT role, content, tool_calls, created_at FROM chat_messages WHERE chat_id=? ORDER BY created_at", (chat_id,)).fetchall(); con.close(); return [{**dict(r), "tool_calls": json.loads(r["tool_calls"] or "[]")} for r in rows]


@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    con = db(); con.execute("SELECT 1"); con.close(); return {"status": "ready"}


@app.get("/api/v1/agent/tools")
def agent_tools(request: Request) -> list[dict[str, Any]]:
    current_user(request)
    return [{"name": name, **spec} for name, spec in TOOL_REGISTRY.items()]


@app.get("/api/v1/batches")
def batches(request: Request, material_type: str | None = None) -> list[dict[str, Any]]:
    current_user(request)
    con = db(); rows = con.execute("SELECT * FROM batches" + (" WHERE material_type=?" if material_type else "") + " ORDER BY arrival_date, batch_id", (material_type,) if material_type else ()).fetchall(); con.close(); return [batch_dict(r) for r in rows]


@app.get("/api/v1/materials")
def materials_api(request: Request) -> list[dict[str, Any]]:
    current_user(request)
    rule_map, requirement_map = rules(), requirements_default()
    return [{"material_type": code, "rule": rule_map.get(code), "required_active_mass_kg": requirement_map.get(code, 0.0)} for code in material_codes()]


@app.post("/api/v1/batches")
def add_batch(item: BatchIn, request: Request) -> dict[str, Any]:
    current_user(request)
    valid, errors = validate_rows([item.model_dump(mode="json")]);
    if errors: raise HTTPException(422, errors)
    save_batches(valid); con = db(); row = con.execute("SELECT * FROM batches WHERE batch_id=?", (item.batch_id,)).fetchone(); con.close(); return batch_dict(row)


@app.get("/api/v1/batches/{batch_id}")
def get_batch(batch_id: str, request: Request) -> dict[str, Any]:
    current_user(request)
    return tool("get_batch_details", {"batch_id": batch_id})


@app.delete("/api/v1/batches/{batch_id}")
def delete_batch(batch_id: str, request: Request) -> dict[str, bool]:
    current_user(request)
    con = db(); cur = con.execute("DELETE FROM batches WHERE batch_id=?", (batch_id,));
    if cur.rowcount: bump_data_version(con)
    con.commit(); con.close();
    if not cur.rowcount: raise HTTPException(404, "batch not found")
    return {"deleted": True}


@app.delete("/api/v1/batches")
def clear_batches(request: Request) -> dict[str, int]:
    current_user(request, admin=True)
    con = db(); cur = con.execute("DELETE FROM batches"); deleted = cur.rowcount or 0
    bump_data_version(con); con.commit(); con.close()
    return {"deleted": deleted}


@app.get("/api/v1/quality-rules")
def get_rules(request: Request) -> list[dict[str, Any]]:
    current_user(request)
    return list(rules().values())


@app.put("/api/v1/quality-rules/{material_type}")
def put_rule(material_type: str, item: RuleIn, request: Request) -> dict[str, Any]:
    current_user(request)
    material_type = material_type.upper()
    if not MATERIAL_CODE.fullmatch(material_type) or item.rework_threshold_percent > item.good_threshold_percent: raise HTTPException(422, "invalid rule")
    con = db(); values = item.model_dump()
    con.execute("INSERT INTO quality_rules VALUES (?,?,?,?,?,?) ON CONFLICT(material_type) DO UPDATE SET good_threshold_percent=excluded.good_threshold_percent, rework_threshold_percent=excluded.rework_threshold_percent, good_recovery_factor=excluded.good_recovery_factor, rework_recovery_factor=excluded.rework_recovery_factor, reject_recovery_factor=excluded.reject_recovery_factor", (material_type, *values.values()))
    con.execute("INSERT INTO requirements VALUES (?,?) ON CONFLICT(material_type) DO NOTHING", (material_type, 0.0)); bump_data_version(con); con.commit(); con.close(); return {"material_type": material_type, **values}


@app.post("/api/v1/classifications/run")
def classify_api(request: Request, material_type: str | None = None) -> Any:
    current_user(request)
    return tool("classify_batches", {"material_type": material_type})


@app.get("/api/v1/inventory/summary")
def inventory(request: Request, material_type: str | None = None) -> Any:
    current_user(request)
    return tool("get_inventory_summary", {"material_type": material_type})


@app.post("/api/v1/imports/preview")
async def import_preview(request: Request, file: UploadFile = File(...)) -> Any:
    current_user(request)
    try: rows = parse_file(await file.read(), file.filename or "upload.csv"); valid, errors = validate_rows(rows); return {"valid_rows": len(valid), "invalid_rows": len(errors), "errors": errors, "rows": valid}
    except Exception as exc: raise HTTPException(400, str(exc))


class ImportCommit(BaseModel): rows: list[dict[str, Any]]


@app.post("/api/v1/imports/commit")
def import_commit(payload: ImportCommit, request: Request) -> dict[str, int]:
    current_user(request)
    valid, errors = validate_rows(payload.rows)
    if errors: raise HTTPException(422, {"errors": errors})
    return {"imported": save_batches(valid)}


@app.post("/api/v1/plans/preview")
def plan_preview(payload: RequirementIn, request: Request) -> Any:
    user = current_user(request); plan_id = str(uuid.uuid4()); plan = build_plan(payload.requirements, payload.policy, payload.allow_rework)
    con = db(); con.execute("INSERT INTO plan_owners(plan_id,user_id,status,created_at,preview_data_version) VALUES (?,?,?,?,?)", (plan_id, user["user_id"], "preview", datetime.utcnow().isoformat(), plan["meta"]["data_version"])); con.commit(); con.close()
    return {"plan_id": plan_id, **plan}


@app.post("/api/v1/plans/{plan_id}/confirm")
def plan_confirm(plan_id: str, payload: RequirementIn, request: Request) -> Any:
    user = current_user(request)
    con = db(); owner = con.execute("SELECT status, preview_data_version FROM plan_owners WHERE plan_id=? AND user_id=?", (plan_id, user["user_id"])).fetchone()
    if not owner: con.close(); raise HTTPException(404, "plan not found")
    if owner["status"] != "preview": con.close(); raise HTTPException(409, "plan already confirmed or cancelled")
    current_version_row = con.execute("SELECT value FROM settings WHERE key='data_version'").fetchone()
    current_version = int(current_version_row[0]) if current_version_row else 1
    if int(owner["preview_data_version"]) != current_version:
        con.close(); raise HTTPException(409, {"code": "STALE_PLAN", "message": "Складские остатки изменились. Пересчитайте план.", "preview_data_version": int(owner["preview_data_version"]), "current_data_version": current_version})
    existing = con.execute("SELECT status FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
    if existing: con.close(); raise HTTPException(409, "plan already confirmed or cancelled")
    plan = build_plan(payload.requirements, payload.policy, payload.allow_rework)
    try:
        con.execute("INSERT INTO plans VALUES (?,?,?,?)", (plan_id, "confirmed", json.dumps(plan), datetime.utcnow().isoformat()))
        for item in [i for m in plan["materials"].values() for i in m["items"]]:
            cur = con.execute("UPDATE batches SET remaining_raw_mass_kg=remaining_raw_mass_kg-? WHERE batch_id=? AND remaining_raw_mass_kg>=?", (item["raw_mass_used_kg"], item["batch_id"], item["raw_mass_used_kg"]))
            if cur.rowcount != 1: raise HTTPException(409, {"code": "STALE_PLAN", "message": "Складские остатки изменились. Пересчитайте план."})
        con.execute("UPDATE plan_owners SET status='confirmed' WHERE plan_id=? AND user_id=? AND status='preview'", (plan_id, user["user_id"]))
        bump_data_version(con); con.commit()
    except HTTPException:
        con.rollback(); con.close(); raise
    except Exception:
        con.rollback(); con.close(); raise
    con.close(); return {"plan_id": plan_id, "status": "confirmed", "plan": plan}


@app.post("/api/v1/plans/production/download")
def production_plan_download(payload: RequirementIn, request: Request) -> StreamingResponse:
    current_user(request)
    plan = build_plan(payload.requirements, PRODUCTION_POLICY, payload.allow_rework)
    fields, rows = production_plan_csv_rows(plan)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    filename = f'production-weekly-plan-{datetime.utcnow().date().isoformat()}.csv'
    return StreamingResponse(iter([output.getvalue().encode("utf-8-sig")]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/v1/policies/compare")
def compare(payload: RequirementIn, request: Request) -> Any:
    current_user(request)
    return tool("compare_allocation_policies", {"requirements": payload.requirements, "policies": POLICIES})


@app.post("/api/v1/scenarios/simulate")
def simulate(payload: dict[str, Any], request: Request) -> Any:
    current_user(request)
    return tool("simulate_requirement_change", payload)


@app.post("/api/v1/agent/chat")
def chat(payload: ChatIn, request: Request) -> Any:
    user = current_user(request)
    con = db()
    if payload.chat_id:
        chat_row = chat_for_user(con, payload.chat_id, user["user_id"])
        chat_id = chat_row["chat_id"]
    else:
        chat_id = str(uuid.uuid4()); now = datetime.utcnow().isoformat(); title = payload.message.strip()[:80]
        con.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (chat_id, user["user_id"], title or "Новый чат", now, now))
    previous = con.execute("SELECT role, content FROM chat_messages WHERE chat_id=? ORDER BY created_at DESC LIMIT 12", (chat_id,)).fetchall()
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(previous)] or payload.history
    save_message(con, chat_id, "user", payload.message)
    con.execute("UPDATE chats SET title=? WHERE chat_id=? AND title='Новый чат'", (payload.message.strip()[:80] or "Новый чат", chat_id)); con.commit(); con.close()
    try:
        normalized = payload.message.lower(); explanation = explanation_tool_for_message(payload.message)
        intent = route_intent(payload.message, history)
        if intent["intent"] == "CLARIFY":
            answer = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": clarification_text(intent), "question": clarification_text(intent), "needs_clarification": True, "choices": intent.get("choices", []), "choice_flow": intent.get("choice_flow"), "tool_calls": []}
            con = db(); save_message(con, chat_id, answer["answer"]); con.commit(); con.close(); return answer
        if any(x in normalized for x in ("проверь партию", "карточк* партии")) and not re.search(r"\b[a-z][a-z0-9_-]{0,15}-\d+\b", normalized) and "сам" not in normalized and not explanation:
            con = db(); choices = [r[0] for r in con.execute("SELECT batch_id FROM batches ORDER BY arrival_date, batch_id LIMIT 20")]; con.close()
            answer = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": "Какую партию проверить?", "question": "Какую партию проверить?", "needs_clarification": True, "choices": choices, "tool_calls": []}
            con = db(); save_message(con, chat_id, "assistant", answer["answer"]); con.commit(); con.close(); return answer
        if any(x in normalized for x in ("отчет по браку", "отчёт по браку", "покажи брак")) and not any(word in normalized for word in ("график", "диаграмм", "визуализ")) and not any(m.lower() in normalized for m in material_codes()) and "все" not in normalized and not explanation:
            answer = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": "По какому материалу сформировать отчёт?", "question": "По какому материалу сформировать отчёт?", "needs_clarification": True, "choices": material_choices("Покажи отчёт по браку"), "tool_calls": []}
            con = db(); save_message(con, chat_id, "assistant", answer["answer"]); con.commit(); con.close(); return answer
        material = requested_material(payload.message)
        plan_request = any(word in normalized for word in ("недельный план", "составь план", "план производства", "построй план")) and not explanation
        if plan_request:
            supplied = parse_requirements(payload.message); missing = [m for m in MATERIALS if m not in supplied]
            if missing:
                answer = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": f"Чтобы построить недельный план, укажите потребность по активному веществу для {', '.join(missing)}. Например: A 3000, B 3000, C 3000.", "needs_clarification": True, "choices": [], "tool_calls": []}
                con = db(); save_message(con, chat_id, "assistant", answer["answer"]); con.commit(); con.close(); return answer
        if any(word in normalized for word in ("остат", "склад", "запас")) and intent["intent"] != "EXECUTE_TOOL" and not material and "все" not in normalized and "всем" not in normalized and not explanation:
            answer = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": "По какому материалу показать остатки?", "question": "По какому материалу показать остатки?", "needs_clarification": True, "choices": material_choices("Покажи остатки"), "tool_calls": []}
            con = db(); save_message(con, chat_id, "assistant", answer["answer"]); con.commit(); con.close(); return answer
        name, answer, data, trace = llm_agent(payload.message, history)
        trace = trace_with_result(trace, data)
        response = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "llm" if name == "llm" else "offline", "answer": answer, "tool": trace[-1]["tool"] if trace else None, "tool_calls": trace, "result": data}
        con = db(); save_message(con, chat_id, "assistant", answer, trace); con.commit(); con.close(); return response
    except Exception as exc:
        con = db(); save_message(con, chat_id, "assistant", f"Не удалось выполнить запрос: {exc}"); con.commit(); con.close(); raise HTTPException(502, str(exc))


@app.post("/api/v1/agent/chat/stream")
def chat_stream(payload: ChatIn, request: Request) -> StreamingResponse:
    user = current_user(request)
    con = db()
    if payload.chat_id:
        chat_id = chat_for_user(con, payload.chat_id, user["user_id"])["chat_id"]
    else:
        chat_id = str(uuid.uuid4()); now = datetime.utcnow().isoformat(); title = payload.message.strip()[:80]
        con.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (chat_id, user["user_id"], title or "Новый чат", now, now))
    previous = con.execute("SELECT role, content FROM chat_messages WHERE chat_id=? ORDER BY created_at DESC LIMIT 12", (chat_id,)).fetchall()
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(previous)] or payload.history
    save_message(con, chat_id, "user", payload.message)
    con.execute("UPDATE chats SET title=? WHERE chat_id=? AND title='Новый чат'", (payload.message.strip()[:80] or "Новый чат", chat_id)); con.commit(); con.close()

    def events():
        response: dict[str, Any] | None = None
        try:
            normalized = payload.message.lower(); explanation = explanation_tool_for_message(payload.message)
            intent = route_intent(payload.message, history)
            if intent["intent"] == "CLARIFY":
                answer = clarification_text(intent)
                response = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": answer, "question": answer, "needs_clarification": True, "choices": intent.get("choices", []), "choice_flow": intent.get("choice_flow"), "tool_calls": []}
                yield sse_event({"type": "token", "text": answer})
            elif any(x in normalized for x in ("проверь партию", "карточк* партии")) and not re.search(r"\b[a-z][a-z0-9_-]{0,15}-\d+\b", normalized) and "сам" not in normalized and not explanation:
                con = db(); choices = [r[0] for r in con.execute("SELECT batch_id FROM batches ORDER BY arrival_date, batch_id LIMIT 20")]; con.close()
                response = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": "Какую партию проверить?", "question": "Какую партию проверить?", "needs_clarification": True, "choices": choices, "tool_calls": []}
                yield sse_event({"type": "token", "text": response["answer"]})
            elif any(x in normalized for x in ("отчет по браку", "отчёт по браку", "покажи брак")) and not any(word in normalized for word in ("график", "диаграмм", "визуализ")) and not any(m.lower() in normalized for m in material_codes()) and "все" not in normalized and not explanation:
                response = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": "По какому материалу сформировать отчёт?", "question": "По какому материалу сформировать отчёт?", "needs_clarification": True, "choices": material_choices("Покажи отчёт по браку"), "tool_calls": []}
                yield sse_event({"type": "token", "text": response["answer"]})
            elif any(word in normalized for word in ("недельный план", "составь план", "план производства", "построй план")) and not explanation and set(parse_requirements(payload.message)) != set(MATERIALS):
                missing = [m for m in MATERIALS if m not in parse_requirements(payload.message)]
                response = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": f"Чтобы построить недельный план, укажите потребность по активному веществу для {', '.join(missing)}. Например: A 3000, B 3000, C 3000.", "needs_clarification": True, "choices": [], "tool_calls": []}
                yield sse_event({"type": "token", "text": response["answer"]})
            elif any(word in normalized for word in ("остат", "склад", "запас")) and intent["intent"] != "EXECUTE_TOOL" and not requested_material(payload.message) and "все" not in normalized and "всем" not in normalized and not explanation:
                response = {"run_id": str(uuid.uuid4()), "chat_id": chat_id, "mode": "assistant", "answer": "По какому материалу показать остатки?", "question": "По какому материалу показать остатки?", "needs_clarification": True, "choices": material_choices("Покажи остатки"), "tool_calls": []}
                yield sse_event({"type": "token", "text": response["answer"]})
            else:
                yield sse_event({"type": "status", "text": "Запрашиваю расчёт…"})
                for item in llm_agent_stream(payload.message, history):
                    if item.get("type") == "done":
                        response = item["response"]; response.update({"run_id": str(uuid.uuid4()), "chat_id": chat_id})
                    else:
                        yield sse_event(item)
            if response:
                response["tool_calls"] = trace_with_result(response.get("tool_calls", []), response.get("result"))
                con = db(); save_message(con, chat_id, "assistant", response["answer"], response["tool_calls"]); con.commit(); con.close()
                yield sse_event({"type": "done", "response": response})
        except Exception as exc:
            try:
                con = db(); save_message(con, chat_id, "assistant", f"Не удалось выполнить запрос: {exc}"); con.commit(); con.close()
            except Exception:
                pass
            yield sse_event({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@app.get("/api/v1/reports/rejections")
def rejection_report(request: Request, material_type: str | None = None) -> Any:
    current_user(request)
    return tool("generate_rejection_report", {"material_type": material_type})


@app.get("/api/v1/reports/{report_id}/download")
def report_download(report_id: str, request: Request, material_type: str | None = None) -> StreamingResponse:
    current_user(request)
    report = tool("generate_rejection_report", {"material_type": material_type}); rows = report["batches"]; output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=["batch_id", "material_type", "concentration_percent", "status", "remaining_raw_mass_kg"]); writer.writeheader(); writer.writerows({k: r.get(k) if k != "status" else r["quality"]["status"] for k in writer.fieldnames} for r in rows); return StreamingResponse(iter([output.getvalue().encode("utf-8-sig")]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="rejection-{report_id}.csv"'})


@app.get("/api/v1/requirements")
def get_requirements(request: Request) -> dict[str, float]:
    current_user(request)
    return requirements_default()


@app.put("/api/v1/requirements")
def put_requirements(payload: dict[str, float], request: Request) -> dict[str, float]:
    current_user(request)
    con = db();
    for material, value in payload.items():
        material = material.upper()
        if not MATERIAL_CODE.fullmatch(material) or value < 0: raise HTTPException(422, "invalid requirement")
        ensure_materials(con, {material})
        con.execute("INSERT INTO requirements VALUES (?,?) ON CONFLICT(material_type) DO UPDATE SET required_active_mass_kg=excluded.required_active_mass_kg", (material, value))
    bump_data_version(con); con.commit(); con.close(); return requirements_default()
