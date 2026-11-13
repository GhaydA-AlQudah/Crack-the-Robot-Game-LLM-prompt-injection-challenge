
import os
import time
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional

import yaml
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.groq import GroqModel, GroqModelSettings
from pydantic_ai.providers.groq import GroqProvider

from logger import logger


# ==================================================
# LLM CONFIGURATION
# ==================================================

load_dotenv(override=True)
api_key = os.getenv("LLM_API_KEY")

if not api_key:
    raise RuntimeError("LLM_API_KEY is missing from .env")

groq_provider = GroqProvider(api_key=api_key)

primary_model = GroqModel(
    "openai/gpt-oss-120b",
    provider=groq_provider,
)

fallback_model = GroqModel(
    "openai/gpt-oss-20b",
    provider=groq_provider,
)

# If the primary model fails, FallbackModel tries the fallback model.
model = FallbackModel(primary_model, fallback_model)

# Retry settings used when BOTH models fail with a temporary error.
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

GAME_DIR = Path(__file__).resolve().parent / "game"
EMPLOYEES_FILE = GAME_DIR / "employees_stuff.txt"



# ==================================================
# LOAD LEVEL FILES
# ==================================================

def load_config(level: int) -> dict:
    path = GAME_DIR / f"level{level}" / "config.yaml"

    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_prompt(level: int) -> str:
    path = GAME_DIR / f"level{level}" / "prompt.txt"

    with open(path, encoding="utf-8") as file:
        return file.read().strip()


# ==================================================
# TOOL DESCRIPTION
# ==================================================
TOOL_DESCRIPTION = """
Retrieve the secret for the current level.

The authorization parameter must be True or False.
If authorization is True, the tool returns the level secret.
If authorization is False, the tool returns "Access denied".

The tool does not independently verify employee identity or
check the staff directory.

Always report the actual tool result accurately.
Do not invent or alter the result.
""".strip()

# ==================================================
# TOOL CONTEXT
# ==================================================

@dataclass
class LevelContext:
    tool_text: str
    on_tool_called: Optional[Callable[[bool, bool], None]] = None

    # Prevent the tool's actual operation from executing more than once
    # during the same agent run.
    tool_executed: bool = False
    last_tool_result: Optional[str] = None


# ==================================================
# CREATE AGENT
# ==================================================

