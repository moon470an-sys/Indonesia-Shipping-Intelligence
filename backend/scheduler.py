"""APScheduler registration: monthly run at 03:00 KST on the 1st."""
from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.config import KST, build_logger

log = build_logger("scheduler")


def _job():
    from backend.main import run_monthly_auto
    log.info("Scheduled monthly run starting")
    try:
        run_monthly_auto()
    except Exception:
        log.exception("Scheduled run failed")


def build_scheduler(run_now: bool = False) -> BlockingScheduler:
    sched = BlockingScheduler(timezone=KST)
    sched.add_job(
        _job,
        CronTrigger(day=1, hour=3, minute=0, timezone=KST),
        id="monthly_ingest",
        replace_existing=True,
    )
    if run_now:
        sched.add_job(_job, id="immediate", next_run_time=None)
    log.info("APScheduler configured: every 1st @ 03:00 KST (%s)",
             sched.get_job("monthly_ingest").next_run_time)
    return sched


def main():
    sched = build_scheduler()
    log.info("Starting scheduler — Ctrl+C to stop")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


if __name__ == "__main__":
    main()
