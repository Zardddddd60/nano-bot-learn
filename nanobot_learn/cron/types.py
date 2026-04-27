"""Cron types."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class CronSchedule:
  """
  Schedule definition for a cron job.
  """

  kind: Literal["at", "every", "cron"]
  at_ms: int | None = None # for "at": timestamp in ms
  every_ms: int | None = None # for "every": interval in ms
  expr: str | None = None # For "cron": cron expression (e.g. "0 9 * * *")
  tz: str | None = None # Timezone for cron expressions

@dataclass
class CronPayload:
  """
  What to do when the job runs.
  """

  kind: Literal["system_event", "agent_turn"] = "agent_turn"
  message: str = ""
  deliver: bool = False # Deliver response to channel
  channel: str | None = None # e.g. "whatsapp"
  to: str | None = None # e.g. phone number
  channel_meta: dict = field(default_factory=dict)  # channel-specific routing (e.g. Slack thread_ts)
  session_key: str | None = None  # original session key for correct session recording

@dataclass
class CronRunRecord:
  """
  A single execution record for a cron jon.
  """

  run_at_ms: int
  status: Literal["ok", "error", "skipped"]
  duration_ms: int = 0
  error: str | None = None

@dataclass
class CronJobState:
  """
  Runtime state of a job.
  """

  next_run_at_ms: int | None = None
  last_run_at_ms: int | None = None
  last_status: Literal["ok", "error", "skipped"] | None = None
  last_error: str | None = None
  run_history: list[CronRunRecord] = field(default_factory=list)

@dataclass
class CronJob:
  """
  A schedule job.
  """
  
  id: str
  name: str
  enabled: bool = True
  # 什么时候/频率触发
  schedule: CronSchedule = field(default_factory=lambda: CronSchedule(kind="every"))
  # 触发了干嘛
  payload: CronPayload = field(default_factory=CronPayload)
  # Job的一些执行状态
  state: CronJobState = field(default_factory=CronJobState)
  created_at_ms: int = 0
  updated_at_ms: int = 0
  delete_after_run: bool = False

  # 把一个普通的dict变成一个CronJob类
  # 如果以后有子类调用，也会返回子类实例，而不是写死 CronJob(...)
  @classmethod
  def from_dict(cls, kwargs: dict):
    state_kwargs = dict(kwargs.get("state", {}))
    state_kwargs["run_history"] = [
      record if isinstance(record, CronRunRecord) else CronRunRecord(**record)
      for record in state_kwargs.get("run_history", [])
    ]
    kwargs["schedule"] = CronSchedule(**kwargs.get("schedule", {"kind": "every"}))
    kwargs["payload"] = CronPayload(**kwargs.get("payload", {}))
    kwargs["state"] = CronJobState(**state_kwargs)

    return cls(**kwargs)

@dataclass
class CronStore:
  """
  Persistent store for cron jobs.
  """

  version: int = 1
  jobs: list[CronJob] = field(default_factory=list)
