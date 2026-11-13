
from app import api


def test_sessions_have_unique_ids(client):
    first = client.post("/game/start").json()
    second = client.post("/game/start").json()

    assert first["session_id"] != second["session_id"]


def test_sessions_are_independent(client):
    first = client.post("/game/start").json()
    second = client.post("/game/start").json()

    first_id = first["session_id"]
    second_id = second["session_id"]

    api.sessions[first_id]["attempts_left"] = 2

    assert api.sessions[second_id]["attempts_left"] == api.MAX_ATTEMPTS


def test_each_session_has_independent_history(client):
    first = client.post("/game/start").json()
    second = client.post("/game/start").json()

    first_id = first["session_id"]
    second_id = second["session_id"]

    api.sessions[first_id]["history_by_level"][1].append("test message")

    assert api.sessions[second_id]["history_by_level"][1] == []


def test_each_session_has_independent_secrets(client):
    first = client.post("/game/start").json()
    second = client.post("/game/start").json()

    first_id = first["session_id"]
    second_id = second["session_id"]

    api.sessions[first_id]["secrets"][1] = "CHANGED_SECRET"

    assert api.sessions[second_id]["secrets"][1] == "TEST_SECRET_LEVEL_1"


def test_new_session_has_initial_counters(client, started_session):
    session_id = started_session["session_id"]
    session = api.sessions[session_id]

    assert session["current_level"] == 1
    assert session["attempts_left"] == api.MAX_ATTEMPTS
    assert session["messages_left"] == api.MAX_MESSAGES
    assert session["tokens_left"] == api.MAX_TOKENS_LIMIT
    assert session["messages_sent"] == 0
    assert session["completed"] is False
