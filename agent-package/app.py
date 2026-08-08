from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_core import AgentService, HttpToolGateway

app = FastAPI(title="Raw Material Agent")
gateway = HttpToolGateway(os.getenv("BACKEND_URL", "http://localhost:8000"), os.getenv("AGENT_SERVICE_TOKEN", ""))
agent = AgentService(gateway)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)


def authorized(token: str | None) -> None:
    expected = os.getenv("AGENT_API_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(401, "invalid agent token")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat")
def chat(payload: ChatRequest, x_agent_api_token: str | None = Header(default=None)) -> dict[str, Any]:
    authorized(x_agent_api_token)
    return agent.handle(payload.message, payload.history)


@app.post("/v1/chat/stream")
def chat_stream(payload: ChatRequest, x_agent_api_token: str | None = Header(default=None)) -> StreamingResponse:
    authorized(x_agent_api_token)

    def events():
        yield "data: " + json.dumps({"type": "status", "text": "Анализирую запрос"}, ensure_ascii=False) + "\n\n"
        try:
            for event in agent.stream(payload.message, payload.history):
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        except Exception as exc:
            yield "data: " + json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
