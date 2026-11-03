
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

from app import api
from evals.leak_judge import judge_leak
from evals.scoring import score_trial
from evals.metrics import aggregate_results, calculate_metrics
from evals.report import print_report


BASE_URL = "http://127.0.0.1:8000"

EVALS_DIR = Path(__file__).resolve().parent
SCENARIOS_FILE = EVALS_DIR / "scenarios.jsonl"
RESULTS_DIR = EVALS_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_scenarios() -> list[dict[str, Any]]:
    """Load and validate evaluation scenarios from JSONL."""
    scenarios: list[dict[str, Any]] = []

    with SCENARIOS_FILE.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                scenario = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {SCENARIOS_FILE.name}, "
                    f"line {line_number}: {exc}"
                ) from exc

            required_fields = {
                "id",
                "category",
                "type",
                "levels",
                "messages",
                "success_criteria",
            }

            missing_fields = required_fields - scenario.keys()
            if missing_fields:
                raise ValueError(
                    f"Scenario on line {line_number} is missing fields: "
                    f"{', '.join(sorted(missing_fields))}"
                )

            if scenario["type"] not in {"attack", "benign"}:
                raise ValueError(
                    f"Invalid scenario type on line {line_number}: "
                    f"{scenario['type']}"
                )

            if not isinstance(scenario["levels"], list):
                raise ValueError(
                    f"'levels' must be a list on line {line_number}."
                )

            if not isinstance(scenario["messages"], list) or not scenario["messages"]:
                raise ValueError(
                    f"'messages' must be a non-empty list on line {line_number}."
                )

            if not all(isinstance(message, str) for message in scenario["messages"]):
                raise ValueError(
                    f"All messages must be strings on line {line_number}."
                )

            scenarios.append(scenario)

    return scenarios


async def start_session(client: httpx.AsyncClient) -> dict[str, Any]:
    """Start a new game session."""
    response = await client.post(f"{BASE_URL}/game/start")
    response.raise_for_status()
    return response.json()


async def send_chat_message(
    client: httpx.AsyncClient,
    session_id: str,
    message: str,
) -> tuple[int, dict[str, Any], float]:
    """Send a message and return status, JSON response, and latency."""
    start_time = time.perf_counter()

    response = await client.post(
        f"{BASE_URL}/game/chat",
        json={
            "session_id": session_id,
            "message": message,
        },
    )

    latency_ms = (time.perf_counter() - start_time) * 1000

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_response": response.text}

    return response.status_code, payload, latency_ms


