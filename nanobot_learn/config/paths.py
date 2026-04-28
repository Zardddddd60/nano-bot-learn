"""Path helpers used by the learning package."""

from pathlib import Path

from nanobot_learn.config.loader import get_config_path
from nanobot_learn.utils.helpers import ensure_dir

def get_data_dir() -> Path:
    """
    Return the instance-level runtime data directory."
    """

    return ensure_dir(get_config_path().parent)

# ~/.nanobot/{name}
def get_runtime_subdir(name: str) -> Path:
    """
    Return a named runtime subdirectory under the instance data dir.
    """

    return ensure_dir(get_data_dir() / name)

# ~/.nanobot/media/{channel}
def get_media_dir(channel: str | None = None) -> Path:
    """
    Return the media directory, optionally namespaced per channel.
    """

    base = get_runtime_subdir("media")
    return ensure_dir(base / channel) if channel else base

# ~/.nanobot/cron
def get_cron_dir() -> Path:
    """
    Return the cron storage directory.
    """

    return get_runtime_subdir("cron")

# ~/.nanobot/logs
def get_logs_dir() -> Path:
    """
    Return the logs directory.
    """

    return get_runtime_subdir("logs")

def get_workspace_path(workspace: str | None = None) -> Path:
    """
    Resolve and ensure the agent workspace path.
    """

    path = Path(workspace).expanduser() if workspace else Path.home() / ".nanobot" / "workspace"
    return ensure_dir(path)

def is_default_workspace(workspace: str | Path | None) -> bool:
    """
    Return whether a workspace resolves to nanobot's default workspace path.
    """

    # "~/.nanobot/workspace" -> "/Users/xxx/.nanobot/workspace"
    default =  Path.home() / ".nanobot" / "workspace"
    current = Path(workspace).expanduser() if workspace is not None else  Path.home() / ".nanobot" / "workspace"
    # strict: 解析路径时，路径必须已经存在吗？
    return current.resolve(strict=False) == default.resolve(strict=False)

# ~/.nanobot/history/cli_history
def get_cli_history_path() -> Path:
    """
    Return the shared CLI history file path.
    """

    return Path.home() / ".nanobot" / "history" / "cli_history"

# ~/.nanobot/bridge
def get_bridge_install_dir() -> Path:
    """
    Return the shared WhatsApp bridge installation directory.
    """
    return Path.home() / ".nanobot" / "bridge"

# ~/.nanobot/sessions
def get_legacy_sessions_dir() -> Path:
    """
    Return the legacy nanobot sessions directory path under the user's home.
    """

    return Path.home() / ".nanobot" / "sessions"
