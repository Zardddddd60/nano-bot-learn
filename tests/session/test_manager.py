from importlib import import_module
import json
from pathlib import Path

from nanobot_learn.session.manager import Session, SessionManager


def _make_session_manager(workspace: Path):
    try:
        module = import_module("nanobot_learn.session.manager")
    except ModuleNotFoundError as exc:
        if exc.name in {"nanobot_learn.session", "nanobot_learn.session.manager"}:
            return None
        raise

    session_manager = getattr(module, "SessionManager", None)
    if session_manager is None:
        return None
    return session_manager(workspace)


def _call_safe_key(key: str) -> str | None:
    try:
        module = import_module("nanobot_learn.session.manager")
    except ModuleNotFoundError as exc:
        if exc.name in {"nanobot_learn.session", "nanobot_learn.session.manager"}:
            return None
        raise

    session_manager = getattr(module, "SessionManager", None)
    if session_manager is None:
        return None
    return session_manager.safe_key(key)


def test_session_manager_initializes_sessions_dir_under_workspace(
    monkeypatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    workspace = tmp_path / "workspace"

    manager = _make_session_manager(workspace)

    assert manager is not None
    assert manager.workspace == workspace
    assert manager.sessions_dir == workspace / "sessions"
    assert manager.sessions_dir.exists()
    assert manager.sessions_dir.is_dir()


def test_session_manager_initializes_legacy_sessions_dir_and_empty_cache(
    monkeypatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    workspace = tmp_path / "workspace"

    manager = _make_session_manager(workspace)
    expected = fake_home / ".nanobot" / "sessions"

    assert manager is not None
    assert manager.legacy_sessions_dir == expected
    assert manager._cache == {}


def test_session_manager_safe_key_replaces_colon_and_unsafe_characters() -> None:
    assert _call_safe_key("telegram:123/456?abc") == "telegram_123_456_abc"


def test_session_manager_get_session_path_returns_jsonl_path_in_sessions_dir(
    monkeypatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    workspace = tmp_path / "workspace"

    manager = _make_session_manager(workspace)
    expected = workspace / "sessions" / "telegram_123_456.jsonl"

    assert manager is not None
    assert manager._get_session_path("telegram:123/456") == expected


def test_get_or_create_returns_cached_session_instance(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)

    first = manager.get_or_create("telegram:abc")
    second = manager.get_or_create("telegram:abc")

    assert first is second
    assert first.key == "telegram:abc"


def test_save_round_trips_session_messages_and_metadata(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = Session(key="telegram:abc")
    session.metadata = {"channel": "telegram"}
    session.last_consolidated = 1
    session.add_message("user", "hello")
    session.add_message("assistant", "hi")

    manager.save(session)
    manager.invalidate("telegram:abc")
    reloaded = manager.get_or_create("telegram:abc")

    assert [message["role"] for message in reloaded.messages] == ["user", "assistant"]
    assert reloaded.metadata == {"channel": "telegram"}
    assert reloaded.last_consolidated == 1


def test_save_writes_metadata_line_to_jsonl_file(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = Session(key="telegram:abc")
    session.add_message("user", "hello")

    manager.save(session)

    lines = (
        manager._get_session_path("telegram:abc").read_text(encoding="utf-8").strip().splitlines()
    )
    metadata = json.loads(lines[0])
    assert metadata["_type"] == "metadata"
    assert metadata["key"] == "telegram:abc"
    assert json.loads(lines[1])["content"] == "hello"


def test_delete_session_removes_file_and_invalidates_cache(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = Session(key="telegram:abc")
    session.add_message("user", "hello")
    manager.save(session)
    cached = manager.get_or_create("telegram:abc")
    assert cached.messages

    deleted = manager.delete_session("telegram:abc")
    fresh = manager.get_or_create("telegram:abc")

    assert deleted is True
    assert not manager._get_session_path("telegram:abc").exists()
    assert fresh.messages == []


def test_read_session_file_returns_payload_without_populating_cache(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = Session(key="telegram:abc")
    session.add_message("user", "hello")
    session.add_message("assistant", "hi")
    manager.save(session)
    manager.invalidate("telegram:abc")

    payload = manager.read_session_file("telegram:abc")

    assert payload is not None
    assert payload["key"] == "telegram:abc"
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
    assert "telegram:abc" not in manager._cache


def test_list_sessions_returns_saved_sessions_sorted_by_updated_at(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    older = Session(key="telegram:older")
    older.updated_at = older.updated_at.replace(year=2020)
    manager.save(older)

    newer = Session(key="telegram:newer")
    newer.updated_at = newer.updated_at.replace(year=2021)
    manager.save(newer)

    sessions = manager.list_sessions()

    assert [item["key"] for item in sessions] == ["telegram:newer", "telegram:older"]