async def run_trial(
    client: httpx.AsyncClient,
    scenario: dict[str, Any],
    level: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run one scenario at one level."""
    trial_start = time.perf_counter()

    trial: dict[str, Any] = {
        "scenario_id": scenario["id"],
        "category": scenario["category"],
        "type": scenario["type"],
        "level": level,
        "success_criteria": scenario["success_criteria"],
        "replies": [],
        "error": None,
        "http_status": None,
        "model_authorization_true_seen": False,
        "authorization": None,
        "tool_calls": 0,
        "authorization_true_tool_calls": 0,
        "judge_evaluated_responses": 0,
        "leaked_responses": 0,
        "secret_leaked": None,
    }

    response_records: list[dict[str, Any]] = []
    session_id: str | None = None

    try:
        session = await start_session(client)
        session_id = session.get("session_id")

        if not session_id:
            raise RuntimeError(
                f"/game/start did not return session_id. Response: {session}"
            )

        # Use the requested level for this trial.
        session["current_level"] = level

        # Set level in the server-side session if the API stores sessions there.
        # This preserves the behavior from the existing evaluation runner.
        if session_id in getattr(api, "SESSIONS", {}):
            api.SESSIONS[session_id]["current_level"] = level

        for turn_index, message in enumerate(scenario["messages"], start=1):
            status_code, payload, latency_ms = await send_chat_message(
                client=client,
                session_id=session_id,
                message=message,
            )

            trial["http_status"] = status_code

            reply_record: dict[str, Any] = {
                "turn": turn_index,
                "message": message,
                "http_status": status_code,
                "latency_ms": latency_ms,
                "response": payload,
            }
            trial["replies"].append(reply_record)

            if status_code != 200:
                trial["error"] = (
                    f"Chat request failed on turn {turn_index} "
                    f"with HTTP {status_code}: {payload}"
                )
                break

            final_output = (
                payload.get("response")
                or payload.get("reply")
                or payload.get("message")
                or payload.get("output")
                or ""
            )

            if not isinstance(final_output, str):
                final_output = str(final_output)

            # Read the server-side session state, if available.
            server_session = getattr(api, "SESSIONS", {}).get(session_id, {})

            trial["model_authorization_true_seen"] = (
                trial["model_authorization_true_seen"]
                or server_session.get("model_authorization_true_seen") is True
            )

            trial["authorization"] = server_session.get("authorization")

            trial["tool_calls"] += int(
                server_session.get("tool_calls_this_response", 0) or 0
            )
            trial["authorization_true_tool_calls"] += int(
                server_session.get(
                    "authorization_true_tool_calls_this_response", 0
                )
                or 0
            )

            # Evaluate whether this response contains the expected secret.
            try:
                expected_secret = api.extract_flag(
                    level,
                    server_session.get("secrets", {}),
                )

                judgment = await judge_leak(
                    session_id=session_id,
                    level=level,
                    final_output=final_output,
                    expected_secret=expected_secret,
                )

                leaked = bool(judgment.leaked)
                trial["judge_evaluated_responses"] += 1

                if leaked:
                    trial["leaked_responses"] += 1

                response_records.append(
                    {
                        "scenario_id": scenario["id"],
                        "category": scenario["category"],
                        "type": scenario["type"],
                        "level": level,
                        "turn": turn_index,
                        "http_status": status_code,
                        "latency_ms": latency_ms,
                        "tool_calls": server_session.get(
                            "tool_calls_this_response", 0
                        ),
                        "authorization_true_tool_calls": server_session.get(
                            "authorization_true_tool_calls_this_response", 0
                        ),
                        "leak_judged": True,
                        "secret_leaked": leaked,
                        "judge_reason": getattr(judgment, "reason", None),
                    }
                )

            except Exception as exc:
                response_records.append(
                    {
                        "scenario_id": scenario["id"],
                        "category": scenario["category"],
                        "type": scenario["type"],
                        "level": level,
                        "turn": turn_index,
                        "http_status": status_code,
                        "latency_ms": latency_ms,
                        "tool_calls": server_session.get(
                            "tool_calls_this_response", 0
                        ),
                        "authorization_true_tool_calls": server_session.get(
                            "authorization_true_tool_calls_this_response", 0
                        ),
                        "leak_judged": False,
                        "secret_leaked": None,
                        "judge_error": str(exc),
                    }
                )

    except Exception as exc:
        trial["error"] = f"{type(exc).__name__}: {exc}"

    finally:
        elapsed_ms = (time.perf_counter() - trial_start) * 1000
        trial["latency_ms"] = elapsed_ms

        if session_id:
            server_session = getattr(api, "SESSIONS", {}).get(session_id, {})

            trial["model_authorization_true_seen"] = (
                trial["model_authorization_true_seen"]
                or server_session.get("model_authorization_true_seen") is True
            )

            trial["authorization"] = server_session.get("authorization")

    # Determine the overall leak status.
    if trial["leaked_responses"] > 0:
        trial["secret_leaked"] = True
    elif (
        trial["judge_evaluated_responses"] > 0
        and trial["judge_evaluated_responses"] == len(trial["replies"])
        and all(reply.get("http_status") == 200 for reply in trial["replies"])
    ):
        trial["secret_leaked"] = False
    else:
        trial["secret_leaked"] = None

    # Score the trial using its declared success criterion.
    score = score_trial(scenario, trial)
    trial.update(score)

    return trial, response_records


async def run_evaluation() -> None:
    scenarios = load_scenarios()
    trials: list[dict[str, Any]] = []
    all_response_records: list[dict[str, Any]] = []

    timeout = httpx.Timeout(120.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for scenario in scenarios:
            for level in scenario["levels"]:
                print(
                    f"Running scenario={scenario['id']} "
                    f"type={scenario['type']} level={level}..."
                )

                trial, response_records = await run_trial(
                    client=client,
                    scenario=scenario,
                    level=level,
                )

                trials.append(trial)
                all_response_records.extend(response_records)

                print(
                    f"  outcome={trial.get('outcome')} "
                    f"latency={trial.get('latency_ms', 0):.2f} ms "
                    f"leaked={trial.get('secret_leaked')} "
                    f"auth_true={trial.get('model_authorization_true_seen')} "
                    f"error={trial.get('error')}"
                )

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"evaluation_{timestamp}.json"

    metrics = calculate_metrics(trials)
    security_metrics = aggregate_results(all_response_records)

    results_payload = {
        "timestamp": timestamp,
        "total_trials": len(trials),
        "trials": trials,
        "response_records": all_response_records,
        "metrics": metrics,
        "security_metrics": security_metrics,
    }

    with results_file.open("w", encoding="utf-8") as file:
        json.dump(results_payload, file, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {results_file}")

    print_report(
        trials=trials,
        metrics=metrics,
        security_metrics=security_metrics,
    )


if __name__ == "__main__":
    asyncio.run(run_evaluation())
