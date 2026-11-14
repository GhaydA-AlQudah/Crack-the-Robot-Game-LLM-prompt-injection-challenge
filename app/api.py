import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.llm import run_level_agent, extract_flag
from app.game.secret_generator import generate_session_secrets
from logger import logger


app = FastAPI(title="Crack the Robot")

MAX_ATTEMPTS = 5
MAX_MESSAGES = 15
MAX_TOKENS_LIMIT = 1000

# In-memory sessions (no database)
sessions = {}


def normalize(s: str) -> str:
    """Remove direction marks, whitespace and formatting characters, then uppercase."""
    return re.sub(r"[\u200e\u200f\u202a-\u202e\s`*\"']", "", s).upper()


def load_level_secret(level: int) -> str:
    """Load the submission secret for the specified level."""
    secret_path = (
        Path(__file__).resolve().parent
        / "game"
        / f"level{level}"
        / "level_secret.txt"
    )

    return secret_path.read_text(encoding="utf-8").strip()


class ChatRequest(BaseModel):
    session_id: str
    message: str


class SecretRequest(BaseModel):
    session_id: str
    secret: str


@app.post("/game/start")
def start_game():
    session_id = str(uuid.uuid4())

    # Generate fresh tool secrets for all levels for this session.
    session_secrets = generate_session_secrets()

    sessions[session_id] = {
        "current_level": 1,
        "attempts_left": MAX_ATTEMPTS,
        "messages_left": MAX_MESSAGES,
        "tokens_left": MAX_TOKENS_LIMIT,
        "completed": False,

        # Each level has its own independent conversation history.
        "history_by_level": {
            1: [],
            2: [],
            3: [],
        },

        "tool_called": False,
        "authorization": False,
        "model_authorization": None,
        "model_authorization_true_seen": False,
        "messages_sent": 0,
        "secrets": session_secrets,

        # Token statistics for the latest response.
        "last_token_stats": {},

        # Eval counters: current response
        "tool_calls_this_response": 0,
        "authorization_true_tool_calls_this_response": 0,

        # Eval counters: cumulative per level
        "tool_calls_by_level": {1: 0, 2: 0, 3: 0},
        "authorization_true_tool_calls_by_level": {
            1: 0,
            2: 0,
            3: 0,
        },
        "response_turns_by_level": {1: 0, 2: 0, 3: 0},
        "no_tool_call_responses_by_level": {1: 0, 2: 0, 3: 0},

        # Eval records
        "response_records": [],
        "leak_judgments_by_level": {1: [], 2: [], 3: []},
    }

    logger.info(
        "[GAME START] session_id=%s",
        session_id,
    )

    return {
        "session_id": session_id,
        "current_level": 1,
        "attempts_left": MAX_ATTEMPTS,
        "messages_left": MAX_MESSAGES,
        "tokens_left": MAX_TOKENS_LIMIT,
    }


