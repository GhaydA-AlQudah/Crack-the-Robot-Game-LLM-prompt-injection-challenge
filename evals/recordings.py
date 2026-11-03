from __future__ import annotations

from typing import Any

from evals.leak_judge import judge_leak


async def make_response_record(
    *,
    session_id: str,
    level: int,
    final_output: str,
    expected_secret: str,
    tool_calls: int,
    authorization_true_tool_calls: int,
    final_authorization: bool,
    model_authorization_true_seen: bool,
) -> dict[str, Any]:
    judgment = await judge_leak(
        session_id=session_id,
        level=level,
        final_output=final_output,
        expected_secret=expected_secret,
    )

    return {
        "session_id": session_id,
        "level": level,
        "tool_calls": tool_calls,
        "authorization_true_tool_calls": authorization_true_tool_calls,
        "final_authorization": final_authorization,
        "model_authorization_true_seen": model_authorization_true_seen,
        "leak_judged": True,
        "secret_leaked": judgment.leaked,
        "leak_judge": judgment.to_dict(),
    }