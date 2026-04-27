"""Cron service for scheduling agent tasks."""

import asyncio
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import time
from typing import Awaitable, Callable, Coroutine, Literal
import uuid

from filelock import FileLock
from loguru import logger

from nanobot_learn.cron.types import CronJob, CronJobState, CronPayload, CronRunRecord, CronSchedule, CronStore


def _now_ms() -> int:
  return int(time.time() * 1000)

def _compute_next_run(schedule: CronSchedule, now_ms: int) -> int | None:
  """Compute next run time in ms."""

  if schedule.kind == "at":
    return schedule.at_ms if schedule.at_ms and schedule.at_ms > now_ms else None
  
  if schedule.kind == "every":
    if not schedule.every_ms or schedule.every_ms <= 0:
      return None
    return now_ms + schedule.every_ms
  
  if schedule.kind == "cron" and schedule.expr:
    try:
      from zoneinfo import ZoneInfo
      from croniter import croniter

      base_time = now_ms / 1000
      tz = ZoneInfo(schedule.tz) if schedule.tz else datetime.now().astimezone().tzinfo
      base_dt = datetime.fromtimestamp(base_time, tz=tz)
      cron = croniter(schedule.expr, base_dt)
      next_dt = cron.get_next(datetime)
      return int(next_dt.timestamp() * 1000)
    except Exception:
      return None

  return None

def _validate_schedule_for_add(schedule: CronSchedule):
  """Validate schedule fields that would otherwise create non-runnable jobs."""
  if schedule.tz and schedule.kind != "cron":
    raise ValueError("tz can only be used with cron schedules.")
  if schedule.kind == "cron" and schedule.tz:
    try:
      from zoneinfo import ZoneInfo

      ZoneInfo(schedule.tz)
    except Exception:
      # 抛出一个新的异常，但不要把原始异常显示出来。
      # 默认情况下，会保留异常链
      # ZoneInfoNotFoundError: ...
      # During handling of the above exception, another exception occurred:
      # ValueError: unknown timezone 'xxx'
      raise ValueError(f"unknown timezone '{schedule.tz}'") from None

