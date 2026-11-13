
from app import api


def test_correct_secret_unlocks_next_level(
    client,
    started_session,
    monkeypatch,
):
    session_id = started_session["session_id"]

    api.sessions[session_id]["tool_called"] = True
    api.sessions[session_id]["authorization"] = True

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "CORRECT_SECRET",
    )

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "CORRECT_SECRET",
        },
    )

    data = response.json()

    assert response.status_code == 200
    assert data["success"] is True
    assert data["completed"] is False
    assert data["current_level"] == 2
    assert data["attempts_left"] == api.MAX_ATTEMPTS
    assert data["messages_left"] == api.MAX_MESSAGES
    assert data["tokens_left"] == api.MAX_TOKENS_LIMIT


def test_wrong_secret_reduces_attempts(
    client,
    started_session,
    monkeypatch,
):
    session_id = started_session["session_id"]

    api.sessions[session_id]["tool_called"] = True
    api.sessions[session_id]["authorization"] = True

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "CORRECT_SECRET",
    )

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "WRONG_SECRET",
        },
    )

    data = response.json()

    assert response.status_code == 200
    assert data["success"] is False
    assert data["attempts_left"] == api.MAX_ATTEMPTS - 1
    assert data["current_level"] == 1


def test_level_3_completes_game(
    client,
    started_session,
    monkeypatch,
):
    session_id = started_session["session_id"]

    session = api.sessions[session_id]
    session["current_level"] = 3
    session["messages_sent"] = 3

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "LEVEL_3_SECRET",
    )
    monkeypatch.setattr(
        api,
        "load_level_secret",
        lambda level: "LEVEL_3_SECRET",
    )

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "LEVEL_3_SECRET",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["completed"] is True

    assert session["completed"] is True


def test_no_attempts_left_blocks_submission(
    client,
    started_session,
    monkeypatch,
):
    session_id = started_session["session_id"]

    session = api.sessions[session_id]
    session["tool_called"] = True
    session["authorization"] = True
    session["attempts_left"] = 0

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "CORRECT_SECRET",
    )

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "CORRECT_SECRET",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No attempts left"


def test_completed_game_rejects_chat(
    client,
    started_session,
):
    session_id = started_session["session_id"]
    api.sessions[session_id]["completed"] = True

    response = client.post(
        "/game/chat",
        json={
            "session_id": session_id,
            "message": "Hello",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already completed"
