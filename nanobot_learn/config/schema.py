"""Configuration schema using Pydantic."""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Base(BaseModel):
  """Base model that accepts both camelCase and snake_case keys."""

  # `ConfigDict`：配置 Pydantic 模型行为
  # model_config是固定配置字段，控制整个模型的校验、解析、序列化行为
  model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class ChannelsConfig(Base):
  """
  Configuration for chat channels.

  Built-in and plugin channel configs are stored as extra fields (dicts).
  Each channel parses its own config in __init__.
  Per-channel "streaming": true enables streaming output (requires send_delta impl).
  """

  # 允许传入模型声明之外的字段
  model_config = ConfigDict(extra="allow")

  send_progress: bool = True # stream agent's text progress to the channel
  send_tool_hints: bool = False # stream tool-call hints (e.g. read_file("…"))
  send_max_retries: int = Field(default=3, ge=0, le=10) # Max delivery attempts (initial send included)
  transcription_provider: str = "groq" # Voice transcription backend: "groq" or "openai"
  transcription_language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")

class DreamCOnfig(Base):
  """Dream memory consolidation configuration."""

  _HOUR_MS = 3_600_000

  interval_h: int = Field(default=2, ge=1) # Every 2 hours by default
  cron: str | None = Field(default=None, exclude=True) # Legacy compatibility override
  model_override: str | None = Field(
    default=None,
    # 输入的alias，都映射到model_override
    validation_alias=AliasChoices("modelChoice", "model", "model_choice"),
  )
  max_batch_size: int = Field(default=20, ge=1) # Max history entries per run
  max_iterations: int = Field(default=15, ge=1) # Max tool calls per Phase 2
  annotate_line_ages: bool = True

  # def build_schema(self, timezone: str) -> CronSche