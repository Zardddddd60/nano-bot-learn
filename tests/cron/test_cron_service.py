import pytest

from nanobot_learn.cron.service import CronService
from nanobot_learn.cron.types import CronSchedule


def test_channel_meta_persists_after_reload(tmp_path):
  store_path = tmp_path / "cron" / "jobs.json"
  service = CronService(store_path)
  service._running = True
  service._arm_timer = lambda: None

  job = service.add_job(
    name="deliver",
    schedule=CronSchedule(kind="every", every_ms=60_000),
    message="hello",
    channel_meta={"thread_ts": "123.456"},
  )

  reloaded = CronService(store_path).get_job(job.id)

  assert reloaded is not None
  assert reloaded.payload.channel_meta == {"thread_ts": "123.456"}


def test_status_returns_enabled_flag_and_job_count(tmp_path):
  service = CronService(tmp_path / "cron" / "jobs.json")
  service.add_job(
    name="status",
    schedule=CronSchedule(kind="every", every_ms=60_000),
    message="hello",
  )

  status = service.status()

  assert status["enabled"] is False
  assert status["jobs"] == 1
  assert "enable" not in status


def test_add_job_reports_unknown_timezone(tmp_path):
  service = CronService(tmp_path / "cron" / "jobs.json")

  with pytest.raises(ValueError, match="unknown timezone 'Bad/Zone'"):
    service.add_job(
      name="bad-zone",
      schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="Bad/Zone"),
      message="hello",
    )
