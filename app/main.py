"""The chat API: POST /chat, GET /history/{session_id}, GET /health."""

import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import Settings, load_settings
from app.memory import CosmosMemoryStore, InMemoryMemoryStore, MemoryStore
from app.model_client import (
    ContentBlockedError,
    FakeModelClient,
    FoundryModelClient,
    ModelBusyError,
    ModelClient,
    ModelUnavailableError,
)
from app.telemetry import logger, record_tokens, setup_telemetry

SESSION_PATTERN = r"^[A-Za-z0-9-]{1,64}$"
REFUSAL = "Sorry, I can't help with that request."


class ChatRequest(BaseModel):
    sessionId: str = Field(pattern=SESSION_PATTERN)
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str


def create_app(
    settings: Settings | None = None,
    memory: MemoryStore | None = None,
    model: ModelClient | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    setup_telemetry(settings.appinsights_connection_string)

    if memory is None:
        memory = (
            InMemoryMemoryStore()
            if settings.use_fakes
            else CosmosMemoryStore(
                settings.cosmos_endpoint,
                settings.cosmos_database,
                settings.cosmos_container,
            )
        )
    if model is None:
        model = (
            FakeModelClient()
            if settings.use_fakes
            else FoundryModelClient(settings.openai_base_url, settings.model_deployment)
        )

    app = FastAPI(title="AI Chatbot with Memory")

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.exception_handler(RequestValidationError)
    async def bad_input(_: Request, exc: RequestValidationError) -> JSONResponse:
        # The design asks for 400 (not FastAPI's default 422) on bad input.
        return JSONResponse(status_code=400, content={"error": "Invalid input."})

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/history/{session_id}")
    def history(session_id: str):
        if not re.match(SESSION_PATTERN, session_id):
            return JSONResponse(status_code=400, content={"error": "Invalid input."})
        try:
            return {"messages": memory.load_recent(session_id, 50)}
        except Exception:
            logger.warning("Could not load history from the memory store.")
            return {"messages": []}

    @app.post("/chat", response_model=ChatResponse)
    def chat(body: ChatRequest):
        text = body.message.strip()
        if not text:
            return JSONResponse(status_code=400, content={"error": "Invalid input."})

        try:
            past = memory.load_recent(body.sessionId, settings.history_limit)
        except Exception:
            logger.warning("Memory store unreachable; answering without history.")
            past = []

        try:
            result = model.reply(past, text)
        except ModelBusyError:
            return JSONResponse(status_code=429, content={"error": "Busy, try again in a moment."})
        except ContentBlockedError:
            logger.warning("Content filter blocked a message.")
            return ChatResponse(reply=REFUSAL)
        except ModelUnavailableError:
            return JSONResponse(status_code=503, content={"error": "Model unavailable, try again."})

        record_tokens(result.total_tokens)
        try:
            memory.save_message(body.sessionId, "user", text)
            memory.save_message(body.sessionId, "assistant", result.text)
        except Exception:
            logger.warning("Could not save messages to the memory store.")

        return ChatResponse(reply=result.text)

    return app


app = create_app()
