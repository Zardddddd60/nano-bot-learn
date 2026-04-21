from nanobot_learn.session.manager import Session


def _assert_no_orphans(history: list[dict]) -> None:
    declared = {
        tc["id"]
        for message in history
        if message.get("role") == "assistant"
        for tc in (message.get("tool_calls") or [])
    }
    orphans = [
        message.get("tool_call_id")
        for message in history
        if message.get("role") == "tool" and message.get("tool_call_id") not in declared
    ]
    assert orphans == []


def _tool_turn(prefix: str, idx: int) -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": f"{prefix}_{idx}_a", "type": "function"},
                {"id": f"{prefix}_{idx}_b", "type": "function"},
            ],
        },
        {"role": "tool", "tool_call_id": f"{prefix}_{idx}_a", "name": "x", "content": "ok"},
        {"role": "tool", "tool_call_id": f"{prefix}_{idx}_b", "name": "y", "content": "ok"},
    ]


def test_add_message_appends_timestamped_message() -> None:
    session = Session(key="telegram:test")

    session.add_message("user", "hello", name="telegram")

    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hello"
    assert session.messages[0]["name"] == "telegram"
    assert "timestamp" in session.messages[0]


def test_get_history_drops_orphan_tool_results_when_window_cuts_tool_calls() -> None:
    session = Session(key="telegram:test")
    session.messages.append({"role": "user", "content": "old turn"})
    for i in range(20):
        session.messages.extend(_tool_turn("old", i))
    session.messages.append({"role": "user", "content": "problem turn"})
    for i in range(25):
        session.messages.extend(_tool_turn("cur", i))
    session.messages.append({"role": "user", "content": "new telegram question"})

    history = session.get_history(max_messages=100)

    _assert_no_orphans(history)
    assert history[0]["role"] == "user"


def test_get_history_preserves_reasoning_content() -> None:
    session = Session(key="telegram:reasoning")
    session.messages.append({"role": "user", "content": "hi"})
    session.messages.append(
        {
            "role": "assistant",
            "content": "done",
            "reasoning_content": "hidden chain of thought",
        }
    )

    history = session.get_history(max_messages=500)

    assert history == [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "done",
            "reasoning_content": "hidden chain of thought",
        },
    ]


def test_retain_recent_legal_suffix_zero_clears_session() -> None:
    session = Session(key="telegram:trim-zero")
    for i in range(10):
        session.messages.append({"role": "user", "content": f"msg{i}"})
    session.last_consolidated = 5

    session.retain_recent_legal_suffix(0)

    assert session.messages == []
    assert session.last_consolidated == 0


def test_retain_recent_legal_suffix_adjusts_last_consolidated() -> None:
    session = Session(key="telegram:trim-cons")
    for i in range(10):
        session.messages.append({"role": "user", "content": f"msg{i}"})
    session.last_consolidated = 7

    session.retain_recent_legal_suffix(4)

    assert len(session.messages) == 4
    assert session.messages[0]["content"] == "msg6"
    assert session.last_consolidated == 1


def test_retain_recent_legal_suffix_keeps_legal_tool_boundary() -> None:
    session = Session(key="telegram:trim-tools")
    session.messages.append({"role": "user", "content": "old"})
    session.messages.extend(_tool_turn("old", 0))
    session.messages.append({"role": "user", "content": "keep"})
    session.messages.extend(_tool_turn("keep", 0))
    session.messages.append({"role": "assistant", "content": "done"})

    session.retain_recent_legal_suffix(4)
    history = session.get_history(max_messages=500)

    _assert_no_orphans(history)
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "keep"
