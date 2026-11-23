"""Tests for the chat API. They use fakes, so no Azure account is needed."""

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import REFUSAL, create_app
from app.memory import InMemoryMemoryStore
from app.model_client import (
    ContentBlockedError,
    FakeModelClient,
    ModelBusyError,
    ModelReply,
    ModelUnavailableError,
)

SESSION = "3f2b8c1e-1111-4a2b-9c3d-123456789abc"


class RaisingModel:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def reply(self, history, message):
        raise self.error


class BrokenMemory:
    def save_message(self, session_id, role, content):
        raise ConnectionError("cosmos down")

    def load_recent(self, session_id, limit):
        raise ConnectionError("cosmos down")


class RecordingModel:
    def __init__(self) -> None:
        self.seen_history = None

    def reply(self, history, message):
        self.seen_history = history
        return ModelReply("ok", 5)


def make_client(memory=None, model=None) -> TestClient:
    app = create_app(
        settings=load_settings(),
        memory=memory or InMemoryMemoryStore(),
        model=model or FakeModelClient(),
    )
    return TestClient(app)


def test_health():
    response = make_client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_reply():
    response = make_client().post("/chat", json={"sessionId": SESSION, "message": "Hi"})
    assert response.status_code == 200
    assert "Hi" in response.json()["reply"]


def test_memory_remembers_name():
    client = make_client()
    client.post("/chat", json={"sessionId": SESSION, "message": "My name is Sam"})
    response = client.post("/chat", json={"sessionId": SESSION, "message": "What is my name?"})
    assert "Sam" in response.json()["reply"]


def test_sessions_are_separate():
    client = make_client()
    client.post("/chat", json={"sessionId": SESSION, "message": "My name is Sam"})
    response = client.post(
        "/chat", json={"sessionId": "other-session", "message": "What is my name?"}
    )
    assert "Sam" not in response.json()["reply"]


def test_only_last_10_messages_are_sent_to_model():
    memory = InMemoryMemoryStore()
    for i in range(12):
        memory.save_message(SESSION, "user", f"message {i}")
    model = RecordingModel()
    make_client(memory=memory, model=model).post(
        "/chat", json={"sessionId": SESSION, "message": "hello"}
    )
    assert len(model.seen_history) == 10
    assert model.seen_history[-1]["content"] == "message 11"


def test_history_endpoint_returns_saved_messages():
    client = make_client()
    client.post("/chat", json={"sessionId": SESSION, "message": "Hello there"})
    data = client.get(f"/history/{SESSION}").json()
    assert [m["role"] for m in data["messages"]] == ["user", "assistant"]


@pytest.mark.parametrize("message", ["", "   ", "x" * 2001])
def test_bad_input_returns_400(message):
    response = make_client().post("/chat", json={"sessionId": SESSION, "message": message})
    assert response.status_code == 400


def test_bad_session_id_returns_400():
    response = make_client().post("/chat", json={"sessionId": "bad id!", "message": "hi"})
    assert response.status_code == 400


def test_model_unavailable_returns_503():
    client = make_client(model=RaisingModel(ModelUnavailableError()))
    response = client.post("/chat", json={"sessionId": SESSION, "message": "hi"})
    assert response.status_code == 503


def test_rate_limited_returns_429():
    client = make_client(model=RaisingModel(ModelBusyError()))
    response = client.post("/chat", json={"sessionId": SESSION, "message": "hi"})
    assert response.status_code == 429


def test_content_filter_returns_polite_refusal():
    client = make_client(model=RaisingModel(ContentBlockedError()))
    response = client.post("/chat", json={"sessionId": SESSION, "message": "hi"})
    assert response.status_code == 200
    assert response.json()["reply"] == REFUSAL


def test_memory_down_still_answers():
    client = make_client(memory=BrokenMemory())
    response = client.post("/chat", json={"sessionId": SESSION, "message": "Hi"})
    assert response.status_code == 200


def test_cosmos_store_does_not_connect_at_startup():
    from app.memory import CosmosMemoryStore

    # Creating the store must not contact Azure; it connects on first use.
    store = CosmosMemoryStore("https://unreachable.invalid:443/", "chatbot", "messages")
    assert store._container is None
