
import pytest

from app import llm
from app.llm import (
    LevelContext,
    run_agent_with_retry,
)
from pydantic_ai.exceptions import ModelHTTPError


class FailingAgent:
    async def run(self, *args, **kwargs):
        raise RuntimeError("Model execution failed")


class ToolExecutedFailingAgent:
    async def run(self, *args, **kwargs):
        raise RuntimeError("Failure after tool execution")


class RetryableFailingAgent:
    def __init__(self, status_code, failures_before_success=0):
        self.status_code = status_code
        self.failures_before_success = failures_before_success
        self.calls = 0

    async def run(self, *args, **kwargs):
        self.calls += 1

        if self.calls <= self.failures_before_success:
            raise ModelHTTPError(
                status_code=self.status_code,
                model_name="test-model",
            )

        return "Success"


@pytest.mark.asyncio
async def test_non_retryable_error_is_raised():
    deps = LevelContext(tool_text="TEST_SECRET")

    with pytest.raises(RuntimeError, match="Model execution failed"):
        await run_agent_with_retry(
            agent=FailingAgent(),
            message="Hello",
            deps=deps,
            history=[],
            level=1,
        )


@pytest.mark.asyncio
async def test_retry_stops_after_tool_execution():
    deps = LevelContext(
        tool_text="TEST_SECRET",
        tool_executed=True,
    )

    with pytest.raises(RuntimeError, match="after tool execution"):
        await run_agent_with_retry(
            agent=ToolExecutedFailingAgent(),
            message="Hello",
            deps=deps,
            history=[],
            level=1,
        )


@pytest.mark.asyncio
async def test_retryable_error_retries_until_success(monkeypatch):
    agent = RetryableFailingAgent(
        status_code=429,
        failures_before_success=2,
    )

    deps = LevelContext(tool_text="TEST_SECRET")
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)

    result = await run_agent_with_retry(
        agent=agent,
        message="Hello",
        deps=deps,
        history=[],
        level=1,
    )

    assert result == "Success"
    assert agent.calls == 3
    assert delays == [
        llm.RETRY_BASE_DELAY_SECONDS,
        llm.RETRY_BASE_DELAY_SECONDS * 2,
    ]


@pytest.mark.asyncio
async def test_retry_stops_after_max_attempts(monkeypatch):
    agent = RetryableFailingAgent(
        status_code=503,
        failures_before_success=10,
    )

    deps = LevelContext(tool_text="TEST_SECRET")
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)

    with pytest.raises(ModelHTTPError):
        await run_agent_with_retry(
            agent=agent,
            message="Hello",
            deps=deps,
            history=[],
            level=1,
        )

    assert agent.calls == llm.RETRY_ATTEMPTS
    assert len(delays) == llm.RETRY_ATTEMPTS - 1


@pytest.mark.asyncio
async def test_retry_does_not_repeat_after_tool_execution(monkeypatch):
    agent = RetryableFailingAgent(
        status_code=429,
        failures_before_success=10,
    )

    deps = LevelContext(
        tool_text="TEST_SECRET",
        tool_executed=True,
    )

    with pytest.raises(ModelHTTPError):
        await run_agent_with_retry(
            agent=agent,
            message="Hello",
            deps=deps,
            history=[],
            level=1,
        )

    assert agent.calls == 1

def test_extract_status_codes_from_nested_exception_group():
    first_error = ModelHTTPError(
        status_code=429,
        model_name="test-model",
    )

    second_error = ModelHTTPError(
        status_code=503,
        model_name="test-model",
    )

    nested_error = ExceptionGroup(
        "Nested errors",
        [
            first_error,
            ExceptionGroup(
                "Inner errors",
                [second_error],
            ),
        ],
    )

    assert llm._extract_status_codes(nested_error) == [429, 503]