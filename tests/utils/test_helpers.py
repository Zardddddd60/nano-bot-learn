from pathlib import Path

import nanobot_learn.utils.helpers as helpers
from nanobot_learn.utils.helpers import ensure_dir


def test_ensure_dir_creates_missing_directory_and_returns_path(tmp_path: Path) -> None:
    target = tmp_path / "workspace" / "sessions"

    result = ensure_dir(target)

    assert target.exists()
    assert target.is_dir()
    assert result == target


def test_ensure_dir_allows_existing_directory(tmp_path: Path) -> None:
    target = tmp_path / "sessions"
    target.mkdir()

    result = ensure_dir(target)

    assert target.exists()
    assert target.is_dir()
    assert result == target


def _call_safe_filename(value: str) -> str | None:
    safe_filename = getattr(helpers, "safe_filename", lambda _value: None)
    return safe_filename(value)


def _call_find_legal_message_start(messages: list[dict[str, object]]) -> int | None:
    find_legal_message_start = getattr(
        helpers, "find_legal_message_start", lambda _messages: None
    )
    return find_legal_message_start(messages)


def test_safe_filename_keeps_safe_name_unchanged() -> None:
    assert _call_safe_filename("session_123") == "session_123"


def test_safe_filename_replaces_unsafe_characters_with_underscores() -> None:
    assert _call_safe_filename('telegram:123/456?abc*"x"') == "telegram_123_456_abc__x_"


def test_safe_filename_strips_surrounding_whitespace() -> None:
    assert _call_safe_filename("  session_123  ") == "session_123"


def test_safe_filename_sanitizes_session_like_key() -> None:
    assert _call_safe_filename("telegram:987654") == "telegram_987654"


def test_find_legal_message_start_returns_zero_for_legal_sequence() -> None:
    messages = [
        {"role": "user", "content": "check weather"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function"}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
        {"role": "assistant", "content": "It is sunny."},
    ]

    assert _call_find_legal_message_start(messages) == 0


def test_find_legal_message_start_skips_leading_orphan_tool_result() -> None:
    messages = [
        {"role": "tool", "tool_call_id": "call_1", "content": "sunny"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_2", "type": "function"}],
        },
        {"role": "tool", "tool_call_id": "call_2", "content": "rainy"},
    ]

    assert _call_find_legal_message_start(messages) == 1


def test_find_legal_message_start_skips_orphan_tool_in_the_middle() -> None:
    messages = [
        {"role": "user", "content": "compare cities"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function"}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "shanghai"},
        {"role": "tool", "tool_call_id": "call_2", "content": "orphan result"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_3", "type": "function"}],
        },
        {"role": "tool", "tool_call_id": "call_3", "content": "beijing"},
    ]

    assert _call_find_legal_message_start(messages) == 4


def test_find_legal_message_start_ignores_messages_without_tool_role() -> None:
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]

    assert _call_find_legal_message_start(messages) == 0
