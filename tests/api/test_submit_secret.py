
def test_submit_secret_rejects_unknown_session(client):
    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": "unknown-session",
            "secret": "ANY_SECRET",
        },
    )

    assert response.status_code == 404


def test_secret_cannot_be_submitted_before_tool_call(
    client,
    started_session,
):
    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": started_session["session_id"],
            "secret": "ANY_SECRET",
        },
    )

    assert response.status_code == 400


def test_wrong_secret_reduces_attempts(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    session_id = started_session["session_id"]

    api.sessions[session_id]["tool_called"] = True
    api.sessions[session_id]["authorization"] = True

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "REAL_SECRET",
    )

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "WRONG_SECRET",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["attempts_left"] == 4


def test_correct_secret_unlocks_next_level(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    session_id = started_session["session_id"]

    api.sessions[session_id]["tool_called"] = True
    api.sessions[session_id]["authorization"] = True

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "REAL_SECRET",
    )

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "real_secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["current_level"] == 2


def test_submit_secret_rejects_invalid_request(client):
    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": "some-session",
        },
    )

    assert response.status_code == 422


def test_submit_secret_rejects_completed_game(
    client,
    started_session,
):
    from app import api

    session_id = started_session["session_id"]
    api.sessions[session_id]["completed"] = True

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "ANY_SECRET",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already completed"


def test_secret_submission_is_case_insensitive(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    session_id = started_session["session_id"]

    api.sessions[session_id]["tool_called"] = True
    api.sessions[session_id]["authorization"] = True

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "MY_SECRET",
    )

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "my_secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True



def test_submit_secret_rejects_unauthorized_tool(
    client,
    started_session,
):
    from app import api

    session_id = started_session["session_id"]
    api.sessions[session_id]["tool_called"] = True
    api.sessions[session_id]["authorization"] = False

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "ANY_SECRET",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "The tool has not been authorized."


def test_submit_secret_rejects_when_no_attempts_left(
    client,
    started_session,
):
    from app import api

    session_id = started_session["session_id"]
    session = api.sessions[session_id]

    session["tool_called"] = True
    session["authorization"] = True
    session["attempts_left"] = 0

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "ANY_SECRET",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No attempts left"


def test_level_three_requires_three_messages(
    client,
    started_session,
):
    from app import api

    session_id = started_session["session_id"]
    session = api.sessions[session_id]

    session["current_level"] = 3
    session["messages_sent"] = 2

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "ANY_SECRET",
        },
    )

    assert response.status_code == 400
    assert "at least 3 messages" in response.json()["detail"]


def test_level_three_completes_game_with_fixed_secret(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    session_id = started_session["session_id"]
    session = api.sessions[session_id]

    session["current_level"] = 3
    session["messages_sent"] = 3

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "GENERATED_SECRET",
    )

    fixed_secret = api.load_level_secret(3)

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": fixed_secret,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["completed"] is True
    assert response.json()["message"] == "Challenge completed!"
    assert session["completed"] is True


def test_level_three_accepts_generated_secret(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    session_id = started_session["session_id"]
    session = api.sessions[session_id]

    session["current_level"] = 3
    session["messages_sent"] = 3

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "GENERATED_SECRET",
    )

    monkeypatch.setattr(
        api,
        "load_level_secret",
        lambda level: "FIXED_SECRET",
    )

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "GENERATED_SECRET",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["completed"] is True
    assert session["completed"] is True


def test_level_three_rejects_wrong_secret(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    session_id = started_session["session_id"]
    session = api.sessions[session_id]

    session["current_level"] = 3
    session["messages_sent"] = 3

    monkeypatch.setattr(
        api,
        "extract_flag",
        lambda level, secrets: "GENERATED_SECRET",
    )

    monkeypatch.setattr(
        api,
        "load_level_secret",
        lambda level: "FIXED_SECRET",
    )

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "WRONG_SECRET",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["attempts_left"] == 4
    assert session["completed"] is False
