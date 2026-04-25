from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from nanobot_learn.providers.base import (
    FinishReason,
    GenerationSettings,
    LLMProvider,
    LLMResponse,
    RetryMode,
    ToolCallRequest,
)


class ScriptedProvider(LLMProvider):
    """Provider test double that returns scripted responses from chat()."""

    def __init__(self, responses: list[LLMResponse]):
        super().__init__()
        self.responses = list(responses)
        self.calls = 0
        self.last_kwargs: dict[str, Any] = {}

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls += 1
        self.last_kwargs = {
            "messages": messages,
            "tools": tools,
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning_effort": reasoning_effort,
            "tool_choice": tool_choice,
        }
        if not self.responses:
            return LLMResponse(content="ok")
        return self.responses.pop(0)

    def get_default_model(self) -> str:
        return "fake-model"


def _openai_tool(name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def test_tool_call_request_serializes_openai_style_payload() -> None:
    request = ToolCallRequest(
        id="call_1",
        name="search",
        arguments={"query": "中文"},
        extra_content={"google": {"thought_signature": "sig"}},
        provider_specific_fields={"outer": "value"},
        function_provider_specific_fields={"inner": "value"},
    )

    payload = request.to_openai_tool_call()

    assert payload == {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": "search",
            "arguments": '{"query": "中文"}',
            "provider_specific_fields": {"inner": "value"},
        },
        "extra_content": {"google": {"thought_signature": "sig"}},
        "provider_specific_fields": {"outer": "value"},
    }


def test_llm_response_executes_tools_only_for_safe_finish_reasons() -> None:
    tool_call = ToolCallRequest(id="call_1", name="read_file", arguments={"path": "a.txt"})

    assert LLMResponse(content=None, tool_calls=[tool_call]).should_execute_tools
    assert LLMResponse(
        content=None,
        tool_calls=[tool_call],
        finish_reason=FinishReason.TOOL_CALLS,
    ).should_execute_tools
    assert not LLMResponse(
        content=None,
        tool_calls=[tool_call],
        finish_reason=FinishReason.ERROR,
    ).should_execute_tools
    assert not LLMResponse(content="no tools").should_execute_tools


def test_generation_settings_are_frozen() -> None:
    settings = GenerationSettings()

    with pytest.raises(FrozenInstanceError):
        settings.temperature = 1.0


def test_sanitize_empty_content_normalizes_provider_unsafe_messages() -> None:
    messages = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1"}]},
        {"role": "user", "content": [{"type": "text", "text": ""}]},
        {"role": "user", "content": {"type": "text", "text": "wrapped"}},
        {"role": "user", "content": [{"type": "text", "text": "ok", "_meta": {"x": 1}}]},
    ]

    sanitized = LLMProvider._sanitize_empty_content(messages)

    assert sanitized == [
        {"role": "user", "content": "(empty)"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1"}]},
        {"role": "user", "content": "(empty)"},
        {"role": "user", "content": [{"type": "text", "text": "wrapped"}]},
        {"role": "user", "content": [{"type": "text", "text": "ok"}]},
    ]


def test_tool_cache_marker_indices_mark_builtin_boundary_and_tail() -> None:
    tools = [
        _openai_tool("read_file"),
        _openai_tool("write_file"),
        _openai_tool("mcp_fs_list"),
        _openai_tool("mcp_git_status"),
    ]

    assert LLMProvider._tool_cache_marker_indices(tools) == [1, 3]


def test_tool_cache_marker_indices_mark_only_tail_without_mcp_tools() -> None:
    tools = [_openai_tool("read_file"), _openai_tool("write_file")]

    assert LLMProvider._tool_cache_marker_indices(tools) == [1]


def test_429_quota_errors_are_not_transient() -> None:
    response = LLMResponse(
        content="Error: exceeded your current quota",
        finish_reason=FinishReason.ERROR,
        error_status_code=429,
    )

    assert not LLMProvider._is_transient_response(response)


def test_structured_transient_metadata_takes_precedence() -> None:
    assert LLMProvider._is_transient_response(
        LLMResponse(content=None, finish_reason=FinishReason.ERROR, error_should_retry=True)
    )
    assert not LLMProvider._is_transient_response(
        LLMResponse(
            content="429 rate limit",
            finish_reason=FinishReason.ERROR,
            error_should_retry=False,
        )
    )
    assert LLMProvider._is_transient_response(
        LLMResponse(content="boom", finish_reason=FinishReason.ERROR, error_status_code=503)
    )
    assert LLMProvider._is_transient_response(
        LLMResponse(content="boom", finish_reason=FinishReason.ERROR, error_kind="timeout")
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("retry after 250ms", 0.25),
        ("try again in 2 seconds", 2.0),
        ("wait 1.5 min before retry", 90.0),
        ('{"retry_after": 3}', 3.0),
    ],
)
def test_extract_retry_after_parses_common_provider_messages(
    content: str,
    expected: float,
) -> None:
    assert LLMProvider._extract_retry_after(content) == expected


