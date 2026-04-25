"""Base LLM provider interface."""

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
import json
import re
from typing import Any, Awaitable, Callable

from loguru import logger

from nanobot_learn.utils.helpers import image_placeholder_text

class FinishReason(StrEnum):
  STOP = "stop"
  TOOL_CALLS = "tool_calls"
  ERROR = "error"
  # 字符串转enum，如果字符串不在枚举里，会抛 ValueError，可以写一个fallback函数，报错转成STOP
  # finish_reason = FinishReason(raw_finish_reason)

class RetryMode(StrEnum):
  STANDARD = "standard"
  PERSISTENT = "persistent"

@dataclass
class ToolCallRequest:
  """A tool call request from the LLM."""
  id: str
  name: str
  arguments: dict[str, Any]
  extra_content: dict[str, Any] | None = None
  provider_specific_fields: dict[str, Any] | None = None
  function_provider_specific_fields: dict[str, Any] | None = None

  def to_openai_tool_call(self) -> dict[str, Any]:
    """Serialize to an OpenAI-style tool_call payload."""
    tool_call = {
      "id": self.id,
      "type": "function",
      "function": {
        "name": self.name,
        # 序列化成 JSON 字符串
        # ensure_ascii=False：中文不会被转成 \u4e2d\u6587
        "arguments": json.dumps(self.arguments, ensure_ascii=False)
      },
    }

    if self.extra_content:
      tool_call["extra_content"] = self.extra_content
    
    if self.provider_specific_fields:
      tool_call["provider_specific_fields"] = self.provider_specific_fields
    
    if self.function_provider_specific_fields:
      tool_call["function"]["provider_specific_fields"] = self.function_provider_specific_fields

    return tool_call
  
@dataclass
class LLMResponse:
  """Response from an LLM provider."""
  content: str | None
  tool_calls: list[ToolCallRequest] = field(default_factory=list)
  finish_reason: FinishReason = FinishReason.STOP
  usage: dict[str, int] = field(default_factory=dict)
  retry_after: float | None = None
  # Provider supplied retry wait in seconds
  reasoning_content: str | None = None
  # Kimi, DeepSeek-R1, Mimo etc.
  thinking_blocks: list[dict] | None = None
  # Structured error metadata used by retry policy when finish_reason == "error".
  error_status_code: int | None = None
  error_kind: str | None = None # "timeout" "connection"
  error_type: str | None = None # Provider/type semantic, e.g. insufficient_quote
  error_code: str | None = None # Provider/code semantic, e.g. rate_limit_exceeded
  error_retry_after_s: float | None = None
  error_should_retry: bool | None = None

  @property
  def has_tool_calls(self) -> bool:
    """Check if response contains tool calls."""
    return len(self.tool_calls) > 0
  
  @property
  def should_execute_tools(self) -> bool:
    """Tools execute only when has_tool_calls AND finish_reason is ``tool_calls`` / ``stop``.
        Blocks gateway-injected calls under ``refusal`` / ``content_filter`` / ``error``."""
    return self.has_tool_calls and self.finish_reason in (FinishReason.STOP, FinishReason.TOOL_CALLS)

@dataclass(frozen=True) # 实例创建后，字段不能再被重新赋值
class GenerationSettings:
  """Default generation settings."""

  temperature: float = 0.7
  max_tokens: int = 4096
  reasoning_effort: str | None = None

_SYNTHETIC_USER_CONTENT = "(conversation continued)"

