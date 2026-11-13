
import os

# Prevent the application from failing during import.
# Tests will mock all model calls.
os.environ.setdefault("LLM_API_KEY", "test-key-not-used")

import pytest
from fastapi.testclient import TestClient

from app import api


@pytest.fixture
def client(monkeypatch):
    """Provide a clean API client and isolated game sessions."""

    api.sessions.clear()

    monkeypatch.setattr(
        api,
        "generate_session_secrets",
        lambda: {
            1: "TEST_SECRET_LEVEL_1",
            2: "TEST_SECRET_LEVEL_2",
            3: "TEST_SECRET_LEVEL_3",
        },
    )

    with TestClient(api.app) as test_client:
        yield test_client

    api.sessions.clear()


@pytest.fixture
def started_session(client):
    """Create a new game session for a test."""

    response = client.post("/game/start")
    assert response.status_code == 200

    return response.json()
