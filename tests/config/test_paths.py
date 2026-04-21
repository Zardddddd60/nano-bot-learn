from importlib import import_module
from pathlib import Path


def _call_get_legacy_sessions_dir() -> Path | None:
    try:
        module = import_module("nanobot_learn.config.paths")
    except ModuleNotFoundError:
        return None

    get_legacy_sessions_dir = getattr(module, "get_legacy_sessions_dir", lambda: None)
    return get_legacy_sessions_dir()


def test_get_legacy_sessions_dir_returns_nanobot_sessions_path_under_home(
    monkeypatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    result = _call_get_legacy_sessions_dir()
    expected = fake_home / ".nanobot" / "sessions"

    assert result == expected


def test_get_legacy_sessions_dir_does_not_create_directory(
    monkeypatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    result = _call_get_legacy_sessions_dir()
    expected = fake_home / ".nanobot" / "sessions"

    assert result == expected
    assert not expected.exists()