class LLMProvider(ABC):
  """Base class for LLM providers."""
  _CHAT_RETRY_DELAYS = (1, 2, 4)
  _PERSISTENT_MAX_DELAY = 60
  _PERSISTENT_IDENTICAL_ERROR_LIMIT = 10
  _RETRY_HEARTBEAT_CHUNK = 30
  _TRANSIENT_ERROR_MARKERS = (
    "429",
    "rate limit",
    "500",
    "502",
    "503",
    "504",
    "overloaded",
    "timeout",
    "timed out",
    "connection",
    "server error",
    "temporarily unavailable",
    "速率限制",
  )
  _RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})
  _TRANSIENT_ERROR_KINDS = frozenset({"timeout", "connection"})
  _NON_RETRYABLE_429_ERROR_TOKENS = frozenset({
    "insufficient_quota",
    "quota_exceeded",
    "quota_exhausted",
    "billing_hard_limit_reached",
    "insufficient_balance",
    "credit_balance_too_low",
    "billing_not_active",
    "payment_required",
  })
  _RETRYABLE_429_ERROR_TOKENS = frozenset({
    "rate_limit_exceeded",
    "rate_limit_error",
    "too_many_requests",
    "request_limit_exceeded",
    "requests_limit_exceeded",
    "overloaded_error",
  })
  _NON_RETRYABLE_429_TEXT_MARKERS = (
    "insufficient_quota",
    "insufficient quota",
    "quota exceeded",
    "quota exhausted",
    "billing hard limit",
    "billing_hard_limit_reached",
    "billing not active",
    "insufficient balance",
    "insufficient_balance",
    "credit balance too low",
    "payment required",
    "out of credits",
    "out of quota",
    "exceeded your current quota",
  )
  _RETRYABLE_429_TEXT_MARKERS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "retry after",
    "try again in",
    "temporarily unavailable",
    "overloaded",
    "concurrency limit",
    "速率限制",
  )

  # 是一个“特殊占位值”，用来表示：调用方没有传这个参数
  # 不用None是因为None可能有业务属性
  # if value is _SENTINEL:
  _SENTINEL = object()

  def __init__(self, api_key: str | None = None, api_base: str | None = None):
    self.api_key = api_key
    self.api_base = api_base
    self.generation: GenerationSettings = GenerationSettings()

  # 遍历整个messages
  # 处理集中情况：
  # 1. msg.content是空串 -> 转成'(empty)' 或者 None（tool_calls）
  # 2. msg.content是block数组，如果处理完是空的，则按照1设置"(empty)"或者None
  # 2.1 block.type="text"但text是空的 -> 过滤
  # 2.2 block._meta -> delete block._meta
  # 3. msg.content是dict -> 转成[dict]
  @staticmethod
  def _sanitize_empty_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize message content: fix empty blocks, strip internal _meta fields."""
    result: list[dict[str, Any]] = []
    for msg in messages:
      content = msg.get("content")

      # 空串 -> 转成 "(empty)"，如果有tool_calls，设置成None
      if isinstance(content, str) and not content:
        clean = dict(msg)
        clean["content"] = None if (msg.get("role") == "assistant" and msg.get("tool_calls")) else "(empty)"
        result.append(clean)
        continue

      if isinstance(content, list):
        new_items: list[Any] = []
        changed = False
        for item in content:
          # text类型的输出没text，这个block直接过滤掉了
          if (
            isinstance(item, dict) and
            item.get("type") in ("text", "input_text", "output_text") and
            not item.get("text")
          ):
            changed = True
            continue

          # 过滤掉block中的_meta字段
          if isinstance(item, dict) and "_meta" in item:
            new_items.append({k: v for k, v in item.items() if k != "_meta"})
            changed = True
          else:
            new_items.append(item)
        if changed:
          clean = dict(msg)
          if new_items:
            clean["content"] = new_items
          elif msg.get("role") == "assistant" and msg.get("tool_calls"):
            clean["content"] = None
          else:
            clean["content"] = "(empty)"
          result.append(clean)
          continue

      if isinstance(content, dict):
        clean = dict(msg)
        clean["content"] = [content]
        result.append(clean)
        continue

      result.append(msg)
    return result

  @staticmethod
  def _tool_name(tool: dict[str, Any]) -> str:
    """Extract tool name from either OpenAI or Anthropic-style tool schemas."""
    name = tool.get("name")
    if isinstance(name, str):
      return name
    fn = tool.get("function")
    if isinstance(fn, dict):
      fname = fn.get("name")
      if isinstance(fname, str):
        return fname
    return ""
  
  @staticmethod
  def _sanitize_request_messages(
    messages: list[dict[str, Any]],
    allowed_keys: frozenset[str],
  ) -> list[dict[str, Any]]:
    """Keep only provider-safe message keys and normalize assistant content."""
    sanitized = []
    for msg in messages:
      clean = {k: v for k, v in msg.items() if k in allowed_keys}
      if clean.get("role") == "assistant" and "content" not in clean:
        clean["content"] = None
      sanitized.append(clean)
    return sanitized
  
  @staticmethod
  def _normalize_error_token(value: Any) -> str | None:
    if value is None:
      return None
    token = str(value).strip().lower()
    return token or None
  
  # 把messages中的图片处理成text
  @staticmethod
  def _strip_image_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Replace image_url blocks with text placeholder. Returns None if no images found."""
    found = False
    result = []
    for msg in messages:
      content = msg.get("content")
      if isinstance(content, list):
        new_content = []
        for block in content:
          if isinstance(block, dict) and block.get("type") == "image_url":
            path = (block.get("_meta") or {}).get("path", "")
            placeholder = image_placeholder_text(path, empty="[image omitted]")
            new_content.append({
              "type": "text",
              "text": placeholder,
            })
            found = True
          else:
            new_content.append(block)
        result.append({
          **msg,
          "content": new_content,
        })
      else:
        result.append(msg)
    return result if found else None
  
  @staticmethod
  def _strip_image_content_inplace(messages: list[dict[str, Any]]) -> bool:
    """
    Replace image_url blocks with text placeholder *in-place*.

    Mutates the content lists of the original message dicts so that
    callers holding references to those dicts also see the stripped
    version.
    """
    found = False
    for msg in messages:
      content = msg.get("content")
      if isinstance(content, list):
        for i, block in enumerate(content):
          if isinstance(block, dict) and block.get("type") == "image_url":
            path = (block.get("_meta", {})).get("path", "")
            placeholder = image_placeholder_text(path, empty="[image omitted]")
            content[i] = {
              "type": "text",
              "text": placeholder
            }
            found = True
    
    return found

  # classmethod 会收到当前类本身 cls。如果子类调用，cls 是子类。
  # 可以动态创建当前子类实例
  # (read, write, mcp_1, mcp2) -> 返回[1,3]，分别在tool设置cache
  @classmethod
  def _tool_cache_marker_indices(cls, tools: list[dict[str, Any]]) -> list[int]:
    """Return cache marker indices: builtin/MCP boundary and tail index."""
    if not tools:
      return []
    
    tail_idx = len(tools) - 1
    last_buildin_idx: int | None = None
    for i in range(tail_idx, -1, -1):
      if not cls._tool_name(tools[i]).startswith("mcp_"):
        last_buildin_idx = i
        break
    
    ordered_unique: list[int] = []
    for idx in (last_buildin_idx, tail_idx):
      if idx is not None and idx not in ordered_unique:
        ordered_unique.append(idx)
    return ordered_unique
  
  @classmethod
  def _is_transient_error(cls, content: str | None) -> bool:
    err = (content or "").lower()
    return any(marker in err for marker in cls._TRANSIENT_ERROR_MARKERS)
  
  # 按顺序判断一个报错的response，是否是transient
  # 1. response.error_should_retry
  # 2. `error_status_code`是否是429 -> _is_retryable_429_response继续判断
  # 3. 408/409/500+ -> True
  # 4. `error_kind`是否在是timeout/connection
  # 5. 判断`response.content`是否在`_TRANSIENT_ERROR_MARKERS`关键字中
  @classmethod
  def _is_transient_response(cls, response: LLMResponse) -> bool:
    """Prefer structured error metadata, fallback to text markers for legacy providers."""
    if response.error_should_retry is not None:
      return bool(response.error_should_retry)
    
    if response.error_status_code is not None:
      status = int(response.error_status_code)
      if status == 429:
        return cls._is_retryable_429_response(response)
      if status in cls._RETRYABLE_STATUS_CODES or status >= 500:
        return True
    
    kind = (response.error_kind or "").strip().lower()
    if kind in cls._TRANSIENT_ERROR_KINDS:
      return True
    
    return cls._is_transient_error(response.content)
  
  @classmethod
  def _is_retryable_429_response(cls, response: LLMResponse) -> bool:
    type_token = cls._normalize_error_token(response.error_type)
    code_token = cls._normalize_error_token(response.error_code)
    semantic_tokens = {
      token for token in (type_token, code_token) if token is not None
    }

    if any(token in cls._NON_RETRYABLE_429_ERROR_TOKENS for token in semantic_tokens):
      return False
    
    content = (response.content or "").lower()
    if any(marker in content for marker in cls._NON_RETRYABLE_429_TEXT_MARKERS):
      return False

    if any(token in cls._RETRYABLE_429_ERROR_TOKENS for token in semantic_tokens):
      return True
    if any(marker in content for marker in cls._RETRYABLE_429_TEXT_MARKERS):
      return True
    
    return True
  
  @classmethod
  def _extract_retry_after_from_response(cls, response: LLMResponse) -> float | None:
    if response.error_retry_after_s is not None and response.error_retry_after_s > 0:
      return response.error_retry_after_s
    if response.retry_after is not None and response.retry_after > 0:
      return response.retry_after
    return cls._extract_retry_after(response.content)
  
  # 从content里硬解啊😂
  @classmethod
  def _extract_retry_after(cls, content: str | None) -> float | None:
    text = (content or "").lower()
    patterns = (
      r"retry after\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds|m|min|minutes)?",
      r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds|m|min|minutes)",
      r"wait\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds|s|sec|secs|seconds|m|min|minutes)\s*before retry",
      r"retry[_-]?after[\"'\s:=]+(\d+(?:\.\d+)?)",
    )
    for idx, pattern in enumerate(patterns):
      match = re.search(pattern, text)
      if not match:
          continue
      value = float(match.group(1))
      unit = match.group(2) if idx < 3 else "s"
      return cls._to_retry_seconds(value, unit)
    return None
  
  @classmethod
  def _to_retry_seconds(cls, value: float, unit: str | None = None) -> float:
    normalized_unit = (unit or "s").lower()
    if normalized_unit in {"ms", "milliseconds"}:
      return max(0.1, value / 1000.0)
    if normalized_unit in {"m", "min", "minutes"}:
      return max(0.1, value * 60.0)
    return max(0.1, value)

  async def _sleep_with_heartbeat(
      self,
      delay: float,
      *,
      attempt: int,
      persistent: bool,
      on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
  ):
    remaining = max(0.0, delay)
    while remaining > 0:
      if on_retry_wait:
        kind = "persistent retry" if persistent else "retry"
        await on_retry_wait(
          f"Model request failed, {kind} in {max(1, int(round(remaining)))}s "
          f"(attempt {attempt})."
        )
      chunk = min(remaining, self._RETRY_HEARTBEAT_CHUNK)
      await asyncio.sleep(chunk)
      remaining -= chunk

  async def _run_with_retry(
      self,
      call: Callable[..., Awaitable[LLMResponse]],
      kw: dict[str, Any],
      original_messages: list[dict[str, Any]],
      *,
      retry_mode: RetryMode,
      on_retry_wait: Callable[[str], Awaitable[None]] | None,
  ) -> LLMResponse:
    attempt = 0
    delays = list(self._CHAT_RETRY_DELAYS)
    persistent = retry_mode == "persistent"
    last_response: LLMResponse | None = None
    # errorResponse.content
    last_error_key: str | None = None
    # 记录error次数
    identical_error_count = 0

    while True:
      attempt += 1
      response = await call(**kw)
      # 不是error立即返回
      if response.finish_reason != FinishReason.ERROR:
        return response
      
      last_response = response
      error_key = ((response.content or "").strip().lower() or None)
      if error_key and error_key == last_error_key:
        identical_error_count += 1
      else:
        last_error_key = error_key
        identical_error_count = 1 if error_key else 0

      # 可能是不能传图片的模型，传了图片，重试一次
      if not self._is_transient_response(response):
        image_stripped_messages = self._strip_image_content(original_messages)
        if image_stripped_messages is not None and image_stripped_messages != kw["messages"]:
          logger.warning(
            "Non-transient LLM error with image content, retrying without images"
          )
          retry_kw = dict(kw)
          retry_kw["messages"] = image_stripped_messages
          result = await call(**retry_kw)

          if result.finish_reason != "error":
            self._strip_image_content_inplace(original_messages)
          return result
        return response
      
      # 相同的报错，连续报错10次，直接返回
      if persistent and identical_error_count >= self._PERSISTENT_IDENTICAL_ERROR_LIMIT:
        logger.warning(
          "Stopping persistent retry after {} identical transient errors: {}",
          identical_error_count,
          (response.content or "")[:120].lower(),
        )
        if on_retry_wait:
          await on_retry_wait(
            f"Persistent retry stopped after {identical_error_count} identical errors."
          )
        return response
      
      # 3次重试
      if not persistent and attempt > len(delays):
        logger.warning(
          "LLM request failed after {} retries, giving up: {}",
          attempt,
          (response.content or "")[:120].lower(),
        )
        if on_retry_wait:
          await on_retry_wait(
            f"Model request failed after {attempt} retries, giving up."
          )
        break
      
      base_delay = delays[min(attempt - 1, len(delays) - 1)]
      delay = self._extract_retry_after_from_response(response) or base_delay
      if persistent:
        delay = min(delay, self._PERSISTENT_MAX_DELAY)
      
      logger.warning(
        "LLM transient error (attempt {}{}), retrying in {}s: {}",
        attempt,
        "+" if persistent and attempt > len(delays) else f"/{len(delays)}",
        int(round(delay)),
        (response.content or "")[:120].lower(),
      )
      await self._sleep_with_heartbeat(
        delay,
        attempt=attempt,
        persistent=persistent,
        on_retry_wait=on_retry_wait,
      )

    assert last_response is not None
    return last_response
  
  async def _safe_chat(self, **kwargs: Any) -> LLMResponse:
    """Call chat() and convert unexpected exceptions to error responses."""
    try:
      return await self.chat(**kwargs)
    except asyncio.CancelledError:
      raise
    except Exception as e:
      return LLMResponse(
        content=f"Error calling LLM: {e}",
        finish_reason=FinishReason.ERROR
      )
  
  async def chat_with_retry(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    max_tokens: object = _SENTINEL,
    temperature: object = _SENTINEL,
    reasoning_effort: object = _SENTINEL,
    tool_choice: str | dict[str, Any] | None = None,
    retry_mode: RetryMode = RetryMode.STANDARD,
    on_retry_wait: Callable[[str], Awaitable[None]] | None = None,
  ) -> LLMResponse:
    """
    Call chat() with retry on transient provider failures.

    Parameters default to ``self.generation`` when not explicitly passed,
    so callers no longer need to thread temperature / max_tokens /
    reasoning_effort through every layer. Explicit ``None`` is also
    normalized to the provider's generation defaults so that downstream
    ``_build_kwargs`` never sees ``None`` for ``max_tokens`` / ``temperature``
    (which would crash ``max(1, max_tokens)``).
    """
    if max_tokens is self._SENTINEL or max_tokens is None:
      max_tokens = self.generation.max_tokens
    if temperature is self._SENTINEL or temperature is None:
      temperature = self.generation.temperature
    if reasoning_effort is self._SENTINEL:
      reasoning_effort = self.generation.reasoning_effort

    kw: dict[str, Any] = dict(
      messages=messages,
      tools=tools,
      model=model,
      max_tokens=max_tokens,
      temperature=temperature,
      reasoning_effort=reasoning_effort,
      tool_choice=tool_choice,
    )
    return await self._run_with_retry(
      self._safe_chat,
      kw,
      messages,
      retry_mode=retry_mode,
      on_retry_wait=on_retry_wait,
    )
  @abstractmethod
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
    """
    Send a chat completion request.

    Args:
        messages: List of message dicts with 'role' and 'content'.
        tools: Optional list of tool definitions.
        model: Model identifier (provider-specific).
        max_tokens: Maximum tokens in response.
        temperature: Sampling temperature.
        tool_choice: Tool selection strategy ("auto", "required", or specific tool dict).

    Returns:
        LLMResponse with content and/or tool calls.
    """
    pass

  @abstractmethod
  def get_default_model(self) -> str:
      """Get the default model for this provider."""
      pass
