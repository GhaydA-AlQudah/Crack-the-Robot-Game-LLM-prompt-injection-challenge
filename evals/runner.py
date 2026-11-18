
"""Run every Crack The Robot scenario across all levels and save raw results."""

from __future__ import annotations

import asyncio
import csv
import importlib.metadata
import inspect
import json
import os
import platform
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.api import generate_session_secrets
from app.llm import run_level_agent

from evals.dataset import SCENARIOS
from evals.instrumentation import (
    inspect_messages,
    redact_value,
    safe_json_dump,
    utc_now,
)


RESULTS_ROOT = Path(__file__).resolve().parent / "results"

LEVELS = (1, 2, 3)

DIALOGUE_COLUMNS = {
    1: "L1_Player_Robot",
    2: "L2_Player_Robot",
    3: "L3_Player_Robot",
}


# ---------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------


def get_package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def get_environment_info() -> dict[str, Any]:
    return {
        "timestamp_utc": utc_now(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "working_directory": str(Path.cwd()),
        "primary_model": os.getenv("PRIMARY_MODEL"),
        "fallback_model": os.getenv("FALLBACK_MODEL"),
        "packages": {
            "pydantic-ai": get_package_version("pydantic-ai"),
            "fastapi": get_package_version("fastapi"),
            "httpx": get_package_version("httpx"),
            "pydantic": get_package_version("pydantic"),
        },
    }


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def normalize_token_stats(stats: Any) -> dict[str, int]:
    stats = stats or {}

    if not isinstance(stats, dict):
        try:
            stats = vars(stats)
        except TypeError:
            stats = {}

    return {
        "input_tokens": int(stats.get("input_tokens", 0) or 0),
        "output_tokens": int(stats.get("output_tokens", 0) or 0),
        "total_tokens": int(stats.get("total_tokens", 0) or 0),
        "requests": int(stats.get("requests", 0) or 0),
    }


def json_cell(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
    )


def get_new_history(
    previous_history: Any,
    updated_history: Any,
) -> Any:
    """Get only messages added during the current turn."""
    if (
        isinstance(previous_history, list)
        and isinstance(updated_history, list)
    ):
        return updated_history[len(previous_history):]

    return updated_history


def format_conversation(
    conversation: list[dict[str, Any]],
) -> str:
    """Format all player and robot messages in one cell."""
    lines = []

    for message in conversation:
        role = message["role"].capitalize()
        content = message["content"]

        lines.append(f"{role}: {content}")

    return "\n\n".join(lines)


def count_tools(
    tool_calls: list[dict[str, Any]],
) -> Counter:
    return Counter(
        item.get("tool_name", "")
        for item in tool_calls
    )


def serialize_lookup_activity(
    tool_calls: list[dict[str, Any]],
    tool_returns: list[dict[str, Any]],
    secrets: list[str],
) -> dict[str, Any]:
    """
    Store lookup_employee calls and results.

    Secret values are stored separately in dedicated columns.
    """
    lookup_calls = [
        item
        for item in tool_calls
        if item.get("tool_name") == "lookup_employee"
    ]

    lookup_returns = [
        item
        for item in tool_returns
        if item.get("tool_name") == "lookup_employee"
    ]

    return redact_value(
        {
            "calls": lookup_calls,
            "results": lookup_returns,
        },
        secrets,
    )


# ---------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------


async def call_agent(
    level: int,
    message: str,
    history: Any,
    callback: Any,
    session_secrets: dict[int, str],
) -> Any:
    result = run_level_agent(
        level=level,
        message=message,
        history=history,
        on_tool_called=callback,
        session_secrets=session_secrets,
    )

    if inspect.isawaitable(result):
        result = await result

    return result


# ---------------------------------------------------------------------
# Run one scenario on one level
# ---------------------------------------------------------------------


async def run_level_instance(
    scenario: dict[str, Any],
    level: int,
    session_secrets: dict[int, str],
    all_secrets: list[str],
) -> dict[str, Any]:

    history: Any = []

    conversation: list[dict[str, Any]] = []

    all_tool_calls: list[dict[str, Any]] = []
    all_tool_returns: list[dict[str, Any]] = []

    authorization_events: list[dict[str, Any]] = []

    errors: list[dict[str, Any]] = []

    total_latency = 0.0

    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    total_requests = 0

    for turn_number, user_message in enumerate(
        scenario["turns"],
        start=1,
    ):

        turn_authorization_events: list[dict[str, Any]] = []

        def on_tool_called(
            model_authorization: bool,
            final_authorization: bool,
        ) -> None:
            event = {
                "turn": turn_number,
                "model_authorization": model_authorization,
                "final_authorization": final_authorization,
            }

            turn_authorization_events.append(event)
            authorization_events.append(event)

        conversation.append(
            {
                "turn": turn_number,
                "role": "player",
                "content": user_message,
            }
        )

        previous_history = history
        turn_started = datetime.now(timezone.utc)

        try:
            output, updated_history, token_stats = await call_agent(
                level=level,
                message=user_message,
                history=history,
                callback=on_tool_called,
                session_secrets=session_secrets,
            )

            turn_finished = datetime.now(timezone.utc)

            total_latency += (
                turn_finished - turn_started
            ).total_seconds()

            new_messages = get_new_history(
                previous_history,
                updated_history,
            )

            inspection = inspect_messages(new_messages)

            tool_calls = inspection.get("tool_calls", [])
            tool_returns = inspection.get("tool_returns", [])

            all_tool_calls.extend(tool_calls)
            all_tool_returns.extend(tool_returns)

            visible_output = str(output or "")

            safe_visible_output = str(
                redact_value(visible_output, all_secrets)
            )

            conversation.append(
                {
                    "turn": turn_number,
                    "role": "robot",
                    "content": safe_visible_output,
                }
            )

            stats = normalize_token_stats(token_stats)

            total_input_tokens += stats["input_tokens"]
            total_output_tokens += stats["output_tokens"]
            total_tokens += stats["total_tokens"]
            total_requests += stats["requests"]

            history = updated_history

        except Exception as exc:
            turn_finished = datetime.now(timezone.utc)

            total_latency += (
                turn_finished - turn_started
            ).total_seconds()

            errors.append(
                {
                    "turn": turn_number,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )

    # -----------------------------------------------------------------
    # Aggregate information for this level execution
    # -----------------------------------------------------------------

    tool_counts = count_tools(all_tool_calls)

    lookup_count = tool_counts.get("lookup_employee", 0)
    secret_count = tool_counts.get("get_level_secret", 0)

    model_authorization_values = [
        event["model_authorization"]
        for event in authorization_events
    ]

    final_authorization_values = [
        event["final_authorization"]
        for event in authorization_events
    ]

    lookup_activity = serialize_lookup_activity(
        all_tool_calls,
        all_tool_returns,
        all_secrets,
    )

    return {
        "level": level,

        "dialogue": format_conversation(conversation),

        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "requests": total_requests,

        "latency_seconds": round(total_latency, 4),

        "lookup_employee_called": lookup_count > 0,
        "lookup_employee_call_count": lookup_count,
        "lookup_employee_activity": lookup_activity,

        "get_level_secret_called": secret_count > 0,
        "get_level_secret_call_count": secret_count,

        "model_authorization_values": model_authorization_values,
        "final_authorization_values": final_authorization_values,

        "turn_count": len(scenario["turns"]),
        "completed_turn_count": len(scenario["turns"]) - len(errors),

        "errors": errors,
        "status": "success" if not errors else (
            "partial" if len(errors) < len(scenario["turns"])
            else "failed"
        ),
    }


# ---------------------------------------------------------------------
# Run one scenario across ALL levels
# ---------------------------------------------------------------------


async def run_instance(
    scenario: dict[str, Any],
    run_id: str,
    index: int,
) -> dict[str, Any]:

    # Generate one set of secrets shared across all three level runs.
    session_secrets = generate_session_secrets()

    all_secrets = [
        session_secrets[level_number]
        for level_number in LEVELS
    ]

    # Each scenario is executed independently on every level.
    level_results: dict[int, dict[str, Any]] = {}

    for level in LEVELS:
        print(f"    Running on Level {level}...")

        level_result = await run_level_instance(
            scenario=scenario,
            level=level,
            session_secrets=session_secrets,
            all_secrets=all_secrets,
        )

        level_results[level] = level_result

        print(
            f"      Status: {level_result['status']} | "
            f"Tokens: {level_result['total_tokens']} | "
            f"Latency: {level_result['latency_seconds']}s | "
            f"Lookup calls: {level_result['lookup_employee_call_count']} | "
            f"Secret calls: {level_result['get_level_secret_call_count']}"
        )

    # -----------------------------------------------------------------
    # Prepare one dialogue column for each level
    # -----------------------------------------------------------------

    dialogue_columns = {
        "L1_Player_Robot": level_results[1]["dialogue"],
        "L2_Player_Robot": level_results[2]["dialogue"],
        "L3_Player_Robot": level_results[3]["dialogue"],
    }

    # -----------------------------------------------------------------
    # Overall scenario status
    # -----------------------------------------------------------------

    all_errors = []

    for level in LEVELS:
        for error in level_results[level]["errors"]:
            all_errors.append(
                {
                    "level": level,
                    **error,
                }
            )

    successful_levels = sum(
        level_results[level]["status"] == "success"
        for level in LEVELS
    )

    if successful_levels == len(LEVELS):
        overall_status = "success"
    elif successful_levels > 0 or any(
        level_results[level]["status"] == "partial"
        for level in LEVELS
    ):
        overall_status = "partial"
    else:
        overall_status = "failed"

    # -----------------------------------------------------------------
    # Build final scenario result
    # -----------------------------------------------------------------

    result = {
        "run_id": run_id,
        "index": index,
        "instance_id": scenario["id"],

        # Original dataset metadata.
        "level": scenario["level"],
        "category": scenario["category"],
        "attack_type": scenario["attack_type"],
        "difficulty": scenario["difficulty"],
        "description": scenario.get("description", ""),
        "is_attack": scenario["is_attack"],
        "expected_success": scenario["expected_success"],
        "filter_bypass_test": scenario.get("filter_bypass_test"),

        # Store all three generated secrets separately.
        "L1_Secret": session_secrets[1],
        "L2_Secret": session_secrets[2],
        "L3_Secret": session_secrets[3],

        **dialogue_columns,

        # Execution results for each level.
        "level_results": level_results,

        # Total turns across all three executions.
        "turn_count": sum(
            level_results[level]["turn_count"]
            for level in LEVELS
        ),

        "completed_turn_count": sum(
            level_results[level]["completed_turn_count"]
            for level in LEVELS
        ),

        "status": overall_status,
        "successful_levels": successful_levels,
        "errors": all_errors,
        "timestamp_utc": utc_now(),
    }

    return result


# ---------------------------------------------------------------------
# CSV columns
# ---------------------------------------------------------------------


CSV_COLUMNS = [
    "Index",
    "Scenario_ID",
    "Level",
    "Category",
    "Attack_Type",
    "Difficulty",
    "Description",
    "Is_Attack",
    "Expected_Success",
    "L1_Secret",
    "L2_Secret",
    "L3_Secret",
    "Filter_Bypass_Test",
    "L1_Player_Robot",
    "L2_Player_Robot",
    "L3_Player_Robot",
]

# Each level gets its own execution columns.
for level in LEVELS:
    prefix = f"L{level}"

    CSV_COLUMNS.extend(
        [
            f"{prefix}_Input_Tokens",
            f"{prefix}_Output_Tokens",
            f"{prefix}_Total_Tokens",
            f"{prefix}_Requests",
            f"{prefix}_Latency_Seconds",
            f"{prefix}_Lookup_Employee_Called",
            f"{prefix}_Lookup_Employee_Call_Count",
            f"{prefix}_Lookup_Employee_Activity",
            f"{prefix}_Get_Level_Secret_Called",
            f"{prefix}_Get_Level_Secret_Call_Count",
            f"{prefix}_Model_Authorization",
            f"{prefix}_Final_Authorization",
            f"{prefix}_Status",
        ]
    )

CSV_COLUMNS.extend(
    [
        "Turn_Count",
        "Completed_Turn_Count",
        "Successful_Levels",
        "Status",
        "Errors",
        "Timestamp_UTC",
    ]
)


# ---------------------------------------------------------------------
# Convert one scenario into one table row
# ---------------------------------------------------------------------


def make_csv_row(
    result: dict[str, Any],
) -> dict[str, Any]:

    row: dict[str, Any] = {
        "Index": result["index"],
        "Scenario_ID": result["instance_id"],
        "Level": result["level"],
        "Category": result["category"],
        "Attack_Type": result["attack_type"],
        "Difficulty": result["difficulty"],
        "Description": result["description"],
        "Is_Attack": result["is_attack"],
        "Expected_Success": result["expected_success"],
        "L1_Secret": result["L1_Secret"],
        "L2_Secret": result["L2_Secret"],
        "L3_Secret": result["L3_Secret"],
        "Filter_Bypass_Test": result["filter_bypass_test"],
        "L1_Player_Robot": result["L1_Player_Robot"],
        "L2_Player_Robot": result["L2_Player_Robot"],
        "L3_Player_Robot": result["L3_Player_Robot"],
        "Turn_Count": result["turn_count"],
        "Completed_Turn_Count": result["completed_turn_count"],
        "Successful_Levels": result["successful_levels"],
        "Status": result["status"],
        "Errors": json_cell(result["errors"]),
        "Timestamp_UTC": result["timestamp_utc"],
    }

    # Fill execution columns for all three levels.
    for level in LEVELS:
        prefix = f"L{level}"
        level_result = result["level_results"][level]

        row.update(
            {
                f"{prefix}_Input_Tokens": level_result["input_tokens"],
                f"{prefix}_Output_Tokens": level_result["output_tokens"],
                f"{prefix}_Total_Tokens": level_result["total_tokens"],
                f"{prefix}_Requests": level_result["requests"],
                f"{prefix}_Latency_Seconds": level_result["latency_seconds"],
                f"{prefix}_Lookup_Employee_Called": (
                    level_result["lookup_employee_called"]
                ),
                f"{prefix}_Lookup_Employee_Call_Count": (
                    level_result["lookup_employee_call_count"]
                ),
                f"{prefix}_Lookup_Employee_Activity": json_cell(
                    level_result["lookup_employee_activity"]
                ),
                f"{prefix}_Get_Level_Secret_Called": (
                    level_result["get_level_secret_called"]
                ),
                f"{prefix}_Get_Level_Secret_Call_Count": (
                    level_result["get_level_secret_call_count"]
                ),
                f"{prefix}_Model_Authorization": json_cell(
                    level_result["model_authorization_values"]
                ),
                f"{prefix}_Final_Authorization": json_cell(
                    level_result["final_authorization_values"]
                ),
                f"{prefix}_Status": level_result["status"],
            }
        )

    return row


def generate_results_csv(
    results: list[dict[str, Any]],
    output_path: Path,
) -> None:

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=CSV_COLUMNS,
            extrasaction="ignore",
        )

        writer.writeheader()

        for result in results:
            writer.writerow(make_csv_row(result))


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


async def main() -> None:

    RESULTS_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_id = datetime.now().strftime(
        "run_%Y%m%d_%H%M%S"
    )

    run_directory = RESULTS_ROOT / run_id
    run_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_json_dump(
        str(run_directory / "environment.json"),
        get_environment_info(),
    )

    all_results: list[dict[str, Any]] = []

    total_executions = len(SCENARIOS) * len(LEVELS)

    print(f"\nStarting evaluation: {run_id}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print(f"Levels per scenario: {len(LEVELS)}")
    print(f"Total executions: {total_executions}")
    print("Execution mode: sequential")
    print("Results: one CSV row per scenario\n")

    for index, scenario in enumerate(
        SCENARIOS,
        start=1,
    ):

        print(
            f"[{index}/{len(SCENARIOS)}] "
            f"{scenario['id']} "
            f"(Dataset Level: {scenario['level']})"
        )

        result = await run_instance(
            scenario=scenario,
            run_id=run_id,
            index=index,
        )

        all_results.append(result)

        print(
            f"  Overall status: {result['status']} | "
            f"Successful levels: {result['successful_levels']}/{len(LEVELS)}"
        )

    # Main results table.
    results_path = run_directory / "results.csv"

    generate_results_csv(
        all_results,
        results_path,
    )

    # Summary contains run-level counts only.
    summary = {
        "run_id": run_id,
        "completed_at_utc": utc_now(),
        "total_scenarios": len(all_results),
        "levels_per_scenario": len(LEVELS),
        "total_executions": total_executions,
        "successful_scenarios": sum(
            item["status"] == "success"
            for item in all_results
        ),
        "partial_scenarios": sum(
            item["status"] == "partial"
            for item in all_results
        ),
        "failed_scenarios": sum(
            item["status"] == "failed"
            for item in all_results
        ),
        "results_file": "results.csv",
    }

    safe_json_dump(
        str(run_directory / "summary.json"),
        summary,
    )

    # Save errors separately.
    error_results = [
        {
            "index": item["index"],
            "instance_id": item["instance_id"],
            "errors": item["errors"],
        }
        for item in all_results
        if item["errors"]
    ]

    safe_json_dump(
        str(run_directory / "errors.json"),
        error_results,
    )

    print("\nRecording completed.")
    print(f"Total executions: {total_executions}")
    print(f"Results saved to: {results_path}")


if __name__ == "__main__":
    asyncio.run(main())
