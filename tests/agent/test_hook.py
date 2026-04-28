from __future__ import annotations

import asyncio
from dataclasses import fields

import pytest

import nanobot_learn.agent.hook as hook_module
from nanobot_learn.agent.hook import AgentHook, AgentHookContext, CompositeHook
from nanobot_learn.providers.base import ToolCallRequest


def _run(coro):
    return asyncio.run(coro)


def _ctx() -> AgentHookContext:
    return AgentHookContext(iteration=0, messages=[])


def test_agent_hook_context_defaults_are_mutable_per_instance_and_slotted() -> None:
    first = AgentHookContext(iteration=1, messages=[{"role": "user", "content": "hi"}])
    second = AgentHookContext(iteration=2, messages=[])

    first.usage["prompt_tokens"] = 3
    first.tool_calls.append(ToolCallRequest(id="call_1", name="list_dir", arguments={}))
    first.streamed_content = True

    assert first.response is None
    assert first.streamed_content is True
    assert second.usage == {}
    assert second.tool_calls == []
    assert "streamed_content" in {field.name for field in fields(AgentHookContext)}
    with pytest.raises(AttributeError):
        first.unexpected_field = "blocked"


def test_agent_hook_base_is_instantiable_noop_and_supports_reraise_flag() -> None:
    hook = AgentHook(reraise=True)
    context = _ctx()

    assert hook._reraise is True
    assert hook.wants_streaming() is False
    _run(hook.before_iteration(context))
    _run(hook.on_stream(context, "delta"))
    _run(hook.on_stream_end(context, resuming=False))
    _run(hook.before_execute_tools(context))
    _run(hook.after_iteration(context))
    assert hook.finalize_content(context, "done") == "done"
    assert hook.finalize_content(context, None) is None


def test_composite_hook_fans_out_async_methods_in_order() -> None:
    events: list[str] = []

    class RecordingHook(AgentHook):
        def __init__(self, label: str) -> None:
            super().__init__()
            self.label = label

        async def before_iteration(self, context: AgentHookContext) -> None:
            events.append(f"{self.label}:before_iteration:{context.iteration}")

        async def on_stream(self, context: AgentHookContext, delta: str) -> None:
            events.append(f"{self.label}:on_stream:{delta}")

        async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None:
            events.append(f"{self.label}:on_stream_end:{resuming}")

        async def before_execute_tools(self, context: AgentHookContext) -> None:
            events.append(f"{self.label}:before_execute_tools")

        async def after_iteration(self, context: AgentHookContext) -> None:
            events.append(f"{self.label}:after_iteration")

    hook = CompositeHook([RecordingHook("A"), RecordingHook("B")])
    context = _ctx()

    _run(hook.before_iteration(context))
    _run(hook.on_stream(context, "delta"))
    _run(hook.on_stream_end(context, resuming=True))
    _run(hook.before_execute_tools(context))
    _run(hook.after_iteration(context))

    assert events == [
        "A:before_iteration:0",
        "B:before_iteration:0",
        "A:on_stream:delta",
        "B:on_stream:delta",
        "A:on_stream_end:True",
        "B:on_stream_end:True",
        "A:before_execute_tools",
        "B:before_execute_tools",
        "A:after_iteration",
        "B:after_iteration",
    ]


def test_composite_hook_uses_any_semantics_for_streaming() -> None:
    class StreamingHook(AgentHook):
        def wants_streaming(self) -> bool:
            return True

    assert CompositeHook([AgentHook(), StreamingHook()]).wants_streaming() is True
    assert CompositeHook([AgentHook(), AgentHook()]).wants_streaming() is False
    assert CompositeHook([]).wants_streaming() is False


def test_composite_hook_isolates_async_errors_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hook_module.logger, "exception", lambda *args, **kwargs: None)
    calls: list[str] = []

    class BadHook(AgentHook):
        async def before_iteration(self, context: AgentHookContext) -> None:
            raise RuntimeError("boom")

    class GoodHook(AgentHook):
        async def before_iteration(self, context: AgentHookContext) -> None:
            calls.append("good")

    _run(CompositeHook([BadHook(), GoodHook()]).before_iteration(_ctx()))

    assert calls == ["good"]


def test_composite_hook_reraises_when_hook_opts_in() -> None:
    class BadHook(AgentHook):
        def __init__(self) -> None:
            super().__init__(reraise=True)

        async def before_iteration(self, context: AgentHookContext) -> None:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _run(CompositeHook([BadHook()]).before_iteration(_ctx()))


def test_composite_hook_finalize_content_is_a_pipeline() -> None:
    class UpperHook(AgentHook):
        def finalize_content(
            self,
            context: AgentHookContext,
            content: str | None,
        ) -> str | None:
            return content.upper() if content else content

    class SuffixHook(AgentHook):
        def finalize_content(
            self,
            context: AgentHookContext,
            content: str | None,
        ) -> str | None:
            return f"{content}!" if content else content

    hook = CompositeHook([UpperHook(), SuffixHook()])

    assert hook.finalize_content(_ctx(), "hello") == "HELLO!"
    assert hook.finalize_content(_ctx(), None) is None