def test_chat_with_retry_uses_generation_defaults_for_omitted_and_none_values() -> None:
    provider = ScriptedProvider([LLMResponse(content="ok")])

    async def _run() -> LLMResponse:
        return await provider.chat_with_retry(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=None,
            temperature=None,
        )

    response = asyncio.run(_run())

    assert response.content == "ok"
    assert provider.last_kwargs["max_tokens"] == 4096
    assert provider.last_kwargs["temperature"] == 0.7
    assert provider.last_kwargs["reasoning_effort"] is None


def test_chat_with_retry_gives_up_after_standard_retries_without_progress_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(content="429 rate limit", finish_reason=FinishReason.ERROR),
            LLMResponse(content="429 rate limit", finish_reason=FinishReason.ERROR),
            LLMResponse(content="429 rate limit", finish_reason=FinishReason.ERROR),
            LLMResponse(content="429 rate limit", finish_reason=FinishReason.ERROR),
            LLMResponse(content="late success"),
        ]
    )
    delays: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("nanobot_learn.providers.base.asyncio.sleep", _fake_sleep)

    async def _run() -> LLMResponse:
        return await provider.chat_with_retry(messages=[{"role": "user", "content": "hello"}])

    response = asyncio.run(_run())

    assert response.finish_reason == FinishReason.ERROR
    assert response.content == "429 rate limit"
    assert provider.calls == 4
    assert delays == [1, 2, 4]


def test_persistent_retry_stops_after_identical_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ScriptedProvider(
        [LLMResponse(content="429 rate limit", finish_reason=FinishReason.ERROR) for _ in range(10)]
    )
    progress: list[str] = []

    async def _fake_sleep(_delay: float) -> None:
        return None

    async def _progress(message: str) -> None:
        progress.append(message)

    monkeypatch.setattr("nanobot_learn.providers.base.asyncio.sleep", _fake_sleep)

    async def _run() -> LLMResponse:
        return await provider.chat_with_retry(
            messages=[{"role": "user", "content": "hello"}],
            retry_mode=RetryMode.PERSISTENT,
            on_retry_wait=_progress,
        )

    response = asyncio.run(_run())

    assert response.finish_reason == FinishReason.ERROR
    assert provider.calls == 10
    assert progress[-1] == "Persistent retry stopped after 10 identical errors."


def test_non_transient_image_error_retries_without_images_and_mutates_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ScriptedProvider(
        [
            LLMResponse(content="image input unsupported", finish_reason=FinishReason.ERROR),
            LLMResponse(content="ok"),
        ]
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe"},
                {"type": "image_url", "image_url": {"url": "file:///tmp/a.png"}, "_meta": {"path": "a.png"}},
            ],
        }
    ]

    async def _fake_sleep(_delay: float) -> None:
        raise AssertionError("non-transient image fallback should not sleep")

    monkeypatch.setattr("nanobot_learn.providers.base.asyncio.sleep", _fake_sleep)

    async def _run() -> LLMResponse:
        return await provider.chat_with_retry(messages=messages)

    response = asyncio.run(_run())

    assert response.content == "ok"
    assert provider.calls == 2
    assert messages[0]["content"][1] == {"type": "text", "text": "[image: a.png]"}
