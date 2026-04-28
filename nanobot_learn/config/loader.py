"""Configuration loading utilities."""

import json
import os
from pathlib import Path
import re
from typing import Any

from loguru import logger
from pydantic import BaseModel
import pydantic

from nanobot_learn.config.schema import Config

_current_config_path: Path | None = None

def set_config_path(path: Path):
  global _current_config_path
  _current_config_path = path

def get_config_path() -> Path:
  if _current_config_path:
    return _current_config_path
  return Path.home() / ".nanobot" / "config.json"

def load_config(config_path: Path | None = None) -> Config:
  """
  Load configuration from file or create default.
  """

  path = config_path or get_config_path()
  config = Config()

  if path.exists():
    try:
      with open(path, encoding="utf-8") as f:
        data = json.load(f)
      config = Config.model_validate(data)
    except (json.JSONDecodeError, ValueError, pydantic.ValidationError) as e:
      logger.warning(f"Failed to load config from {path}: {e}")
      logger.warning("Using default configuration.")
  
  _apply_ssrf_whitelist(config)
  return config

def _apply_ssrf_whitelist(config: Config):
  """Apply SSRF whitelist from config to the network security module."""
  from nanobot_learn.security.network import configure_ssrf_whitelist

  configure_ssrf_whitelist(config.tools.ssrf_whitelist)

def save_config(config: Config, config_path: Path | None = None):
  """
  Save configuration to file.
  """

  path = config_path or get_config_path()
  path.parent.mkdir(parents=True, exist_ok=True)

  data = config.model_dump(mode="json", by_alias=True)

  with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)


# ${OPENAI_API_KEY} match[0] = ${OPENAI_API_KEY} match[1] = OPENAI_API_KEY
_ENV_REF_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

def resolve_config_env_vars(config: Config) -> Config:
  """
  Return *config* with ``${VAR}`` env-var references resolved.

  Walks in place so fields declared with ``exclude=True`` (e.g.
  ``DreamConfig.cron``) survive; returns the same instance when no
  references are present. Raises ``ValueError`` if a referenced
  variable is not set.
  """
  return _resolve_in_place(config)

def _resolve_in_place(obj: Any) -> Any:
  if isinstance(obj, str):
    new = _ENV_REF_PATTERN.sub(_env_replace, obj)
    return new if new != obj else obj
  # 处理内部的channels，agent等等，它们都是BaseModel的子类
  if isinstance(obj, BaseModel):
    updates: dict[str, Any] = {}
    # 遍历它声明过的所有字段
    for name in type(obj).model_fields:
      old_value = getattr(obj, name)
      new_value = _resolve_in_place(old_value)
      if new_value is not old_value:
        updates[name] = new_value
    # ChannelsConfig 允许 extra：
    # 配置里有未声明的字段，存在 obj.__pydantic_extra__
    #   {
    #   "channels": {
    #     "telegram": {       telegram 就在extra
    #       "token": "${TELEGRAM_TOKEN}"
    #     }
    #   }
    # }
    extras = obj.__pydantic_extra__
    new_extras: dict[str, Any] | None = None
    if extras:
      resolved = {k: _resolve_in_place(extras[k]) for k, v in extras.items()}
      if any(resolved[k] is not extras[k] for k in extras):
        new_extras = resolved
    # 既没有最外层的update，又没有里层的更新
    if not updates and new_extras is None:
      return obj
    copy = obj.model_copy(update=updates) if updates else obj.model_copy()
    if new_extras is not None:
      copy.__pydantic_extra__ = new_extras
    return copy

  if isinstance(obj, dict):
    resolved = {k: _resolve_in_place(v) for k, v in obj.items()}
    return resolved if any(resolved[k] is not obj[k] for k in obj) else obj
  
  if isinstance(obj, list):
    resolved = [_resolve_in_place(item) for item in obj]
    return resolved if any(new_item is not old_item for new_item, old_item in zip(resolved, obj)) else obj

  return obj

# 如果没有找到对应的环境变量会报错
def _env_replace(match: re.Match[str]) -> str:
  name = match.group(1)
  value = os.environ.get(name)
  if value is None:
    raise ValueError(
      f"Environment variable '{name}' referenced in config is not set"
    )
  return value
