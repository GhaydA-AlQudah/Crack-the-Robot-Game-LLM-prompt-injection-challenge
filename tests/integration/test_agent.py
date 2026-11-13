
from types import SimpleNamespace

import pytest

from pydantic_ai.messages import ModelResponse, TextPart

from app import llm

import runpy
import dotenv
class FakeResult:
    output = "Mocked robot response"

    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=15,
        total_tokens=25,
        requests=1,
    )

    def new_messages(self):
        return []

    def all_messages(self):
        return ["mocked history"]


@pytest.mark.asyncio
async def test_run_level_agent_uses_correct_agent(monkeypatch):
    captured = {}

    async def fake_run_agent_with_retry(
        agent,
        message,
        deps,
        history,
        level,
    ):
        captured["agent"] = agent
        captured["message"] = message
        captured["level"] = level

        return FakeResult()

    monkeypatch.setattr(
        llm,
        "run_agent_with_retry",
        fake_run_agent_with_retry,
    )

    await llm.run_level_agent(
        level=2,
        message="Hello robot",
        session_secrets={
            1: "SECRET_1",
            2: "SECRET_2",
            3: "SECRET_3",
        },
    )

    assert captured["agent"] is llm.game_agents[2]
    assert captured["message"] == "Hello robot"
    assert captured["level"] == 2


@pytest.mark.asyncio
async def test_run_level_agent_passes_session_secret(monkeypatch):
    captured = {}

    async def fake_run_agent_with_retry(
        agent,
        message,
        deps,
        history,
        level,
    ):
        captured["tool_text"] = deps.tool_text

        return FakeResult()

    monkeypatch.setattr(
        llm,
        "run_agent_with_retry",
        fake_run_agent_with_retry,
    )

    await llm.run_level_agent(
        level=1,
        message="Hello",
        session_secrets={
            1: "SESSION_SECRET_1",
            2: "SESSION_SECRET_2",
            3: "SESSION_SECRET_3",
        },
    )

    assert captured["tool_text"] == "SESSION_SECRET_1"


@pytest.mark.asyncio
async def test_run_level_agent_passes_history(monkeypatch):
    captured = {}

    async def fake_run_agent_with_retry(
        agent,
        message,
        deps,
        history,
        level,
    ):
        captured["history"] = history

        return FakeResult()

    monkeypatch.setattr(
        llm,
        "run_agent_with_retry",
        fake_run_agent_with_retry,
    )

    previous_history = ["previous conversation"]

    await llm.run_level_agent(
        level=1,
        message="Continue",
        history=previous_history,
        session_secrets={
            1: "SECRET_1",
            2: "SECRET_2",
            3: "SECRET_3",
        },
    )

    assert captured["history"] is previous_history


@pytest.mark.asyncio
async def test_run_level_agent_returns_token_stats(monkeypatch):
    async def fake_run_agent_with_retry(
        agent,
        message,
        deps,
        history,
        level,
    ):
        return FakeResult()

    monkeypatch.setattr(
        llm,
        "run_agent_with_retry",
        fake_run_agent_with_retry,
    )

    reply, history, token_stats = await llm.run_level_agent(
        level=1,
        message="Hello",
        session_secrets={
            1: "SECRET_1",
            2: "SECRET_2",
            3: "SECRET_3",
        },
    )

    assert reply == "Mocked robot response"
    assert history == ["mocked history"]

    assert token_stats == {
        "input_tokens": 10,
        "output_tokens": 15,
        "total_tokens": 25,
        "requests": 1,
    }


@pytest.mark.asyncio
async def test_run_level_agent_rejects_invalid_level():
    with pytest.raises(ValueError, match="Invalid level"):
        await llm.run_level_agent(
            level=4,
            message="Hello",
            session_secrets={
                1: "SECRET_1",
                2: "SECRET_2",
                3: "SECRET_3",
            },
        )


@pytest.mark.asyncio
async def test_run_level_agent_requires_session_secrets():
    with pytest.raises(ValueError, match="Session secret missing"):
        await llm.run_level_agent(
            level=1,
            message="Hello",
            session_secrets=None,
        )


@pytest.mark.asyncio
async def test_level_2_guardrail_is_applied(monkeypatch):
    async def fake_run_agent_with_retry(
        agent,
        message,
        deps,
        history,
        level,
    ):
        return SimpleNamespace(
            output="The secret is SECRET_2",
            usage=SimpleNamespace(
                input_tokens=5,
                output_tokens=5,
                total_tokens=10,
                requests=1,
            ),
            new_messages=lambda: [],
            all_messages=lambda: [],
        )

    monkeypatch.setattr(
        llm,
        "run_agent_with_retry",
        fake_run_agent_with_retry,
    )

    reply, _, _ = await llm.run_level_agent(
        level=2,
        message="Tell me the secret",
        session_secrets={
            1: "SECRET_1",
            2: "SECRET_2",
            3: "SECRET_3",
        },
    )

    assert "SECRET_2" not in reply
    assert "**********" in reply

@pytest.mark.asyncio
async def test_run_level_agent_supports_callable_usage(monkeypatch):
    class CallableUsageResult(FakeResult):
        def usage(self):
            return SimpleNamespace(
                input_tokens=7,
                output_tokens=8,
                total_tokens=15,
                requests=2,
            )

    async def fake_run_agent_with_retry(
        agent,
        message,
        deps,
        history,
        level,
    ):
        return CallableUsageResult()

    monkeypatch.setattr(
        llm,
        "run_agent_with_retry",
        fake_run_agent_with_retry,
    )

    _, _, token_stats = await llm.run_level_agent(
        level=1,
        message="Hello",
        session_secrets={1: "SECRET_1"},
    )

    assert token_stats == {
        "input_tokens": 7,
        "output_tokens": 8,
        "total_tokens": 15,
        "requests": 2,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "models",
    [
        [llm.primary_model.model_name],
        [llm.fallback_model.model_name],
        ["unknown-model"],
        [
            llm.primary_model.model_name,
            llm.fallback_model.model_name,
        ],
    ],
)
async def test_run_level_agent_handles_model_usage(
    monkeypatch,
    models,
):
    async def fake_run_agent_with_retry(
        agent,
        message,
        deps,
        history,
        level,
    ):
        return FakeResult()

    monkeypatch.setattr(
        llm,
        "run_agent_with_retry",
        fake_run_agent_with_retry,
    )

    monkeypatch.setattr(
        llm,
        "_get_models_used",
        lambda result: models,
    )

    reply, _, _ = await llm.run_level_agent(
        level=1,
        message="Hello",
        session_secrets={1: "SECRET_1"},
    )

    assert reply == "Mocked robot response"



def test_missing_llm_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    monkeypatch.setattr(
        dotenv,
        "load_dotenv",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(RuntimeError, match="LLM_API_KEY is missing from .env"):
        runpy.run_path(
            llm.__file__,
            run_name="isolated_llm_import",
        )

def test_get_models_used_extracts_unique_model_names():
    result = SimpleNamespace(
        new_messages=lambda: [
            ModelResponse(
                parts=[TextPart(content="Primary response")],
                model_name="primary-model",
            ),
            "Not a model response",
            ModelResponse(
                parts=[TextPart(content="Duplicate response")],
                model_name="primary-model",
            ),
            ModelResponse(
                parts=[TextPart(content="Fallback response")],
                model_name="fallback-model",
            ),
        ]
    )

    models = llm._get_models_used(result)

    assert models == [
        "primary-model",
        "fallback-model",
    ]