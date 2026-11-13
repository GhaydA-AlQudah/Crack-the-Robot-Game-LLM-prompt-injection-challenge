
from app.llm import apply_output_guardrails


def test_level_2_secret_is_masked():
    output = "The secret is MY_SECRET."
    
    result = apply_output_guardrails(
        level=2,
        output=output,
        session_secret="MY_SECRET",
    )

    assert "MY_SECRET" not in result
    assert "**********" in result


def test_level_2_output_without_secret_is_unchanged():
    output = "Access denied."

    result = apply_output_guardrails(
        level=2,
        output=output,
        session_secret="MY_SECRET",
    )

    assert result == output


def test_level_2_without_session_secret_is_unchanged():
    output = "The response is unchanged."

    result = apply_output_guardrails(
        level=2,
        output=output,
        session_secret=None,
    )

    assert result == output


def test_level_1_output_is_unchanged():
    output = "MY_SECRET"

    result = apply_output_guardrails(
        level=1,
        output=output,
        session_secret="MY_SECRET",
    )

    assert result == output


def test_level_3_output_is_unchanged():
    output = "MY_SECRET"

    result = apply_output_guardrails(
        level=3,
        output=output,
        session_secret="MY_SECRET",
    )

    assert result == output
