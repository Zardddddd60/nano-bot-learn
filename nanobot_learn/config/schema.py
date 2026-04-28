"""Configuration schema using Pydantic."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings, SettingsConfigDict

from nanobot_learn.cron.types import CronSchedule
from nanobot_learn.providers.registry import PROVIDERS, find_by_name


class Base(BaseModel):
  """Base model that accepts both camelCase and snake_case keys."""

  model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChannelsConfig(Base):
  """Configuration for chat channels."""

  model_config = ConfigDict(extra="allow")

  send_progress: bool = True
  send_tool_hints: bool = False
  send_max_retries: int = Field(default=3, ge=0, le=10)
  transcription_provider: str = "groq"
  transcription_language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")


class DreamConfig(Base):
  """Dream memory consolidation configuration."""

  _HOUR_MS = 3_600_000

  interval_h: int = Field(default=2, ge=1)
  cron: str | None = Field(default=None, exclude=True)
  model_override: str | None = Field(
    default=None,
    validation_alias=AliasChoices("modelOverride", "model", "model_override"),
  )
  max_batch_size: int = Field(default=20, ge=1)
  max_iterations: int = Field(default=15, ge=1)
  annotate_line_ages: bool = True

  def build_schedule(self, timezone: str) -> CronSchedule:
    """Build the runtime schedule, preferring the legacy cron override if present."""
    if self.cron:
      return CronSchedule(kind="cron", expr=self.cron, tz=timezone)
    return CronSchedule(kind="every", every_ms=self.interval_h * self._HOUR_MS)

  def describe_schedule(self) -> str:
    """Return a human-readable summary for logs and startup output."""
    if self.cron:
      return f"cron {self.cron} (legacy)"
    return f"every {self.interval_h}h"


class AgentDefaults(Base):
  """Default agent configuration."""

  workspace: str = "~/.nanobot/workspace"
  model: str = "anthropic/claude-opus-4-5"
  provider: str = "auto"
  max_tokens: int = 8192
  context_window_tokens: int = 65_536
  context_block_limit: int | None = None
  temperature: float = 0.1
  max_tool_iterations: int = 200
  max_tool_result_chars: int = 16_000
  provider_retry_mode: Literal["standard", "persistent"] = "standard"
  reasoning_effort: str | None = None
  timezone: str = "UTC"
  unified_session: bool = False
  disabled_skills: list[str] = Field(default_factory=list)
  session_ttl_minutes: int = Field(
    default=0,
    ge=0,
    validation_alias=AliasChoices("idleCompactAfterMinutes", "sessionTtlMinutes"),
    serialization_alias="idleCompactAfterMinutes",
  )
  consolidation_ratio: float = Field(
    default=0.5,
    ge=0.1,
    le=0.95,
    validation_alias=AliasChoices("consolidationRatio"),
    serialization_alias="consolidationRatio",
  )
  dream: DreamConfig = Field(default_factory=DreamConfig)


class AgentsConfig(Base):
  """Agent configuration."""

  defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
  """LLM provider configuration."""

  api_key: str | None = None
  api_base: str | None = None
  extra_headers: dict[str, str] | None = None


class ProvidersConfig(Base):
  """Configuration for LLM providers."""

  custom: ProviderConfig = Field(default_factory=ProviderConfig)
  azure_openai: ProviderConfig = Field(default_factory=ProviderConfig)
  anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
  openai: ProviderConfig = Field(default_factory=ProviderConfig)
  openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
  deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
  groq: ProviderConfig = Field(default_factory=ProviderConfig)
  zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
  dashscope: ProviderConfig = Field(default_factory=ProviderConfig)
  vllm: ProviderConfig = Field(default_factory=ProviderConfig)
  ollama: ProviderConfig = Field(default_factory=ProviderConfig)
  lm_studio: ProviderConfig = Field(default_factory=ProviderConfig)
  ovms: ProviderConfig = Field(default_factory=ProviderConfig)
  gemini: ProviderConfig = Field(default_factory=ProviderConfig)
  moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
  minimax: ProviderConfig = Field(default_factory=ProviderConfig)
  minimax_anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
  mistral: ProviderConfig = Field(default_factory=ProviderConfig)
  stepfun: ProviderConfig = Field(default_factory=ProviderConfig)
  xiaomi_mimo: ProviderConfig = Field(default_factory=ProviderConfig)
  aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)
  siliconflow: ProviderConfig = Field(default_factory=ProviderConfig)
  volcengine: ProviderConfig = Field(default_factory=ProviderConfig)
  volcengine_coding_plan: ProviderConfig = Field(default_factory=ProviderConfig)
  byteplus: ProviderConfig = Field(default_factory=ProviderConfig)
  byteplus_coding_plan: ProviderConfig = Field(default_factory=ProviderConfig)
  openai_codex: ProviderConfig = Field(default_factory=ProviderConfig, exclude=True)
  github_copilot: ProviderConfig = Field(default_factory=ProviderConfig, exclude=True)
  qianfan: ProviderConfig = Field(default_factory=ProviderConfig)


class HeartbeatConfig(Base):
  """Heartbeat service configuration."""

  enabled: bool = True
  interval_s: int = 30 * 60
  keep_recent_messages: int = 8


class ApiConfig(Base):
  """OpenAI-compatible API server configuration."""

  host: str = "127.0.0.1"
  port: int = 8900
  timeout: float = 120.0


class GatewayConfig(Base):
  """Gateway/server configuration."""

  host: str = "127.0.0.1"
  port: int = 18790
  heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)


class WebSearchConfig(Base):
  """Web search tool configuration."""

  provider: str = "duckduckgo"
  api_key: str = ""
  base_url: str = ""
  max_results: int = 5
  timeout: int = 30


class WebToolsConfig(Base):
  """Web tools configuration."""

  enable: bool = True
  proxy: str | None = None
  search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(Base):
  """Shell exec tool configuration."""

  enable: bool = True
  timeout: int = 60
  path_append: str = ""
  sandbox: str = ""
  allowed_env_keys: list[str] = Field(default_factory=list)


class MCPServerConfig(Base):
  """MCP server connection configuration (stdio or HTTP)."""

  type: Literal["stdio", "sse", "streamableHttp"] | None = None
  command: str = ""
  args: list[str] = Field(default_factory=list)
  env: dict[str, str] = Field(default_factory=dict)
  url: str = ""
  headers: dict[str, str] = Field(default_factory=dict)
  tool_timeout: int = 30
  enabled_tools: list[str] = Field(default_factory=lambda: ["*"])


class MyToolConfig(Base):
  """Self-inspection tool configuration."""

  enable: bool = True
  allow_set: bool = False


class ToolsConfig(Base):
  """Tools configuration."""

  web: WebToolsConfig = Field(default_factory=WebToolsConfig)
  exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
  my: MyToolConfig = Field(default_factory=MyToolConfig)
  restrict_to_workspace: bool = False
  mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
  ssrf_whitelist: list[str] = Field(default_factory=list)


class Config(BaseSettings):
  """Root configuration for nanobot."""

  agents: AgentsConfig = Field(default_factory=AgentsConfig)
  channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
  providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
  api: ApiConfig = Field(default_factory=ApiConfig)
  gateway: GatewayConfig = Field(default_factory=GatewayConfig)
  tools: ToolsConfig = Field(default_factory=ToolsConfig)

  @property
  def workspace_path(self) -> Path:
    """Get expanded workspace path."""
    return Path(self.agents.defaults.workspace).expanduser()

  def _match_provider(self, model: str | None = None) -> tuple[ProviderConfig | None, str | None]:
    """Match provider config and its registry name."""
    forced = self.agents.defaults.provider
    if forced != "auto":
      spec = find_by_name(forced)
      if not spec:
        return None, None
      provider = getattr(self.providers, spec.name, None)
      return (provider, spec.name) if provider else (None, None)

    model_lower = (model or self.agents.defaults.model).lower()
    model_normalized = model_lower.replace("-", "_")
    model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
    normalized_prefix = model_prefix.replace("-", "_")

    def keyword_matches(keyword: str) -> bool:
      keyword = keyword.lower()
      return keyword in model_lower or keyword.replace("-", "_") in model_normalized

    for spec in PROVIDERS:
      provider = getattr(self.providers, spec.name, None)
      if provider and normalized_prefix == spec.name:
        if spec.is_oauth or spec.is_local or provider.api_key:
          return provider, spec.name

    for spec in PROVIDERS:
      provider = getattr(self.providers, spec.name, None)
      if provider and any(keyword_matches(keyword) for keyword in spec.keywords):
        if spec.is_oauth or spec.is_local or provider.api_key:
          return provider, spec.name

    local_fallback: tuple[ProviderConfig, str] | None = None
    for spec in PROVIDERS:
      if not spec.is_local:
        continue
      provider = getattr(self.providers, spec.name, None)
      if not (provider and provider.api_base):
        continue
      if spec.detect_by_base_keyword and spec.detect_by_base_keyword in provider.api_base:
        return provider, spec.name
      if local_fallback is None:
        local_fallback = (provider, spec.name)
    if local_fallback:
      return local_fallback

    for spec in PROVIDERS:
      if spec.is_oauth:
        continue
      provider = getattr(self.providers, spec.name, None)
      if provider and provider.api_key:
        return provider, spec.name
    return None, None

  def get_provider(self, model: str | None = None) -> ProviderConfig | None:
    """Get matched provider config."""
    provider, _ = self._match_provider(model)
    return provider

  def get_provider_name(self, model: str | None = None) -> str | None:
    """Get the registry name of the matched provider."""
    _, name = self._match_provider(model)
    return name

  def get_api_key(self, model: str | None = None) -> str | None:
    """Get API key for the given model."""
    provider = self.get_provider(model)
    return provider.api_key if provider else None

  def get_api_base(self, model: str | None = None) -> str | None:
    """Get API base URL for the given model."""
    provider, name = self._match_provider(model)
    if provider and provider.api_base:
      return provider.api_base
    if name:
      spec = find_by_name(name)
      if spec and spec.default_api_base:
        return spec.default_api_base
    return None

  model_config = SettingsConfigDict(env_prefix="NANOBOT_", env_nested_delimiter="__")
