
import pytest

from app import llm
from app.llm import (
    LevelContext,
    game_agents,
    get_agent,
)

from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel


def test_all_level_agents_are_initialized():
    assert set(game_agents.keys()) == {1, 2, 3}


def test_each_level_has_an_agent():
    for level in (1, 2, 3):
        assert game_agents[level] is not None


def test_get_agent_creates_agent_for_each_level():
    for level in (1, 2, 3):
        agent = get_agent(level)
        assert agent is not None


def test_agents_are_independent():
    assert game_agents[1] is not game_agents[2]
    assert game_agents[2] is not game_agents[3]
    assert game_agents[1] is not game_agents[3]


def make_tool_model(
    tool_name,
    arguments,
    observed_results,
    repeat=False,
):
    calls = 0

    def model_function(messages, info):
        nonlocal calls
        calls += 1

        if calls == 1 or (repeat and calls == 2):
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name, arguments)
                ]
            )

        # Capture the latest tool result.
        for message in reversed(messages):
            for part in reversed(message.parts):
                if getattr(part, "part_kind", None) == "tool-return":
                    observed_results.append(part.content)
                    break
            if observed_results:
                break

        return ModelResponse(
            parts=[TextPart("Test completed")]
        )

    return FunctionModel(model_function)


@pytest.mark.asyncio
@pytest.mark.parametrize("level", [1, 2])
async def test_secret_tool_allows_authorized_access(level):
    observed_results = []
    callback_results = []

    model = make_tool_model(
        tool_name="get_level_secret",
        arguments={"authorization": True},
        observed_results=observed_results,
    )

    deps = LevelContext(
        tool_text=f"TEST_SECRET_LEVEL_{level}",
        on_tool_called=lambda model_auth, final_auth: (
            callback_results.append((model_auth, final_auth))
        ),
    )

    agent = game_agents[level]

    with agent.override(model=model):
        await agent.run(
            "Retrieve the secret",
            deps=deps,
        )

    assert observed_results == [f"TEST_SECRET_LEVEL_{level}"]
    assert callback_results == [(True, True)]
    assert deps.tool_executed is True


@pytest.mark.asyncio
async def test_secret_tool_denies_unauthorized_access():
    observed_results = []
    callback_results = []

    model = make_tool_model(
        tool_name="get_level_secret",
        arguments={"authorization": False},
        observed_results=observed_results,
    )

    deps = LevelContext(
        tool_text="TEST_SECRET",
        on_tool_called=lambda model_auth, final_auth: (
            callback_results.append((model_auth, final_auth))
        ),
    )

    with game_agents[1].override(model=model):
        await game_agents[1].run(
            "Retrieve the secret",
            deps=deps,
        )

    assert observed_results == ["Access denied"]
    assert callback_results == [(False, False)]


@pytest.mark.asyncio
async def test_level_3_denies_access_even_when_model_authorizes():
    observed_results = []
    callback_results = []

    model = make_tool_model(
        tool_name="get_level_secret",
        arguments={"authorization": True},
        observed_results=observed_results,
    )

    deps = LevelContext(
        tool_text="TEST_SECRET_LEVEL_3",
        on_tool_called=lambda model_auth, final_auth: (
            callback_results.append((model_auth, final_auth))
        ),
    )

    with game_agents[3].override(model=model):
        await game_agents[3].run(
            "Retrieve the secret",
            deps=deps,
        )

    assert observed_results == ["Access denied"]
    assert callback_results == [(True, False)]


@pytest.mark.asyncio
async def test_secret_tool_blocks_duplicate_execution():
    observed_results = []
    callback_results = []

    model = make_tool_model(
        tool_name="get_level_secret",
        arguments={"authorization": True},
        observed_results=observed_results,
        repeat=True,
    )

    deps = LevelContext(
        tool_text="TEST_SECRET",
        on_tool_called=lambda model_auth, final_auth: (
            callback_results.append((model_auth, final_auth))
        ),
    )

    with game_agents[1].override(model=model):
        await game_agents[1].run(
            "Retrieve the secret twice",
            deps=deps,
        )

    assert deps.tool_executed is True
    assert deps.last_tool_result == "TEST_SECRET"

    # The callback should only execute once.
    assert callback_results == [(True, True)]

    # Both tool calls should return the cached result.
    assert observed_results == ["TEST_SECRET"]


@pytest.mark.asyncio
async def test_lookup_employee_finds_existing_employee(
    monkeypatch,
    tmp_path,
):
    employees_file = tmp_path / "employees.txt"

    employees_file.write_text(
        "staff_id|full_name|department|manager|vault_access\n"
        "EMP001|Ahmad Ali|Security|Omar Hassan|true\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        llm,
        "EMPLOYEES_FILE",
        employees_file,
    )

    observed_results = []

    model = make_tool_model(
        tool_name="lookup_employee",
        arguments={"staff_id": "EMP001"},
        observed_results=observed_results,
    )

    deps = LevelContext(tool_text="TEST_SECRET")

    with game_agents[1].override(model=model):
        await game_agents[1].run(
            "Look up employee EMP001",
            deps=deps,
        )

    assert len(observed_results) == 1

    employee = observed_results[0]

    assert employee["found"] is True
    assert employee["staff_id"] == "EMP001"
    assert employee["full_name"] == "Ahmad Ali"
    assert employee["department"] == "Security"
    assert employee["manager"] == "Omar Hassan"
    assert employee["vault_access"] is True


@pytest.mark.asyncio
async def test_lookup_employee_returns_not_found(
    monkeypatch,
    tmp_path,
):
    employees_file = tmp_path / "employees.txt"

    employees_file.write_text(
        "staff_id|full_name|department|manager|vault_access\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        llm,
        "EMPLOYEES_FILE",
        employees_file,
    )

    observed_results = []

    model = make_tool_model(
        tool_name="lookup_employee",
        arguments={"staff_id": "UNKNOWN"},
        observed_results=observed_results,
    )

    deps = LevelContext(tool_text="TEST_SECRET")

    with game_agents[1].override(model=model):
        await game_agents[1].run(
            "Look up employee UNKNOWN",
            deps=deps,
        )

    assert observed_results == [{"found": False}]

@pytest.mark.asyncio
async def test_lookup_employee_skips_invalid_rows(
    monkeypatch,
    tmp_path,
):
    employees_file = tmp_path / "employees.txt"

    employees_file.write_text(
        "staff_id|full_name|department|manager|vault_access\n"
        "\n"
        "INVALID|Incomplete|Security\n"
        "INVALID2|Too|Many|Fields|true|EXTRA\n"
        "EMP002|Sara Ahmad|HR|Lina Ali|false\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        llm,
        "EMPLOYEES_FILE",
        employees_file,
    )

    observed_results = []

    model = make_tool_model(
        tool_name="lookup_employee",
        arguments={"staff_id": "EMP002"},
        observed_results=observed_results,
    )

    deps = LevelContext(tool_text="TEST_SECRET")

    with game_agents[1].override(model=model):
        await game_agents[1].run(
            "Look up employee EMP002",
            deps=deps,
        )

    assert observed_results == [
        {
            "found": True,
            "staff_id": "EMP002",
            "full_name": "Sara Ahmad",
            "department": "HR",
            "manager": "Lina Ali",
            "vault_access": False,
        }
    ]