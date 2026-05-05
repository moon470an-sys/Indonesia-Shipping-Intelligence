"""Retry only the fleet codes that failed in the most recent fleet run, then re-run diff + report."""
from __future__ import annotations

import json
import sys

from backend.config import build_logger, current_snapshot_month
from backend.db.database import init_db, session_scope
from backend.db.models import IngestionRun
from backend.scrapers.kapal_scraper import scrape_all as fleet_scrape

log = build_logger("retry_failed")


def latest_failed_codes(month: str) -> list[str]:
    with session_scope() as s:
        run = (s.query(IngestionRun)
               .filter(IngestionRun.run_month == month, IngestionRun.task == "fleet")
               .order_by(IngestionRun.id.desc())
               .first())
        if run is None or not run.notes:
            return []
        try:
            notes = json.loads(run.notes)
        except json.JSONDecodeError:
            return []
        return notes.get("failed_codes", []) or []


def main() -> int:
    init_db()
    month = current_snapshot_month()
    failed = latest_failed_codes(month)
    if not failed:
        log.info("No failed fleet codes to retry for %s", month)
    else:
        log.info("Retrying %d failed fleet codes for %s: %s", len(failed), month, failed)
        summary = fleet_scrape(snapshot_month=month, codes=failed)
        log.info("Retry fleet summary: %s",
                 {k: v for k, v in summary.items() if k != "details"})

    # rerun diff + report so they reflect the retried data
    from backend.diff.cargo_diff import diff_month as cargo_diff
    from backend.diff.vessel_diff import diff_month as vessel_diff
    from backend.reports.change_report import build_reports

    v = vessel_diff(month)
    c = cargo_diff(month)
    log.info("Retry diff: vessel=%s cargo=%s", v, c)
    out = build_reports(month)
    log.info("Reports refreshed: %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
