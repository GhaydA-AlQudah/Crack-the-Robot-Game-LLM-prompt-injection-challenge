
import pytest

from app.llm import extract_flag
from app.game.secret_generator import generate_session_secrets


def test_generate_session_secrets():
    secrets = generate_session_secrets()

    assert isinstance(secrets, dict)
    assert set(secrets.keys()) == {1, 2, 3}

    for secret in secrets.values():
        assert isinstance(secret, str)
        assert secret.strip()


def test_extract_flag_returns_correct_secret():
    secrets = {
        1: "SECRET_1",
        2: "SECRET_2",
        3: "SECRET_3",
    }

    assert extract_flag(1, secrets) == "SECRET_1"
    assert extract_flag(2, secrets) == "SECRET_2"
    assert extract_flag(3, secrets) == "SECRET_3"


@pytest.mark.parametrize("level", [0, 4, -1])
def test_extract_flag_rejects_invalid_level(level):
    with pytest.raises(ValueError, match="Invalid level"):
        extract_flag(level, {1: "SECRET_1", 2: "SECRET_2", 3: "SECRET_3"})


def test_extract_flag_rejects_missing_session_secrets():
    with pytest.raises(ValueError, match="Session secret missing"):
        extract_flag(1, None)


def test_extract_flag_rejects_missing_level_secret():
    with pytest.raises(ValueError, match="Session secret missing"):
        extract_flag(2, {1: "SECRET_1"})
