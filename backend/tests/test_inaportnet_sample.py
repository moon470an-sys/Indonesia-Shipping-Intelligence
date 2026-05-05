"""Sample LK3 scrape — list ports + IDTPP single month."""
from __future__ import annotations

from backend.config import build_logger, current_snapshot_month
from backend.db.database import init_db
from backend.scrapers.inaportnet_scraper import (
    fetch_lk3, list_ports, upsert_ports,
)

log = build_logger("test_inaport")


def run_sample() -> bool:
    init_db()
    snap = current_snapshot_month()
    # Use 2025-01 per spec
    ports = list_ports(2025, 1)
    if not ports:
        log.error("Sample LK3: list ports empty")
        return False
    n_ports = upsert_ports(ports)
    log.info("Sample LK3: seeded %d ports", n_ports)
    n, err = fetch_lk3("IDTPP", "dn", 2025, 1, snap)
    log.info("Sample LK3: IDTPP/dn/2025-01 rows=%d err=%s", n, err)
    return n_ports > 0 and (err is None or err == "empty_response")


if __name__ == "__main__":
    ok = run_sample()
    print("OK" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)
