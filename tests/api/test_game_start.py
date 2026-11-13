
def test_start_game(client):
    response = client.post("/game/start")

    assert response.status_code == 200

    data = response.json()

    assert data["session_id"]
    assert data["current_level"] == 1
    assert data["attempts_left"] == 5
    assert data["messages_left"] == 15
    assert data["tokens_left"] == 1000


def test_start_game_creates_session(client):
    response = client.post("/game/start")
    session_id = response.json()["session_id"]

    from app import api

    assert session_id in api.sessions


def test_start_game_returns_unique_session_ids(client):
    first = client.post("/game/start").json()
    second = client.post("/game/start").json()

    assert first["session_id"] != second["session_id"]


def test_start_game_initializes_all_level_histories(
    client,
    started_session,
):
    from app import api

    session_id = started_session["session_id"]
    session = api.sessions[session_id]

    assert set(session["history_by_level"].keys()) == {1, 2, 3}

    for history in session["history_by_level"].values():
        assert history == []


def test_start_game_initializes_evaluation_counters(
    client,
    started_session,
):
    from app import api

    session = api.sessions[started_session["session_id"]]

    assert session["tool_calls_by_level"] == {1: 0, 2: 0, 3: 0}
    assert session["response_turns_by_level"] == {1: 0, 2: 0, 3: 0}
    assert session["no_tool_call_responses_by_level"] == {
        1: 0,
        2: 0,
        3: 0,
    }
