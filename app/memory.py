"""Chat history storage.

Two implementations share one interface:
- CosmosMemoryStore: the real one, used in Azure.
- InMemoryMemoryStore: keeps messages in a Python list, used by tests and local runs.
"""

import uuid
from datetime import datetime, timezone
from typing import Protocol


class MemoryStore(Protocol):
    def save_message(self, session_id: str, role: str, content: str) -> None: ...

    def load_recent(self, session_id: str, limit: int) -> list[dict]: ...


def _now() -> str:
    # Microseconds keep messages in the right order even when saved quickly.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._items: list[dict] = []

    def save_message(self, session_id: str, role: str, content: str) -> None:
        self._items.append(
            {
                "id": str(uuid.uuid4()),
                "sessionId": session_id,
                "role": role,
                "content": content,
                "createdAt": _now(),
            }
        )

    def load_recent(self, session_id: str, limit: int) -> list[dict]:
        mine = [i for i in self._items if i["sessionId"] == session_id]
        return [{"role": i["role"], "content": i["content"]} for i in mine[-limit:]]


class CosmosMemoryStore:
    def __init__(self, endpoint: str, database: str, container: str) -> None:
        self._endpoint = endpoint
        self._database = database
        self._container_name = container
        self._container = None

    def _get_container(self):
        # Connect on first use, not at startup. The Cosmos client contacts the
        # account as soon as it is created, so connecting lazily lets the API
        # start (and answer without memory) even when Cosmos DB is unreachable.
        if self._container is None:
            from azure.cosmos import CosmosClient
            from azure.identity import DefaultAzureCredential

            client = CosmosClient(self._endpoint, credential=DefaultAzureCredential())
            self._container = client.get_database_client(self._database).get_container_client(
                self._container_name
            )
        return self._container

    def save_message(self, session_id: str, role: str, content: str) -> None:
        self._get_container().create_item(
            {
                "id": str(uuid.uuid4()),
                "sessionId": session_id,
                "role": role,
                "content": content,
                "createdAt": _now(),
            }
        )

    def load_recent(self, session_id: str, limit: int) -> list[dict]:
        query = (
            "SELECT c.role, c.content, c.createdAt FROM c "
            "WHERE c.sessionId = @sid ORDER BY c.createdAt DESC "
            "OFFSET 0 LIMIT @limit"
        )
        items = list(
            self._get_container().query_items(
                query=query,
                parameters=[
                    {"name": "@sid", "value": session_id},
                    {"name": "@limit", "value": limit},
                ],
                partition_key=session_id,
            )
        )
        items.reverse()  # oldest first, the order the model expects
        return [{"role": i["role"], "content": i["content"]} for i in items]
