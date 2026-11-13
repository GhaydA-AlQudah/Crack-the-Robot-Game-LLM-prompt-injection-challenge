def test_chat_accepts_empty_message_with_mock(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    async def fake_run_level_agent(
        level,
        message,
        history=None,
        on_tool_called=None,
        session_secrets=None,
    ):
        assert message == ""

        return (
            "Mock response",
            [],
            {
                "input_tokens": 1,
                "output_tokens": 2,
                "total_tokens": 3,
            },
        )

    monkeypatch.setattr(
        api,
        "run_level_agent",
        fake_run_level_agent,
    )

    response = client.post(
        "/game/chat",
        json={
            "session_id": started_session["session_id"],
            "message": "",
        },
    )

    assert response.status_code == 200


import pytest


def test_chat_rejects_unknown_session(client):
    response = client.post(
        "/game/chat",
        json={
            "session_id": "unknown-session",
            "message": "Hello",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


def test_chat_rejects_completed_game(client, started_session):
    from app import api

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


def test_chat_rejects_message_limit(client, started_session):
    from app import api

    session_id = started_session["session_id"]
    api.sessions[session_id]["messages_left"] = 0

    response = client.post(
        "/game/chat",
        json={
            "session_id": session_id,
            "message": "Hello",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Message limit reached for this level."


def test_chat_rejects_token_limit(client, started_session):
    from app import api

    session_id = started_session["session_id"]
    api.sessions[session_id]["tokens_left"] = 0

    response = client.post(
        "/game/chat",
        json={
            "session_id": session_id,
            "message": "Hello",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Token limit reached for this level."


def test_chat_handles_value_error_from_agent(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    async def fake_run_level_agent(**kwargs):
        raise ValueError("Invalid level")

    monkeypatch.setattr(api, "run_level_agent", fake_run_level_agent)

    response = client.post(
        "/game/chat",
        json={
            "session_id": started_session["session_id"],
            "message": "Hello",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid level"


def test_chat_reraises_agent_exception(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    async def fake_run_level_agent(**kwargs):
        raise RuntimeError("Agent failed")

    monkeypatch.setattr(api, "run_level_agent", fake_run_level_agent)

    with pytest.raises(RuntimeError, match="Agent failed"):
        client.post(
            "/game/chat",
            json={
                "session_id": started_session["session_id"],
                "message": "Hello",
            },
        )


def test_chat_tracks_authorized_tool_call(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    session_id = started_session["session_id"]

    async def fake_run_level_agent(
        level,
        message,
        history=None,
        on_tool_called=None,
        session_secrets=None,
    ):
        on_tool_called(True, True)

        return (
            "Tool executed",
            [],
            {
                "input_tokens": 2,
                "output_tokens": 3,
                "total_tokens": 5,
            },
        )

    monkeypatch.setattr(api, "run_level_agent", fake_run_level_agent)

    response = client.post(
        "/game/chat",
        json={
            "session_id": session_id,
            "message": "Call the tool",
        },
    )

    session = api.sessions[session_id]

    assert response.status_code == 200
    assert session["tool_called"] is True
    assert session["authorization"] is True
    assert session["model_authorization"] is True
    assert session["model_authorization_true_seen"] is True
    assert session["tool_calls_this_response"] == 1
    assert session["authorization_true_tool_calls_this_response"] == 1
    assert session["tool_calls_by_level"][1] == 1
    assert session["authorization_true_tool_calls_by_level"][1] == 1
    assert session["response_turns_by_level"][1] == 1
    assert session["no_tool_call_responses_by_level"][1] == 0


def test_chat_tracks_response_without_tool_call(
    client,
    started_session,
    monkeypatch,
):
    from app import api

    session_id = started_session["session_id"]

    async def fake_run_level_agent(**kwargs):
        return (
            "Normal response",
            [],
            {
                "input_tokens": 1,
                "output_tokens": 2,
                "total_tokens": 3,
            },
        )

    monkeypatch.setattr(api, "run_level_agent", fake_run_level_agent)

    response = client.post(
        "/game/chat",
        json={
            "session_id": session_id,
            "message": "Hello",
        },
    )

    session = api.sessions[session_id]

    assert response.status_code == 200
    assert session["response_turns_by_level"][1] == 1
    assert session["tool_calls_by_level"][1] == 0
    assert session["no_tool_call_responses_by_level"][1] == 1
