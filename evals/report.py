from __future__ import annotations

from typing import Any


def format_rate(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def print_table(
    title: str,
    rows: dict[str, dict[str, Any]],
) -> None:
    print(f"\n{title}")
    print("=" * len(title))

    if not rows:
        print("No data.")
        return

    for key, data in rows.items():
        print(f"\n{key}")
        print(f"  Response turns: {data['response_turns']}")
        print(f"  Tool calls: {data['tool_calls']}")
        print(
            "  Responses with tool call: "
            f"{data['responses_with_tool_call']} "
            f"({format_rate(data['tool_call_rate'])})"
        )
        print(
            "  No-tool-call responses: "
            f"{data['no_tool_call_responses']} "
            f"({format_rate(data['no_tool_call_rate'])})"
        )
        print(
            "  authorization=True tool calls: "
            f"{data['authorization_true_tool_calls']} "
            f"({format_rate(data['authorization_true_rate'])})"
        )
        print(
            "  Actual leaks: "
            f"{data['leaked_responses']}/"
            f"{data['judge_evaluated_responses']} "
            f"({format_rate(data['leak_rate'])})"
        )


def print_security_metrics(aggregate: dict[str, Any]) -> None:
    print_table("SECURITY METRICS BY LEVEL", aggregate.get("by_level", {}))
    print_table("SECURITY METRICS BY SESSION", aggregate.get("by_session", {}))


from typing import Any


def print_report(result: dict[str, Any]) -> None:
    """Print the main evaluation summary."""
    metrics = result.get("metrics", {})

    print("\n" + "=" * 60)
    print("EVALUATION REPORT")
    print("=" * 60)

    print(f"Total trials: {metrics.get('trial_count', 0)}")
    print(f"Attack trials: {metrics.get('attack_count', 0)}")
    print(f"Benign trials: {metrics.get('benign_count', 0)}")

    attack_rate = metrics.get("attack_success_rate")
    benign_rate = metrics.get("benign_success_rate")

    print(
        "Attack success rate: "
        + (f"{attack_rate * 100:.2f}%" if attack_rate is not None else "N/A")
    )
    print(
        "Benign success rate: "
        + (f"{benign_rate * 100:.2f}%" if benign_rate is not None else "N/A")
    )

    print(f"Average latency: {metrics.get('average_latency_ms', 'N/A')} ms")
    print(
        "Average model latency: "
        f"{metrics.get('average_model_latency_ms', 'N/A')} ms"
    )
    print(f"Input tokens: {metrics.get('total_input_tokens', 0)}")
    print(f"Output tokens: {metrics.get('total_output_tokens', 0)}")
    print(f"Total tokens: {metrics.get('total_tokens', 0)}")
    print(f"Estimated cost: ${metrics.get('total_cost_usd', 0):.8f}")
    print("=" * 60)