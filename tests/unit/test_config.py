
from app.llm import (
    load_config,
    load_prompt,
    GAME_DIR,
)


def test_all_level_configs_load():
    for level in (1, 2, 3):
        config = load_config(level)

        assert isinstance(config, dict)


def test_all_level_prompts_load():
    for level in (1, 2, 3):
        prompt = load_prompt(level)

        assert isinstance(prompt, str)
        assert prompt.strip()


def test_level_configs_contain_valid_settings():
    for level in (1, 2, 3):
        config = load_config(level)

        if "temperature" in config:
            assert isinstance(config["temperature"], (int, float))
            assert 0 <= config["temperature"] <= 2

        if "max_tokens" in config:
            assert isinstance(config["max_tokens"], int)
            assert config["max_tokens"] > 0


def test_level_directories_exist():
    for level in (1, 2, 3):
        level_dir = GAME_DIR / f"level{level}"

        assert level_dir.is_dir()
        assert (level_dir / "config.yaml").is_file()
        assert (level_dir / "prompt.txt").is_file()
