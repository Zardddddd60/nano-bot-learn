from pathlib import Path

from nanobot_learn.config.schema import Config, DreamConfig
from nanobot_learn.providers.registry import find_by_name


def test_provider_registry_lives_under_providers_package() -> None:
    spec = find_by_name("openrouter")

    assert spec is not None
    assert spec.name == "openrouter"
    assert spec.default_api_base == "https://openrouter.ai/api/v1"


def test_config_defaults_expose_nested_sections() -> None:
    config = Config(_env_prefix="NANOBOT_LEARN_TEST_")

    assert config.agents.defaults.workspace == "~/.nanobot/workspace"
    assert config.channels.send_progress is True
    assert config.providers.custom.api_key is None
    assert config.tools.web.enable is True
    assert config.workspace_path == Path("~/.nanobot/workspace").expanduser()


def test_config_accepts_camel_case_aliases_and_serializes_preferred_names() -> None:
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "idleCompactAfterMinutes": 30,
                    "consolidationRatio": 0.3,
                    "dream": {"modelOverride": "openrouter/sonnet"},
                }
            },
            "tools": {
                "restrictToWorkspace": True,
                "mcpServers": {
                    "filesystem": {
                        "command": "npx",
                        "enabledTools": ["list"],
                    }
                },
            },
        }
    )

    assert config.agents.defaults.session_ttl_minutes == 30
    assert config.agents.defaults.consolidation_ratio == 0.3
    assert config.agents.defaults.dream.model_override == "openrouter/sonnet"
    assert config.tools.restrict_to_workspace is True
    assert config.tools.mcp_servers["filesystem"].enabled_tools == ["list"]

    dumped = config.model_dump(mode="json", by_alias=True)
    assert dumped["agents"]["defaults"]["idleCompactAfterMinutes"] == 30
    assert dumped["agents"]["defaults"]["consolidationRatio"] == 0.3
    assert dumped["tools"]["restrictToWorkspace"] is True
    assert dumped["tools"]["mcpServers"]["filesystem"]["enabledTools"] == ["list"]


def test_config_reads_nested_nanobot_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("NANOBOT_AGENTS__DEFAULTS__MODEL", "openai/gpt-4.1")
    monkeypatch.setenv("NANOBOT_PROVIDERS__OPENAI__API_KEY", "sk-test")
    monkeypatch.setenv("NANOBOT_TOOLS__WEB__ENABLE", "false")

    config = Config()

    assert config.agents.defaults.model == "openai/gpt-4.1"
    assert config.providers.openai.api_key == "sk-test"
    assert config.tools.web.enable is False


def test_config_matches_provider_by_model_prefix() -> None:
    config = Config.model_validate(
        {
            "agents": {"defaults": {"model": "openai/gpt-4.1"}},
            "providers": {"openai": {"apiKey": "sk-test"}},
        }
    )

    assert config.get_provider_name() == "openai"
    assert config.get_api_key() == "sk-test"
    assert config.get_provider().api_key == "sk-test"


def test_config_honors_forced_provider() -> None:
    config = Config.model_validate(
        {
            "agents": {"defaults": {"provider": "custom", "model": "anything"}},
            "providers": {"custom": {"apiKey": "custom-key", "apiBase": "https://api.example.test"}},
        }
    )

    assert config.get_provider_name() == "custom"
    assert config.get_api_key() == "custom-key"
    assert config.get_api_base() == "https://api.example.test"


def test_dream_config_aliases_and_schedule_description() -> None:
    config = DreamConfig.model_validate({"modelOverride": "openrouter/sonnet", "intervalH": 3})

    assert config.model_override == "openrouter/sonnet"
    assert config.describe_schedule() == "every 3h"
