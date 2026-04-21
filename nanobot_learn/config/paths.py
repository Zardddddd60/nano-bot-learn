"""Path helpers used by the learning package."""

from pathlib import Path


def get_legacy_sessions_dir() -> Path:
    """Return the legacy nanobot sessions directory path under the user's home."""
    return Path.home() / ".nanobot" / "sessions"
