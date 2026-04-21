from pathlib import Path
import re
from typing import Any

def ensure_dir(path: Path) -> Path:
  """Ensure directory exists, return it."""
  # parents: 表示如果上级目录不存在，就一路帮你创建出来。
  # exist_ok: 如果这个目录已经存在，不要报错，直接当作成功
  path.mkdir(parents=True, exist_ok=True)
  # 函数既完成初始化副作用，又保留值传递能力
  return path

# 文件内私有常量
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')

def safe_filename(name: str) -> str:
  """Replace unsafe path characters with underscores."""
  return _UNSAFE_CHARS.sub("_", name).strip()


# 找到message中，不包含孤儿tool + tool+call_id的message
def find_legal_message_start(messages: list[dict[str, Any]]) -> int:
  """"find first legal index of messages"""
  declared_call_id_set = set()
  start = 0
  for i, msg in enumerate(messages):
    role = msg.get("role")
    if role == "assistant":
      for tool_call in msg.get("tool_calls") or []:
        if isinstance(tool_call, dict) and tool_call.get("id"):
          declared_call_id_set.add(str(tool_call.get("id")))
    elif role == "tool":
      tool_call_id = msg.get("tool_call_id")
      if tool_call_id and str(tool_call_id) not in declared_call_id_set:
        start = i + 1
        declared_call_id_set.clear()

  return start
