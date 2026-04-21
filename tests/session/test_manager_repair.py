import json
from datetime import datetime
from pathlib import Path

from nanobot_learn.session.manager import SessionManager


def _write_jsonl(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_load_migrates_legacy_session_file(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    manager = SessionManager(tmp_path / "workspace")
    legacy_path = manager._get_legacy_session_path("telegram:abc")
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        legacy_path,
        [
            json.dumps(
                {
                    "_type": "metadata",
                    "key": "telegram:abc",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "metadata": {},
                    "last_consolidated": 0,
                }
            ),
            json.dumps({"role": "user", "content": "hello"}),
        ],
    )

    session = manager._load("telegram:abc")

    assert session is not None
    assert session.messages == [{"role": "user", "content": "hello"}]
    assert manager._get_session_path("telegram:abc").exists()
    assert not legacy_path.exists()


def test_load_recovers_valid_messages_from_corrupt_jsonl(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    path = manager._get_session_path("telegram:abc")
    _write_jsonl(
        path,
        [
            json.dumps(
                {
                    "_type": "metadata",
                    "key": "telegram:abc",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "metadata": {"source": "repair"},
                    "last_consolidated": 0,
                }
            ),
            json.dumps({"role": "user", "content": "hello"}),
            '{"role": "assistant", "content": "partial...',
        ],
    )

    session = manager._load("telegram:abc")

    assert session is not None
    assert session.metadata == {"source": "repair"}
    assert session.messages == [{"role": "user", "content": "hello"}]


def test_read_session_file_returns_repaired_payload_for_corrupt_jsonl(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    path = manager._get_session_path("telegram:abc")
    _write_jsonl(
        path,
        [
            json.dumps(
                {
                    "_type": "metadata",
                    "key": "telegram:abc",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "metadata": {"source": "repair"},
                    "last_consolidated": 0,
                }
            ),
            json.dumps({"role": "user", "content": "hello"}),
            '{"role": "assistant", "content": "partial...',
        ],
    )

    payload = manager.read_session_file("telegram:abc")

    assert payload is not None
    assert payload["key"] == "telegram:abc"
    assert payload["metadata"] == {"source": "repair"}
    assert payload["messages"] == [{"role": "user", "content": "hello"}]


def test_list_sessions_keeps_repaired_corrupt_file(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    path = manager._get_session_path("telegram:abc")
    _write_jsonl(
        path,
        [
            "NOT VALID JSON",
            json.dumps(
                {
                    "_type": "metadata",
                    "key": "telegram:abc",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "metadata": {},
                    "last_consolidated": 0,
                }
            ),
            json.dumps({"role": "user", "content": "hello"}),
        ],
    )

    sessions = manager.list_sessions()

    assert any(item["key"] == "telegram:abc" for item in sessions)
