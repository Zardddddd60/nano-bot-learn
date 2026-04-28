"""Provider registry metadata used to resolve model names to providers."""

from dataclasses import dataclass
from typing import Any

from pydantic.alias_generators import to_snake


@dataclass(frozen=True)
class ProviderSpec:
  """One LLM provider's metadata."""

  name: str
  keywords: tuple[str, ...]
  env_key: str
  display_name: str = ""
  backend: str = "openai_compat"
  env_extras: tuple[tuple[str, str], ...] = ()
  is_gateway: bool = False
  is_local: bool = False
  detect_by_key_prefix: str = ""
  detect_by_base_keyword: str = ""
  default_api_base: str = ""
  strip_model_prefix: bool = False
  supports_max_completion_tokens: bool = False
  model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()
  is_oauth: bool = False
  is_direct: bool = False
  supports_prompt_caching: bool = False
  thinking_style: str = ""
  reasoning_as_content: bool = False

  @property
  def label(self) -> str:
    return self.display_name or self.name.title()


PROVIDERS: tuple[ProviderSpec, ...] = (
  ProviderSpec(
    name="custom",
    keywords=(),
    env_key="",
    display_name="Custom",
    is_direct=True,
  ),
  ProviderSpec(
    name="azure_openai",
    keywords=("azure", "azure-openai"),
    env_key="",
    display_name="Azure OpenAI",
    backend="azure_openai",
    is_direct=True,
  ),
  ProviderSpec(
    name="openrouter",
    keywords=("openrouter",),
    env_key="OPENROUTER_API_KEY",
    display_name="OpenRouter",
    is_gateway=True,
    detect_by_key_prefix="sk-or-",
    detect_by_base_keyword="openrouter",
    default_api_base="https://openrouter.ai/api/v1",
    supports_prompt_caching=True,
  ),
  ProviderSpec(
    name="aihubmix",
    keywords=("aihubmix",),
    env_key="OPENAI_API_KEY",
    display_name="AiHubMix",
    is_gateway=True,
    detect_by_base_keyword="aihubmix",
    default_api_base="https://aihubmix.com/v1",
    strip_model_prefix=True,
  ),
  ProviderSpec(
    name="siliconflow",
    keywords=("siliconflow",),
    env_key="OPENAI_API_KEY",
    display_name="SiliconFlow",
    is_gateway=True,
    detect_by_base_keyword="siliconflow",
    default_api_base="https://api.siliconflow.cn/v1",
  ),
  ProviderSpec(
    name="volcengine",
    keywords=("volcengine", "volces", "ark"),
    env_key="OPENAI_API_KEY",
    display_name="VolcEngine",
    is_gateway=True,
    detect_by_base_keyword="volces",
    default_api_base="https://ark.cn-beijing.volces.com/api/v3",
    thinking_style="thinking_type",
  ),
  ProviderSpec(
    name="volcengine_coding_plan",
    keywords=("volcengine-plan",),
    env_key="OPENAI_API_KEY",
    display_name="VolcEngine Coding Plan",
    is_gateway=True,
    default_api_base="https://ark.cn-beijing.volces.com/api/coding/v3",
    strip_model_prefix=True,
    thinking_style="thinking_type",
  ),
  ProviderSpec(
    name="byteplus",
    keywords=("byteplus",),
    env_key="OPENAI_API_KEY",
    display_name="BytePlus",
    is_gateway=True,
    detect_by_base_keyword="bytepluses",
    default_api_base="https://ark.ap-southeast.bytepluses.com/api/v3",
    strip_model_prefix=True,
    thinking_style="thinking_type",
  ),
  ProviderSpec(
    name="byteplus_coding_plan",
    keywords=("byteplus-plan",),
    env_key="OPENAI_API_KEY",
    display_name="BytePlus Coding Plan",
    is_gateway=True,
    default_api_base="https://ark.ap-southeast.bytepluses.com/api/coding/v3",
    strip_model_prefix=True,
    thinking_style="thinking_type",
  ),
  ProviderSpec(
    name="anthropic",
    keywords=("anthropic", "claude"),
    env_key="ANTHROPIC_API_KEY",
    display_name="Anthropic",
    backend="anthropic",
    supports_prompt_caching=True,
  ),
  ProviderSpec(
    name="openai",
    keywords=("openai", "gpt"),
    env_key="OPENAI_API_KEY",
    display_name="OpenAI",
    supports_max_completion_tokens=True,
  ),
  ProviderSpec(
    name="openai_codex",
    keywords=("openai-codex",),
    env_key="",
    display_name="OpenAI Codex",
    backend="openai_codex",
    detect_by_base_keyword="codex",
    default_api_base="https://chatgpt.com/backend-api",
    is_oauth=True,
  ),
  ProviderSpec(
    name="github_copilot",
    keywords=("github_copilot", "copilot"),
    env_key="",
    display_name="Github Copilot",
    backend="github_copilot",
    default_api_base="https://api.githubcopilot.com",
    strip_model_prefix=True,
    is_oauth=True,
    supports_max_completion_tokens=True,
  ),
  ProviderSpec(
    name="deepseek",
    keywords=("deepseek",),
    env_key="DEEPSEEK_API_KEY",
    display_name="DeepSeek",
    default_api_base="https://api.deepseek.com",
    thinking_style="thinking_type",
  ),
  ProviderSpec(
    name="gemini",
    keywords=("gemini",),
    env_key="GEMINI_API_KEY",
    display_name="Gemini",
    default_api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
  ),
  ProviderSpec(
    name="zhipu",
    keywords=("zhipu", "glm", "zai"),
    env_key="ZAI_API_KEY",
    display_name="Zhipu AI",
    env_extras=(("ZHIPUAI_API_KEY", "{api_key}"),),
    default_api_base="https://open.bigmodel.cn/api/paas/v4",
  ),
  ProviderSpec(
    name="dashscope",
    keywords=("qwen", "dashscope"),
    env_key="DASHSCOPE_API_KEY",
    display_name="DashScope",
    default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
    thinking_style="enable_thinking",
  ),
  ProviderSpec(
    name="moonshot",
    keywords=("moonshot", "kimi"),
    env_key="MOONSHOT_API_KEY",
    display_name="Moonshot",
    default_api_base="https://api.moonshot.ai/v1",
    model_overrides=(
      ("kimi-k2.5", {"temperature": 1.0}),
      ("kimi-k2.6", {"temperature": 1.0}),
    ),
  ),
  ProviderSpec(
    name="minimax",
    keywords=("minimax",),
    env_key="MINIMAX_API_KEY",
    display_name="MiniMax",
    default_api_base="https://api.minimax.io/v1",
    thinking_style="reasoning_split",
  ),
  ProviderSpec(
    name="minimax_anthropic",
    keywords=("minimax_anthropic",),
    env_key="MINIMAX_API_KEY",
    display_name="MiniMax (Anthropic)",
    backend="anthropic",
    default_api_base="https://api.minimax.io/anthropic",
  ),
  ProviderSpec(
    name="mistral",
    keywords=("mistral",),
    env_key="MISTRAL_API_KEY",
    display_name="Mistral",
    default_api_base="https://api.mistral.ai/v1",
  ),
  ProviderSpec(
    name="stepfun",
    keywords=("stepfun", "step"),
    env_key="STEPFUN_API_KEY",
    display_name="Step Fun",
    default_api_base="https://api.stepfun.com/v1",
    reasoning_as_content=True,
  ),
  ProviderSpec(
    name="xiaomi_mimo",
    keywords=("xiaomi_mimo", "mimo"),
    env_key="XIAOMIMIMO_API_KEY",
    display_name="Xiaomi MIMO",
    default_api_base="https://api.xiaomimimo.com/v1",
  ),
  ProviderSpec(
    name="vllm",
    keywords=("vllm",),
    env_key="HOSTED_VLLM_API_KEY",
    display_name="vLLM/Local",
    is_local=True,
  ),
  ProviderSpec(
    name="ollama",
    keywords=("ollama", "nemotron"),
    env_key="OLLAMA_API_KEY",
    display_name="Ollama",
    is_local=True,
    detect_by_base_keyword="11434",
    default_api_base="http://localhost:11434/v1",
  ),
  ProviderSpec(
    name="lm_studio",
    keywords=("lm-studio", "lmstudio", "lm_studio"),
    env_key="LM_STUDIO_API_KEY",
    display_name="LM Studio",
    is_local=True,
    detect_by_base_keyword="1234",
    default_api_base="http://localhost:1234/v1",
  ),
  ProviderSpec(
    name="ovms",
    keywords=("openvino", "ovms"),
    env_key="",
    display_name="OpenVINO Model Server",
    is_direct=True,
    is_local=True,
    default_api_base="http://localhost:8000/v3",
  ),
  ProviderSpec(
    name="groq",
    keywords=("groq",),
    env_key="GROQ_API_KEY",
    display_name="Groq",
    default_api_base="https://api.groq.com/openai/v1",
  ),
  ProviderSpec(
    name="qianfan",
    keywords=("qianfan", "ernie"),
    env_key="QIANFAN_API_KEY",
    display_name="Qianfan",
    default_api_base="https://qianfan.baidubce.com/v2",
  ),
)


def find_by_name(name: str) -> ProviderSpec | None:
  """Find a provider spec by config field name, e.g. ``dashscope``."""
  normalized = to_snake(name.replace("-", "_"))
  for spec in PROVIDERS:
    if spec.name == normalized:
      return spec
  return None