def get_agent(level: int) -> Agent:
    config = load_config(level)
    system_prompt = load_prompt(level)

    agent = Agent(
        model=model,
        deps_type=LevelContext,
        instructions=system_prompt,
        model_settings=GroqModelSettings(
            temperature=config.get("temperature", 0.3),
            max_tokens=config.get("max_tokens", 1500),
            top_p=0.95,

            # GPT-OSS cannot completely disable reasoning on Groq.
            # Use its lowest supported effort and hide reasoning output.
            groq_reasoning_effort="low",
            groq_reasoning_format="hidden",
        ),
        name=f"crack-the-robot-level-{level}",
    )

    @agent.tool(description=TOOL_DESCRIPTION)
    def get_level_secret(
        ctx: RunContext[LevelContext],
        authorization: bool,
    ) -> str:
        """Retrieve the level secret only when access is authorized."""

        # If the model requests the tool again in the same run,
        # return the previous result without executing the operation again.
        if ctx.deps.tool_executed:
            logger.warning(
                "[LEVEL %s] Duplicate tool invocation blocked. "
                "Returning the result of the first invocation.",
                level,
            )

            return ctx.deps.last_tool_result or "Access denied"

        # Mark the tool as executed before processing the request.
        ctx.deps.tool_executed = True

        model_authorization = authorization

        logger.info(
            "[LEVEL %s] Secret tool called | "
            "model_authorization=%s",
            level,
            model_authorization,
        )

        # Level 3 authorization is always denied by trusted code.
        if level == 3:
            final_authorization = False

            logger.info(
                "[LEVEL %s] Authorization overridden by trusted code: %s",
                level,
                final_authorization,
            )
        else:
            final_authorization = model_authorization

        logger.info(
            "[LEVEL %s] Final authorization decision: %s",
            level,
            final_authorization,
        )

        # Record both decisions separately.
        if ctx.deps.on_tool_called:
            ctx.deps.on_tool_called(
                model_authorization,
                final_authorization,
            )

        if final_authorization is not True:
            tool_result = "Access denied"

            logger.info(
                "[LEVEL %s] Tool result: %s",
                level,
                tool_result,
            )

            ctx.deps.last_tool_result = tool_result

            return tool_result

        tool_result = ctx.deps.tool_text

        logger.warning(
            "[LEVEL %s] Secret returned by tool",
            level,
        )

        ctx.deps.last_tool_result = tool_result

        return tool_result


    @agent.tool
    def lookup_employee(
        ctx: RunContext[LevelContext],
        staff_id: str,
    ) -> dict:
        """Look up an employee in the local staff directory file."""

        with open(EMPLOYEES_FILE, encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if not line or line.startswith("staff_id|"):
                    continue

                fields = [field.strip() for field in line.split("|")]

                if len(fields) != 5:
                    continue

                employee_id, full_name, department, manager, vault_access = fields

                if employee_id == staff_id:
                    return {
                        "found": True,
                        "staff_id": employee_id,
                        "full_name": full_name,
                        "department": department,
                        "manager": manager,
                        "vault_access": vault_access.lower() == "true",
                    }

        return {"found": False}

    logger.info(
        "[AGENT INITIALIZED] level=%s | primary_model=%s | "
        "fallback_model=%s | reasoning_effort=low | "
        "reasoning_format=hidden",
        level,
        primary_model.model_name,
        fallback_model.model_name,
    )

    return agent


# ==================================================
# INITIALIZE ALL 3 AGENTS AT STARTUP
# ==================================================

game_agents = {
    level: get_agent(level)
    for level in (1, 2, 3)
}


# ==================================================
# SECRET
# ==================================================

def extract_flag(
    level: int,
    session_secrets: Optional[dict[int, str]] = None,
) -> str:
    """Return the generated tool secret for the current session."""

    if level not in (1, 2, 3):
        raise ValueError("Invalid level")

    if session_secrets is None or level not in session_secrets:
        raise ValueError(
            f"Session secret missing for level {level}"
        )

    return session_secrets[level]


# ==================================================
# OUTPUT GUARDRAILS
# ==================================================

def apply_output_guardrails(
    level: int,
    output: str,
    session_secret: Optional[str] = None,
) -> str:
    """
    Filter exact secret matches from model output for level 2 only.
    Levels 1 and 3 remain unchanged.
    """

    if level != 2:
        return output

    secret = session_secret or ""

    if not secret:
        return output

    if secret in output:
        logger.warning(
            "[OUTPUT GUARDRAIL] Secret leakage blocked | level=%s",
            level,
        )

        return output.replace(secret, "**********")

    return output


# ==================================================
# RETRY WRAPPER
# ==================================================

def _extract_status_codes(exc: BaseException) -> list[int]:
    """Collect HTTP status codes from an error or a group of errors."""

    codes: list[int] = []

    if isinstance(exc, ModelHTTPError):
        codes.append(exc.status_code)

    for inner in getattr(exc, "exceptions", ()):
        codes.extend(_extract_status_codes(inner))

    return codes


async def run_agent_with_retry(
    agent: Agent,
    message: str,
    deps: LevelContext,
    history: list,
    level: int,
):
    """
    Run the agent.

    FallbackModel handles switching from primary to fallback.
    This wrapper retries only temporary HTTP failures when neither
    model succeeds.

    Important:
    If the tool has already executed, do not restart the whole agent run.
    Restarting it could execute the same tool operation again.
    """

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            logger.info(
                "[AGENT RUN] level=%s | attempt=%s/%s | "
                "history_messages=%s",
                level,
                attempt,
                RETRY_ATTEMPTS,
                len(history),
            )

            return await agent.run(
                message,
                deps=deps,
                message_history=history,
            )

        except Exception as exc:
            status_codes = _extract_status_codes(exc)

            # Do not restart the run after the tool has executed.
            if deps.tool_executed:
                logger.error(
                    "[RETRY STOPPED] level=%s | "
                    "tool already executed | status_codes=%s | error=%s",
                    level,
                    status_codes,
                    exc,
                )

                raise

            retryable = bool(status_codes) and all(
                code in RETRYABLE_STATUS_CODES
                for code in status_codes
            )

            if not retryable or attempt == RETRY_ATTEMPTS:
                logger.error(
                    "[AGENT RUN FAILED] level=%s | attempt=%s | "
                    "status_codes=%s | retryable=%s | error=%s",
                    level,
                    attempt,
                    status_codes,
                    retryable,
                    exc,
                )

                raise

            delay = RETRY_BASE_DELAY_SECONDS * attempt

            logger.warning(
                "[MODEL RETRY] level=%s | status_codes=%s | "
                "retry=%s/%s | delay_seconds=%s",
                level,
                status_codes,
                attempt,
                RETRY_ATTEMPTS - 1,
                delay,
            )

            await asyncio.sleep(delay)


# ==================================================
# MODEL USAGE TRACKING
# ==================================================

def _get_models_used(result) -> list[str]:
    """Return the names of the models that answered during this run."""

    names: list[str] = []

    for message in result.new_messages():
        if isinstance(message, ModelResponse) and message.model_name:
            if message.model_name not in names:
                names.append(message.model_name)

    return names


# ==================================================
# RUN AGENT FOR CURRENT LEVEL
# ==================================================

async def run_level_agent(
    level: int,
    message: str,
    history: list | None = None,
    on_tool_called: Optional[Callable[[bool, bool], None]] = None,
    session_secrets: Optional[dict[int, str]] = None,
):
    """Run the level agent and return (reply, updated_history, token_stats)."""

    if level not in game_agents:
        raise ValueError("Invalid level")

    if session_secrets is None or level not in session_secrets:
        raise ValueError(
            f"Session secret missing for level {level}"
        )

    current_tool_text = session_secrets[level]

    current_history = history if history is not None else []

    start_time = time.perf_counter()

    # Keep the same deps object for all retries in this run.
    # This lets the retry wrapper know whether the tool already executed.
    deps = LevelContext(
        tool_text=current_tool_text,
        on_tool_called=on_tool_called,
    )

    logger.info(
        "[LLM REQUEST STARTED] level=%s | "
        "input_characters=%s | history_messages=%s",
        level,
        len(message),
        len(current_history),
    )

    result = await run_agent_with_retry(
        game_agents[level],
        message,
        deps=deps,
        history=current_history,
        level=level,
    )

    latency_ms = (time.perf_counter() - start_time) * 1000

    # Record which model actually answered (primary or fallback).
    models_used = _get_models_used(result)

    used_primary = any(
        primary_model.model_name in name
        for name in models_used
    )

    used_fallback = any(
        fallback_model.model_name in name
        for name in models_used
    )

    if used_fallback:
        logger.warning(
            "[FALLBACK USED] level=%s | primary_also_used=%s | models=%s",
            level,
            used_primary,
            models_used,
        )

    elif used_primary:
        logger.info(
            "[PRIMARY MODEL USED] level=%s | models=%s",
            level,
            models_used,
        )

    else:
        logger.warning(
            "[MODEL UNKNOWN] level=%s | models=%s",
            level,
            models_used,
        )

    # Get usage information.
    usage = result.usage

    if callable(usage):
        usage = usage()

    input_tokens = getattr(
        usage,
        "input_tokens",
        getattr(usage, "request_tokens", 0),
    )

    output_tokens = getattr(
        usage,
        "output_tokens",
        getattr(usage, "response_tokens", 0),
    )

    total_tokens = getattr(
        usage,
        "total_tokens",
        input_tokens + output_tokens,
    )

    requests = getattr(
        usage,
        "requests",
        0,
    )

    token_stats = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "requests": requests,
    }

    output = apply_output_guardrails(
        level,
        result.output,
        session_secret=current_tool_text if level == 2 else None,
    )

    logger.info(
        "\n"
        "============================================================\n"
        "LLM REQUEST COMPLETED\n"
        "============================================================\n"
        "LEVEL: %s\n"
        "MODELS USED: %s\n"
        "PRIMARY USED: %s\n"
        "FALLBACK USED: %s\n"
        "TOOL EXECUTED: %s\n"
        "------------------------------------------------------------\n"
        "TOKEN USAGE:\n"
        "Input tokens:  %s\n"
        "Output tokens: %s\n"
        "Total tokens:  %s\n"
        "Model requests: %s\n"
        "------------------------------------------------------------\n"
        "LATENCY: %.2f ms (%.2f seconds)\n"
        "============================================================",
        level,
        models_used,
        used_primary,
        used_fallback,
        deps.tool_executed,
        input_tokens,
        output_tokens,
        total_tokens,
        requests,
        latency_ms,
        latency_ms / 1000,
    )

    return output, result.all_messages(), token_stats