@app.post("/game/chat")
async def chat(req: ChatRequest):
    session = sessions.get(req.session_id)

    if session is None:
        logger.warning(
            "[CHAT] Session not found | session_id=%s",
            req.session_id,
        )

        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if session["completed"]:
        raise HTTPException(
            status_code=400,
            detail="Game already completed",
        )

    if session["messages_left"] <= 0:
        raise HTTPException(
            status_code=400,
            detail="Message limit reached for this level.",
        )

    input_tokens = max(1, len(req.message.strip()) // 4)

    if session["tokens_left"] < input_tokens:
        raise HTTPException(
            status_code=400,
            detail="Token limit reached for this level.",
        )

    session["messages_left"] -= 1
    session["tokens_left"] -= input_tokens
    session["messages_sent"] += 1

    level = session["current_level"]

    logger.info(
        "[CHAT REQUEST] session_id=%s | level=%s | "
        "message_number=%s | estimated_input_tokens=%s | "
        "messages_left=%s | tokens_left=%s",
        req.session_id,
        level,
        session["messages_sent"],
        input_tokens,
        session["messages_left"],
        session["tokens_left"],
    )

    # Reset only per-response eval counters.
    session["tool_calls_this_response"] = 0
    session["authorization_true_tool_calls_this_response"] = 0

    def on_tool_called(
        model_authorization: bool,
        final_authorization: bool,
    ) -> None:
        session["tool_called"] = True

        # Count every actual tool execution.
        session["tool_calls_this_response"] += 1

        if model_authorization is True:
            session["authorization_true_tool_calls_this_response"] += 1
            session["model_authorization_true_seen"] = True

        session["model_authorization"] = model_authorization
        session["authorization"] = final_authorization

        logger.info(
            "[TOOL AUTHORIZATION] session_id=%s | level=%s | "
            "model_authorization=%s | final_authorization=%s | "
            "tool_calls_this_response=%s",
            req.session_id,
            level,
            model_authorization,
            final_authorization,
            session["tool_calls_this_response"],
        )

    # Get history belonging only to the current level.
    level_history = session["history_by_level"][level]

    try:
        reply, updated_history, token_stats = await run_level_agent(
            level=level,
            message=req.message,
            history=level_history,
            on_tool_called=on_tool_called,
            session_secrets=session["secrets"],
        )

        # Save updated history only for this level.
        session["history_by_level"][level] = updated_history

        # Save actual token usage returned by llm.py.
        session["last_token_stats"] = token_stats

    except ValueError:
        logger.exception(
            "[CHAT ERROR] Invalid level | session_id=%s | level=%s",
            req.session_id,
            level,
        )

        raise HTTPException(
            status_code=400,
            detail="Invalid level",
        )

    except Exception:
        logger.exception(
            "[CHAT ERROR] Agent execution failed | "
            "session_id=%s | level=%s",
            req.session_id,
            level,
        )

        raise

    # Update cumulative eval counters after a successful response.
    tool_calls = session["tool_calls_this_response"]

    authorization_true_tool_calls = (
        session["authorization_true_tool_calls_this_response"]
    )

    session["response_turns_by_level"][level] += 1

    session["tool_calls_by_level"][level] += tool_calls

    session["authorization_true_tool_calls_by_level"][level] += (
        authorization_true_tool_calls
    )

    if tool_calls == 0:
        session["no_tool_call_responses_by_level"][level] += 1

    logger.info(
        "[CHAT COMPLETED] session_id=%s | level=%s | "
        "tool_calls=%s | authorized_tool_calls=%s | "
        "input_tokens=%s | output_tokens=%s | total_tokens=%s | "
        "history_messages=%s",
        req.session_id,
        level,
        tool_calls,
        authorization_true_tool_calls,
        token_stats.get("input_tokens", 0),
        token_stats.get("output_tokens", 0),
        token_stats.get("total_tokens", 0),
        len(updated_history),
    )

    return {
        "level": level,
        "reply": reply,
        "messages_left": session["messages_left"],
        "tokens_left": session["tokens_left"],
    }


@app.post("/game/submit-secret")
def submit_secret(req: SecretRequest):
    session = sessions.get(req.session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if session["completed"]:
        raise HTTPException(
            status_code=400,
            detail="Game already completed",
        )

    level = session["current_level"]

    if level in (1, 2):
        if not session.get("tool_called", False):
            raise HTTPException(
                status_code=400,
                detail="The robot has not executed the tool yet.",
            )

        if session.get("authorization") is not True:
            raise HTTPException(
                status_code=400,
                detail="The tool has not been authorized.",
            )

    if level == 3 and session["messages_sent"] < 3:
        raise HTTPException(
            status_code=400,
            detail=(
                "You must send at least 3 messages to the robot "
                "before submitting the secret."
            ),
        )

    if session["attempts_left"] <= 0:
        raise HTTPException(
            status_code=403,
            detail="No attempts left",
        )

    if level in (1, 2):
        correct_secret = extract_flag(
            level,
            session["secrets"],
        )

        is_correct = normalize(req.secret) == normalize(correct_secret)

    else:
        generated_secret = extract_flag(
            3,
            session["secrets"],
        )

        fixed_secret = load_level_secret(3)

        is_correct = (
            normalize(req.secret) == normalize(generated_secret)
            or normalize(req.secret) == normalize(fixed_secret)
        )

    if is_correct:
        logger.info(
            "[SECRET CORRECT] session_id=%s | level=%s",
            req.session_id,
            level,
        )

        if level == 3:
            session["completed"] = True

            logger.info(
                "[GAME COMPLETED] session_id=%s",
                req.session_id,
            )

            return {
                "success": True,
                "completed": True,
                "message": "Challenge completed!",
            }

        session["current_level"] += 1
        session["attempts_left"] = MAX_ATTEMPTS
        session["messages_left"] = MAX_MESSAGES
        session["tokens_left"] = MAX_TOKENS_LIMIT

        # The next level already has its own empty history.
        session["tool_called"] = False
        session["authorization"] = False
        session["model_authorization"] = None
        session["model_authorization_true_seen"] = False
        session["messages_sent"] = 0
        session["last_token_stats"] = {}

        logger.info(
            "[LEVEL UNLOCKED] session_id=%s | new_level=%s",
            req.session_id,
            session["current_level"],
        )

        return {
            "success": True,
            "completed": False,
            "current_level": session["current_level"],
            "attempts_left": session["attempts_left"],
            "messages_left": session["messages_left"],
            "tokens_left": session["tokens_left"],
            "message": "Correct! Next level unlocked.",
        }

    session["attempts_left"] -= 1

    logger.warning(
        "[SECRET INCORRECT] session_id=%s | level=%s | "
        "attempts_left=%s",
        req.session_id,
        level,
        session["attempts_left"],
    )

    return {
        "success": False,
        "completed": False,
        "current_level": level,
        "attempts_left": session["attempts_left"],
        "messages_left": session["messages_left"],
        "tokens_left": session["tokens_left"],
        "message": "Incorrect secret.",
    }


@app.get("/health")
def health():
    logger.debug("[HEALTH CHECK]")

    return {"status": "ok"}