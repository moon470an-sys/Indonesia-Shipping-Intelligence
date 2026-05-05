"""Sample fleet scrape — single code, one page."""
from __future__ import annotations

from backend.config import build_logger, current_snapshot_month
from backend.db.database import init_db
from backend.scrapers.kapal_scraper import _fetch_page, _persist_records

log = build_logger("test_kapal")


def run_sample() -> bool:
    init_db()
    code = "AAa"
    snap = current_snapshot_month()
    page = _fetch_page(code, 0)
    if not page:
        log.error("Sample fleet: no page returned")
        return False
    recs = page.get("data") or []
    log.info("Sample fleet: code=%s recordsFiltered=%s, page0_rows=%d",
             code, page.get("recordsFiltered"), len(recs))
    if not recs:
        log.error("Sample fleet: data empty")
        return False
    n = _persist_records(recs[: min(100, len(recs))], code, snap)
    log.info("Sample fleet: persisted %d rows", n)
    return n > 0


if __name__ == "__main__":
    ok = run_sample()
    print("OK" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
