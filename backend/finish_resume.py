"""Finish what resume_run started: cargo diff + reports + summary."""
from __future__ import annotations

import json
import sys
from datetime import datetime

from sqlalchemy import select, func, distinct

from backend.config import (
    PROJECT_ROOT, SEARCH_CODES, build_logger, current_snapshot_month,
)
from backend.db.database import init_db, session_scope
from backend.db.models import (
    CargoChange, CargoSnapshot, IngestionRun, Port, VesselChange, VesselSnapshot,
)

log = build_logger("finish")


def main() -> int:
    init_db()
    month = current_snapshot_month()
    log.info("=== Finish resume for %s ===", month)

    from backend.diff.cargo_diff import diff_month as cargo_diff
    from backend.diff.vessel_diff import diff_month as vessel_diff
    from backend.reports.change_report import build_reports

    # vessel diff is idempotent — re-running ensures vessels_current/changes are fresh
    v = vessel_diff(month)
    cd = cargo_diff(month)
    log.info("Finish diff: vessel=%s cargo=%s", v, cd)

    out = build_reports(month)
    log.info("Reports: %s", out)

    with session_scope() as s:
        v_total = s.execute(select(func.count(VesselSnapshot.id))
                            .where(VesselSnapshot.snapshot_month == month)).scalar_one()
        c_total = s.execute(select(func.count(CargoSnapshot.id))
                            .where(CargoSnapshot.snapshot_month == month)).scalar_one()
        v_codes = s.execute(select(func.count(distinct(VesselSnapshot.search_code)))
                            .where(VesselSnapshot.snapshot_month == month)).scalar_one()
        port_count = s.execute(select(func.count(Port.kode_pelabuhan))).scalar_one()
        cargo_keys = s.execute(
            select(func.count()).select_from(
                select(CargoSnapshot.kode_pelabuhan, CargoSnapshot.data_year,
                       CargoSnapshot.data_month, CargoSnapshot.kind)
                .where(CargoSnapshot.snapshot_month == month).distinct().subquery()
            )
        ).scalar_one()

    text = f"""# 인도네시아 해운 BI — 실행 결과 ({month})

> baseline 실행 (이전 snapshot 없음). 다음 달부터 실제 변경(ADDED/REMOVED/MODIFIED/REVISED) 비교가 의미를 가집니다.

## 데이터 적재 (snapshot {month})
- 선복량: {v_codes}/56 코드, **{v_total}척** 누적
- 항구 마스터: {port_count}개
- 물동량: **{c_total} 행**, 고유 (port,year,month,kind) 키 {cargo_keys}/{267*24*2}

## 변경 탐지 (baseline)
- 선박: ADDED {v['added']}, REMOVED {v['removed']}, MODIFIED {v['modified']} (필드 단위 {v['modified_fields']})
- 물동량: ADDED 키 {cd['added_keys']}, REMOVED 키 {cd['removed_keys']}, REVISED 키 {cd['revised_keys']}, REVISED 셀 {cd['revised_cells']}

## 산출물
- HTML: {out['html']}
- Excel: {out['xlsx']}

## 보충 / 다음 단계
- 누락분 보충 추가가 필요하면: `python -m backend.resume_run`
- 매월 1일 03:00 KST 자동 실행: `python -m backend.scheduler`
- 단일 무인 실행: `python -m backend.main monthly --auto`

## 작성 시각
- {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
    summary_path = PROJECT_ROOT / "RESULT_SUMMARY.md"
    summary_path.write_text(text, encoding="utf-8")
    log.info("RESULT_SUMMARY.md written: %s", summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
