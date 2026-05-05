"""Smart resume — fetch only missing fleet codes / cargo keys for the current snapshot,
then refresh diff and reports.
"""
from __future__ import annotations

import json
import sys

from sqlalchemy import select, distinct, func

from backend.config import (
    CARGO_KINDS, SEARCH_CODES, build_logger, current_snapshot_month,
)
from backend.db.database import init_db, session_scope
from backend.db.models import CargoSnapshot, IngestionRun, VesselSnapshot
from backend.scrapers.inaportnet_scraper import (
    _previous_months, scrape_all as cargo_scrape, seed_ports,
)
from backend.scrapers.kapal_scraper import scrape_all as fleet_scrape

log = build_logger("resume")


def _existing_fleet_codes(month: str) -> set[str]:
    with session_scope() as s:
        rows = s.execute(
            select(distinct(VesselSnapshot.search_code))
            .where(VesselSnapshot.snapshot_month == month)
        ).all()
        return {r[0] for r in rows if r[0]}


def _existing_cargo_keys(month: str) -> set[tuple[str, int, int, str]]:
    with session_scope() as s:
        rows = s.execute(
            select(
                CargoSnapshot.kode_pelabuhan,
                CargoSnapshot.data_year,
                CargoSnapshot.data_month,
                CargoSnapshot.kind,
            )
            .where(CargoSnapshot.snapshot_month == month)
            .distinct()
        ).all()
        return set(rows)


def resume_fleet(month: str) -> dict:
    have = _existing_fleet_codes(month)
    missing = [c for c in SEARCH_CODES if c not in have]
    if not missing:
        log.info("Fleet: nothing missing (%d/%d codes covered)", len(have), len(SEARCH_CODES))
        return {"missing_count": 0, "succeeded": 0, "failed": 0, "failed_codes": []}
    log.info("Fleet: %d codes missing, retrying — %s", len(missing), missing)
    summary = fleet_scrape(snapshot_month=month, codes=missing)
    return summary


def resume_cargo(month: str) -> dict:
    seed_ports()
    have = _existing_cargo_keys(month)
    months = _previous_months(24)
    with session_scope() as s:
        ports = [p[0] for p in s.execute(select(distinct(CargoSnapshot.kode_pelabuhan)))
                                  .all()] or []
    # if ports table is wider, prefer the seeded ports list
    from backend.db.models import Port
    with session_scope() as s:
        seeded = [p.kode_pelabuhan for p in s.query(Port).all()]
    if seeded:
        ports = seeded

    all_targets = [(p, y, m, k) for p in ports for (y, m) in months for k in CARGO_KINDS]
    missing = [(p, y, m, k) for (p, y, m, k) in all_targets if (p, y, m, k) not in have]
    log.info("Cargo: total=%d, already=%d, missing=%d", len(all_targets), len(have), len(missing))
    if not missing:
        return {"missing_count": 0, "succeeded": 0, "failed": 0, "failed_targets": []}
    # group by unique ports/months/kinds for the existing scrape_all signature.
    # but scrape_all iterates the cross-product — that re-includes done keys.
    # Instead, call fetch_lk3 directly via a thread pool.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import random
    import time
    from backend.config import CARGO_WORKERS
    from backend.scrapers.inaportnet_scraper import fetch_lk3

    succeeded = 0
    empty: list[dict] = []
    failed: list[dict] = []
    rows_total = 0

    def _run(t):
        port, y, m, k = t
        time.sleep(random.uniform(0.05, 0.2))
        try:
            return t, *fetch_lk3(port, k, y, m, month)
        except Exception as exc:
            return t, 0, f"exception: {exc}"

    completed = 0
    with ThreadPoolExecutor(max_workers=CARGO_WORKERS) as ex:
        futs = [ex.submit(_run, t) for t in missing]
        for fut in as_completed(futs):
            t, n, err = fut.result()
            completed += 1
            port, y, m, k = t
            rows_total += n
            if err == "empty_response":
                empty.append({"port": port, "year": y, "month": m, "kind": k})
            elif err:
                failed.append({"port": port, "year": y, "month": m, "kind": k, "error": err})
            else:
                succeeded += 1
            if completed % 200 == 0:
                log.info("cargo resume progress: %d/%d (rows=%d)", completed, len(missing), rows_total)

    summary = {
        "missing_count": len(missing),
        "succeeded": succeeded,
        "empty": len(empty),
        "failed": len(failed),
        "rows_total": rows_total,
        "failed_targets": failed[:200],
    }
    log.info("Cargo resume done: %s", {k: v for k, v in summary.items() if k != "failed_targets"})
    return summary


def main() -> int:
    init_db()
    month = current_snapshot_month()
    log.info("=== Resume run for %s ===", month)

    f = resume_fleet(month)
    c = resume_cargo(month)

    from backend.diff.cargo_diff import diff_month as cargo_diff
    from backend.diff.vessel_diff import diff_month as vessel_diff
    from backend.reports.change_report import build_reports

    v = vessel_diff(month)
    cd = cargo_diff(month)
    log.info("Resume diff: vessel=%s cargo=%s", v, cd)
    out = build_reports(month)
    log.info("Resume reports: %s", out)

    # write a simple summary so the user can see the resumed totals
    from datetime import datetime
    from backend.config import PROJECT_ROOT
    with session_scope() as s:
        v_total = s.execute(select(func.count(VesselSnapshot.id))
                            .where(VesselSnapshot.snapshot_month == month)).scalar_one()
        c_total = s.execute(select(func.count(CargoSnapshot.id))
                            .where(CargoSnapshot.snapshot_month == month)).scalar_one()
        v_codes = s.execute(select(func.count(func.distinct(VesselSnapshot.search_code)))
                            .where(VesselSnapshot.snapshot_month == month)).scalar_one()
    text = f"""# 인도네시아 해운 BI — 재개(Resume) 실행 결과 ({month})

## 누락분 보충
- Fleet: {f['missing_count']}개 코드 재시도 → 성공 {f.get('succeeded', 0)}, 실패 {f.get('failed', 0)} ({f.get('failed_codes', [])})
- Cargo: {c['missing_count']}개 키 재시도 → 성공 {c.get('succeeded', 0)}, 빈응답 {c.get('empty', 0)}, 실패 {c.get('failed', 0)}

## 누적 적재 (snapshot {month})
- 선복량: 코드 {v_codes}/56, 누적 {v_total}척
- 물동량: 누적 {c_total} rows

## 변경 탐지
- Vessel: ADDED {v['added']}, REMOVED {v['removed']}, MODIFIED {v['modified']} (필드 단위 {v['modified_fields']})
- Cargo: ADDED 키 {cd['added_keys']}, REMOVED 키 {cd['removed_keys']}, REVISED 키 {cd['revised_keys']}, REVISED 셀 {cd['revised_cells']}
- baseline 여부: vessel={v['is_baseline']}, cargo={cd['is_baseline']}

## 산출물
- HTML: {out['html']}
- Excel: {out['xlsx']}

## 작성 시각
- {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
    out_path = PROJECT_ROOT / "RESUME_SUMMARY.md"
    out_path.write_text(text, encoding="utf-8")
    log.info("RESUME_SUMMARY.md written: %s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
