import json

from nanobot_learn.config.loader import load_config


def test_load_config_returns_defaults_when_file_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("NANOBOT_AGENTS__DEFAULTS__MODEL", raising=False)

    config = load_config(tmp_path / "missing.json")

    assert config.agents.defaults.model == "anthropic/claude-opus-4-5"


def test_load_config_reads_json_config_with_aliases(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"model": "openai/gpt-4.1"}},
                "providers": {"openai": {"apiKey": "sk-test"}},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.agents.defaults.model == "openai/gpt-4.1"
    assert config.get_api_key() == "sk-test"