class CronService:
  """Service for managing and executing scheduled jobs."""

  _MAX_RUN_HISTORY = 20

  def __init__(
    self,
    store_path: Path,
    on_job: Callable[[CronJob], Awaitable[str | None]] | None = None,
    max_sleep_ms: int = 300_000 # 5min
  ):
    # /tmp/nanobot/cron_state.jsonl
    self.store_path = store_path
    # /tmp/nanobot/action.jsonl
    self._action_path = store_path.parent / "action.jsonl"
    # /tmp/nanobot.lock
    self._lock = FileLock(str(self._action_path.parent) + ".lock")

    self.on_job = on_job
    self.max_sleep_ms = max_sleep_ms

    # 管理多个cron
    self._store: CronStore | None = None
    self._timer_task: asyncio.Task | None = None
    self._running = False
    # 当前正在execute job
    self._timer_active = False

  # store_path存的是version和jobs对象
  def _load_jobs(self) -> tuple[list[CronJob], int]:
    jobs: list[CronJob] = []
    version = 1

    if self.store_path.exists():
      try:
        data = json.loads(self.store_path.read_text(encoding="utf-8"))
        version = data.get("version", 1)

        for job in data.get("jobs", []):
          jobs.append(CronJob(
            id=job["id"],
            name=job["name"],
            enabled=job.get("enabled", True),
            schedule=CronSchedule(
              kind=job["schedule"]["kind"],
              at_ms=job["schedule"].get("atMs"),
              every_ms=job["schedule"].get("everyMs"),
              expr=job["schedule"].get("expr"),
              tz=job["schedule"].get("tz"),
            ),
            payload=CronPayload(
              kind=job["payload"].get("kind", "agent_turn"),
              message=job["payload"].get("message", ""),
              deliver=job["payload"].get("deliver", False),
              channel=job["payload"].get("channel"),
              to=job["payload"].get("to"),
              channel_meta=(
                  job["payload"].get("channelMeta")
                  or job["payload"].get("channel_meta")
                  or {}
              ),
              session_key=job["payload"].get("sessionKey") or job["payload"].get("session_key"),
            ),
            state=CronJobState(
              next_run_at_ms=job.get("state", {}).get("nextRunAtMs"),
              last_run_at_ms=job.get("state", {}).get("lastRunAtMs"),
              last_status=job.get("state", {}).get("lastStatus"),
              last_error=job.get("state", {}).get("lastError"),
              run_history=[
                CronRunRecord(
                  run_at_ms=r["runAtMs"],
                  status=r["status"],
                  duration_ms=r.get("durationMs", 0),
                  error=r.get("error"),
                )
                for r in job.get("state", {}).get("runHistory", [])
              ],
            ),
            created_at_ms=job.get("createdAtMs", 0),
            updated_at_ms=job.get("updatedAtMs", 0),
            delete_after_run=job.get("deleteAfterRun", False),
          ))
      except Exception as e:
        logger.warning("Failed to load cron store: {}", e)

    return jobs, version
  
  # 把 _action_path 里的“增量操作日志”合并进当前内存里的 self._store.jobs，然后在合适的
  # 时候写回 store_path 主存储文件。
  def _merge_action(self):
    if not self._action_path.exists():
      return
    
    if self._store is None:
      return
    
    store = self._store
    job_list = store.jobs
    jobs_map = {job.id: job for job in job_list}

    def _update(params: dict):
      job = CronJob.from_dict(params)
      jobs_map[job.id] = job

    def _del(params: dict):
      if job_id := params.get("job_id"):
        jobs_map.pop(job_id, None)

    with self._lock:
      with open(self._action_path, "r", encoding="utf-8") as f:
        changed = False
        for line in f:
          try:
            line = line.strip()
            action = json.loads(line)
            if "action" not in action:
              continue
            if action["action"] == "del":
              _del(action.get("params", {}))
            else:
              _update(action.get("params", {}))
            changed = True
          except Exception as e:
            logger.debug(f"load action line error: {e}")
            continue
      store.jobs = list(jobs_map.values())
      if self._running and changed:
        self._action_path.write_text("", encoding="utf-8")
        self._save_store()

  def _save_store(self) -> None:
    """Save jobs to disk."""
    if not self._store:
      return

    self.store_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
      "version": self._store.version,
      "jobs": [
        {
          "id": j.id,
          "name": j.name,
          "enabled": j.enabled,
          "schedule": {
            "kind": j.schedule.kind,
            "atMs": j.schedule.at_ms,
            "everyMs": j.schedule.every_ms,
            "expr": j.schedule.expr,
            "tz": j.schedule.tz,
          },
          "payload": {
            "kind": j.payload.kind,
            "message": j.payload.message,
            "deliver": j.payload.deliver,
            "channel": j.payload.channel,
            "to": j.payload.to,
            "channelMeta": j.payload.channel_meta,
            "sessionKey": j.payload.session_key,
          },
          "state": {
            "nextRunAtMs": j.state.next_run_at_ms,
            "lastRunAtMs": j.state.last_run_at_ms,
            "lastStatus": j.state.last_status,
            "lastError": j.state.last_error,
            "runHistory": [
              {
                "runAtMs": r.run_at_ms,
                "status": r.status,
                "durationMs": r.duration_ms,
                "error": r.error,
              }
              for r in j.state.run_history
            ],
          },
          "createdAtMs": j.created_at_ms,
          "updatedAtMs": j.updated_at_ms,
          "deleteAfterRun": j.delete_after_run,
        }
        for j in self._store.jobs
      ]
    }

    self.store_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

  def _load_store(self) -> CronStore:
    """
    Load jobs from disk. Reloads automatically if file was modified externally.
    - Reload every time because it needs to merge operations on the jobs object from other instances.
    - During _on_timer execution, return the existing store to prevent concurrent
      _load_store calls (e.g. from list_jobs polling) from replacing it mid-execution.
    """

    if self._timer_active and self._store:
      return self._store
    jobs, version = self._load_jobs()
    self._store = CronStore(version=version, jobs=jobs)
    self._merge_action()

    return self._store
  
  # store里边有所有的job
  def _recompute_next_runs(self):
    """
    Recompute next run times for all enabled jobs.
    """

    if not self._store:
      return
    now = _now_ms()
    for job in self._store.jobs:
      if job.enabled:
        job.state.next_run_at_ms = _compute_next_run(job.schedule, now)

  def _get_next_wake_ms(self) -> int | None:
    """
    Get the earliest next run time across all jobs.
    """

    if not self._store:
      return
    times = [
      job.state.next_run_at_ms for job in self._store.jobs
      if job.enabled and job.state.next_run_at_ms
    ]

    return min(times) if times else None
  
  def _arm_timer(self):
    """
    Schedule the next timer tick.
    """

    if self._timer_task:
      self._timer_task.cancel()

    if not self._running:
      return

    next_wake = self._get_next_wake_ms()
    if next_wake is None:
      delay_ms = self.max_sleep_ms
    else:
      delay_ms = min(self.max_sleep_ms, max(0, next_wake - _now_ms()))
    delay_in_s = delay_ms / 1000

    async def tick():
      await asyncio.sleep(delay_in_s)
      if self._running:
        await self._on_timer()
    
    self._timer_task = asyncio.create_task(tick())

  async def _on_timer(self):
    # merge了action的最新store
    self._load_store()
    if not self._store:
      # 过一段时间再过来看看
      self._arm_timer()
      return
    
    self._timer_active = True
    try:
      now = _now_ms()
      due_jobs = [
        job for job in self._store.jobs
        if job.enabled and job.state.next_run_at_ms and now >= job.state.next_run_at_ms
      ]

      for job in due_jobs:
        await self._execute_job(job)
      self._save_store()
    finally:
      self._timer_active = False
    self._arm_timer()

  # 运行self.on_job
  # 更新job.state
  # 更新job下次执行时间
  async def _execute_job(self, job: CronJob):
    """
    Execute a single job.
    """

    start_ms = _now_ms()
    logger.info("Cron: executing job '{}' ({})", job.name, job.id)

    try:
      # 这里执行的是self.on_job(job)而不是sel.job()
      if self.on_job:
        await self.on_job(job)

      job.state.last_status = "ok"
      job.state.last_error = None
      logger.info("Cron: job '{}' completed", job.name)
    except Exception as e:
      job.state.last_error = str(e)
      job.state.last_status = "error"
      logger.error("Cron: job '{}' failed: {}", job.name, e)
    
    end_ms = _now_ms()
    job.state.last_run_at_ms = start_ms
    job.updated_at_ms = end_ms

    job.state.run_history.append(CronRunRecord(
      run_at_ms=start_ms,
      status=job.state.last_status,
      duration_ms=end_ms - start_ms,
      error=job.state.last_error,
    ))
    job.state.run_history = job.state.run_history[-self._MAX_RUN_HISTORY:]

    if self._store:
      if job.schedule.kind == "at":
        if job.delete_after_run:
          self._store.jobs = [j for j in self._store.jobs if job.id != j.id]
        else:
          job.enabled = False
          job.state.next_run_at_ms = None
      else:
        job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())

  def _append_action(self, action: Literal["add", "del", "update"], params: dict):
    self.store_path.parent.mkdir(exist_ok=True, parents=True)
    with self._lock:
      with open(self._action_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
          "action": action,
          "params": params,
        }, ensure_ascii=False) + "\n")

  def list_jobs(self, include_disabled = False) -> list[CronJob]:
    """
    List all jobs.
    """

    store = self._load_store()
    all_jobs = store.jobs if include_disabled else [job for job in store.jobs if job.enabled]
    return sorted(all_jobs, key=lambda j: j.state.next_run_at_ms or float('inf'))

  def add_job(
    self,
    name: str,
    schedule: CronSchedule,
    message: str,
    deliver = False,
    channel: str | None = None,
    to: str | None = None,
    delete_after_run = False,
    channel_meta: dict | None = None,
    session_key: str | None = None,
  ) -> CronJob:
    """
    Add a new job.
    """

    _validate_schedule_for_add(schedule)
    now = _now_ms()

    job = CronJob(
      id=str(uuid.uuid4())[:8],
      name=name,
      enabled=True,
      schedule=schedule,
      payload=CronPayload(
        kind="agent_turn",
        message=message,
        deliver=deliver,
        channel=channel,
        to=to,
        channel_meta=channel_meta or {},
        session_key=session_key,
      ),
      state=CronJobState(next_run_at_ms=_compute_next_run(schedule, now)),
      created_at_ms=now,
      updated_at_ms=now,
      delete_after_run=delete_after_run,
    )

    if self._running:
      store = self._load_store()
      store.jobs.append(job)
      self._save_store()
      # start schedule
      self._arm_timer()
    else:
      self._append_action("add", asdict(job))

    logger.info("Cron: added job '{}' ({})", name, job.id)
    return job

  def register_system_job(self, job: CronJob) -> CronJob:
    """
    Register an internal system job (idempotent on restart).
    """

    store = self._load_store()
    now = _now_ms()
    job.state = CronJobState(next_run_at_ms=_compute_next_run(job.schedule, now))
    job.created_at_ms = now
    job.updated_at_ms = now
    store.jobs = [j for j in store.jobs if j.id != job.id]
    store.jobs.append(job)
    self._save_store()
    self._arm_timer()
    logger.info("Cron: registered system job '{}' ({})", job.name, job.id)
    return job

  def remove_job(self, job_id: str) -> Literal["removed", "protected", "not_found"]:
    """
    Remove a job by ID, unless it is a protected system job.
    """

    store = self._load_store()
    # 找到相同id的
    target_job = next((j for j in store.jobs if j.id == job_id), None)

    if target_job is None:
      return "not_found"
    
    if target_job.payload.kind == "system_event":
      logger.info("Cron: refused to remove protected system job {}", job_id)
      return "protected"
    
    before = len(store.jobs)
    store.jobs = [j for j in store.jobs if j.id != job_id]
    removed = len(store.jobs) < before

    if removed:
      if self._running:
        self._save_store()
        self._arm_timer()
      else:
        self._append_action("del", {"job_id": job_id})
      logger.info("Cron: removed job {}", job_id)
      return "removed"
    return "not_found"
  
  def enable_job(self, job_id: str, enabled = True) -> CronJob | None:
    """
    Enable or disable a job.
    """

    store = self._load_store()
    for job in store.jobs:
      if job.id == job_id:
        job.enabled = enabled
        now = _now_ms()
        job.updated_at_ms = now
        if enabled:
          job.state.next_run_at_ms = _compute_next_run(job.schedule, now)
        else:
          job.state.next_run_at_ms = None
        if self._running:
          self._save_store()
          self._arm_timer()
        else:
          self._append_action("update", asdict(job))
        return job
    return None
  
  def update_job(
    self,
    job_id: str,
    *,
    name: str | None = None,
    schedule: CronSchedule | None = None,
    message: str | None = None,
    deliver: bool | None = None,
    channel: str | None | ellipsis = ...,
    to: str | None | ellipsis = ...,
    delete_after_run: bool | None = None,
  ) -> CronJob | Literal["not_found", "protected"]:
    """
    Update mutable fields of an existing job.
    System jobs cannot be updated.

    For ``channel`` and ``to``, pass an explicit value (including ``None``)
    to update; omit (sentinel ``...``) to leave unchanged.
    """

    store = self._load_store()
    target_job = next((job for job in store.jobs if job.id == job_id), None)
    if target_job is None:
      return "not_found"
    
    if target_job.payload.kind == "system_event":
      return "protected"
    
    if schedule is not None:
      _validate_schedule_for_add(schedule)
      target_job.schedule = schedule
    
    if name is not None:
      target_job.name = name

    if message is not None:
      target_job.payload.message = message

    if deliver is not None:
      target_job.payload.deliver = deliver

    if channel is not ...:
      target_job.payload.channel = channel

    if to is not ...:
      target_job.payload.to = to

    if delete_after_run is not None:
      target_job.delete_after_run = delete_after_run

    now = _now_ms()
    target_job.updated_at_ms = now
    if target_job.enabled:
      target_job.state.next_run_at_ms = _compute_next_run(target_job.schedule, now)

    if self._running:
      self._save_store()
      self._arm_timer()
    else:
      self._append_action("update", asdict(target_job))
    logger.info("Cron: updated job '{}' ({})", target_job.name, target_job.id)
    return target_job
  
  async def run_job(self, job_id: str, force = False) -> bool:
    """
    Manually run a job without disturbing the service's running state.
    """

    was_running = self._running
    self._running = True

    try:
      store = self._load_store()
      for job in store.jobs:
        if job.id == job_id:
          if not force and not job.enabled:
            return False
          await self._execute_job(job)
          self._save_store()
          return True
      return False
    finally:
      self._running = was_running
      if was_running:
        self._arm_timer()
  
  def get_job(self, job_id: str) -> CronJob | None:
    """
    Get a job by ID.
    """

    store = self._load_store()
    return next((job for job in store.jobs if job.id == job_id), None)

  def status(self) -> dict:
    """
    Get service status.
    """

    store = self._load_store()
    return {
      "enabled": self._running,
      "jobs": len(store.jobs),
      "next_wake_at_ms": self._get_next_wake_ms(),
    }
  
  async def start(self):
    """
    Start the cron service.
    """

    self._running = True
    self._load_store()
    # 重新计算，但没开始
    self._recompute_next_runs()
    self._save_store()
    self._arm_timer()
    logger.info("Cron service started with {} jobs", len(self._store.jobs if self._store else []))

  def stop(self):
    """
    Stop the cron service.
    """
    self._running = False
    if self._timer_task:
      self._timer_task.cancel()
      self._timer_task = None
