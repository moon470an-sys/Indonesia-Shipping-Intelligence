"""Single CLI entrypoint - Phase 0..5 orchestration."""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select, func

from backend.config import (
    LOG_DIR, PROJECT_ROOT, REPORT_DIR, build_logger, current_snapshot_month, now_kst,
)
from backend.db.database import init_db, session_scope, engine
from backend.db.models import (
    CargoSnapshot, IngestionRun, Port, VesselSnapshot,
)

log = build_logger("main")


# ------------------------- helpers -------------------------

def _record_run(month: str, task: str, status: str,
                started: datetime, finished: datetime,
                total: int, succeeded: int, failed: int, notes: dict) -> None:
    with session_scope() as s:
        s.add(IngestionRun(
            run_month=month,
            task=task,
            started_at=started,
            finished_at=finished,
            status=status,
            total_targets=total,
            succeeded=succeeded,
            failed=failed,
            notes=json.dumps(notes, ensure_ascii=False, default=str)[:65000],
        ))


def _progress_writer(state: dict, stop_evt: threading.Event):
    path = LOG_DIR / "progress.log"
    while not stop_evt.is_set():
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.utcnow().isoformat()} {json.dumps(state, default=str)}\n")
        except Exception:
            pass
        stop_evt.wait(1800)  # 30 min


# ------------------------- phases -------------------------

def phase_sample() -> bool:
    """Phase 1 - sample tests with 3 retries."""
    from backend.tests import test_inaportnet_sample, test_kapal_sample
    for attempt in range(1, 4):
        log.info("Sample attempt %d/3", attempt)
        ok_fleet = False
        ok_cargo = False
        try:
            ok_fleet = test_kapal_sample.run_sample()
        except Exception:
            log.exception("Fleet sample crashed")
        try:
            ok_cargo = test_inaportnet_sample.run_sample()
        except Exception:
            log.exception("Cargo sample crashed")
        if ok_fleet and ok_cargo:
            return True
        if attempt < 3:
            log.warning("Sample failed (fleet=%s cargo=%s); waiting 60s", ok_fleet, ok_cargo)
            time.sleep(60)
    return False


def phase_fleet(snapshot_month: str) -> dict:
    from backend.scrapers.kapal_scraper import scrape_all
    started = datetime.utcnow()
    summary = scrape_all(snapshot_month=snapshot_month)
    finished = datetime.utcnow()
    status = "success" if summary["failed"] == 0 else "partial"
    _record_run(snapshot_month, "fleet", status, started, finished,
                summary["total_codes"], summary["succeeded"], summary["failed"], summary)
    return summary


def phase_cargo(snapshot_month: str) -> dict:
    from backend.scrapers.inaportnet_scraper import scrape_all, seed_ports
    started = datetime.utcnow()
    seed_ports()
    state = {"phase": "cargo", "stage": "running", "ts": started.isoformat()}
    stop_evt = threading.Event()
    t = threading.Thread(target=_progress_writer, args=(state, stop_evt), daemon=True)
    t.start()
    summary = scrape_all(snapshot_month=snapshot_month)
    stop_evt.set()
    finished = datetime.utcnow()
    status = "success" if summary["failed"] == 0 else "partial"
    _record_run(snapshot_month, "cargo", status, started, finished,
                summary["total_targets"], summary["succeeded"], summary["failed"], summary)
    return summary


def phase_validate(snapshot_month: str) -> dict:
    """Re-validate fleet dimensions/tonnage and correct upstream decimal typos.

    Runs after the fleet scrape so the diff phase sees corrected values, and
    so the dashboard never displays the raw outliers. Exceptions are caught
    and recorded as a 'partial' run — a validator failure must not block the
    rest of the monthly pipeline.
    """
    from backend.data_quality.fleet_validator import validate_snapshot
    started = datetime.utcnow()
    try:
        result = validate_snapshot(snapshot_month, dry_run=False)
        finished = datetime.utcnow()
        notes = {k: v for k, v in result.items() if k != "fixes"}
        notes["sample_fixes"] = [
            {"vessel_key": f.vessel_key, "field": f.field,
             "original": f.original, "corrected": f.corrected, "rule": f.rule}
            for f in result["fixes"][:50]
        ]
        _record_run(snapshot_month, "validate", "success", started, finished,
                    result["rows_scanned"], result["rows_affected"],
                    0, notes)
        log.info("Validator: scanned=%d affected=%d fixes=%d",
                 result["rows_scanned"], result["rows_affected"], result["fixes_total"])
        return notes
    except Exception as exc:
        finished = datetime.utcnow()
        _record_run(snapshot_month, "validate", "failed", started, finished,
                    0, 0, 1, {"error": repr(exc)})
        log.exception("Fleet validation failed (continuing pipeline)")
        return {"error": repr(exc)}


def phase_validate_cargo(snapshot_month: str) -> dict:
    """Re-validate cargo (LK3) tonnage / cargo amounts after the cargo scrape.

    Mirrors phase_validate but for cargo_snapshot.raw_row. Decimal-shift
    typos in the upstream LK3 export inflate port-level totals by
    millions of tonnes when left in place. Same defensive contract as the
    fleet validator: failures are logged and the pipeline continues.
    """
    from backend.data_quality.cargo_validator import validate_snapshot
    started = datetime.utcnow()
    try:
        result = validate_snapshot(snapshot_month, dry_run=False)
        finished = datetime.utcnow()
        notes = {k: v for k, v in result.items() if k != "fixes"}
        notes["sample_fixes"] = [
            {"row_id": f.row_id, "field": f.field,
             "original": f.original, "corrected": f.corrected, "rule": f.rule}
            for f in result["fixes"][:50]
        ]
        _record_run(snapshot_month, "validate_cargo", "success", started, finished,
                    result["suspects"], result["rows_affected"], 0, notes)
        log.info("Cargo validator: suspects=%d affected=%d fixes=%d (%.1fs)",
                 result["suspects"], result["rows_affected"],
                 result["fixes_total"], result["elapsed_s"])
        return notes
    except Exception as exc:
        finished = datetime.utcnow()
        _record_run(snapshot_month, "validate_cargo", "failed", started, finished,
                    0, 0, 1, {"error": repr(exc)})
        log.exception("Cargo validation failed (continuing pipeline)")
        return {"error": repr(exc)}


def phase_diff(snapshot_month: str) -> dict:
    from backend.diff.cargo_diff import diff_month as cargo_diff
    from backend.diff.vessel_diff import diff_month as vessel_diff
    started = datetime.utcnow()
    v = vessel_diff(snapshot_month)
    c = cargo_diff(snapshot_month)
    finished = datetime.utcnow()
    _record_run(snapshot_month, "diff", "success", started, finished,
                v["added"] + v["removed"] + v["modified"] + c["added_keys"] + c["revised_keys"],
                0, 0, {"vessel": v, "cargo": c})
    return {"vessel": v, "cargo": c}


def phase_report(snapshot_month: str) -> dict:
    from backend.reports.change_report import build_reports
    started = datetime.utcnow()
    out = build_reports(snapshot_month)
    finished = datetime.utcnow()
    _record_run(snapshot_month, "report", "success", started, finished,
                0, 0, 0, out)
    return out


def write_summary(month: str, started: datetime, finished: datetime,
                  fleet: dict, cargo: dict, diffs: dict, report: dict) -> Path:
    elapsed = finished - started
    hrs, rem = divmod(int(elapsed.total_seconds()), 3600)
    mins = rem // 60
    v_kpis = report.get("vessel_kpis", {})
    c_kpis = report.get("cargo_kpis", {})
    text = f"""# 인도네시아 해운 BI - 실행 결과 ({month})

## 실행 시간
- 시작: {started.strftime('%Y-%m-%d %H:%M:%S')} UTC
- 종료: {finished.strftime('%Y-%m-%d %H:%M:%S')} UTC
- 소요: {hrs}h {mins}m

## 데이터 적재
- 선복량: {fleet['total_codes']} 코드 / {fleet['total_records']}척 (snapshot {month})
- 물동량: {cargo['ports']}항구 × {cargo['months']}개월 × {cargo['kinds']} kind = {cargo['total_targets']} 작업 / {cargo['succeeded']} 성공 / {cargo['empty']} 빈응답 / {cargo['failed']} 실패

## 변경 탐지 (snapshot {month})
- 선박 ADDED: {v_kpis.get('added', diffs['vessel']['added'])}
- 선박 REMOVED: {v_kpis.get('removed', diffs['vessel']['removed'])}
- 선박 MODIFIED: {v_kpis.get('modified', diffs['vessel']['modified'])} (소유주 {v_kpis.get('mod_owner',0)}, GT {v_kpis.get('mod_gt',0)}, 선명 {v_kpis.get('mod_name',0)}, 선종 {v_kpis.get('mod_type',0)})
- 물동량 REVISED 셀: {c_kpis.get('revised_cells', diffs['cargo']['revised_cells'])} (REVISED 키 {diffs['cargo']['revised_keys']}, ADDED {diffs['cargo']['added_keys']}, REMOVED {diffs['cargo']['removed_keys']})
- baseline 여부: vessel={diffs['vessel']['is_baseline']}, cargo={diffs['cargo']['is_baseline']}

## 실패 항목
- 선복량 실패 코드: {fleet.get('failed_codes', [])}
- 물동량 실패 (상위 10개): {cargo.get('failed_targets', [])[:10]}

## 다음 단계
- HTML 리포트: {report['html']}
- Excel: {report['xlsx']}
- 스케줄러: 매월 1일 03:00 KST (`python -m backend.scheduler`)
"""
    out = PROJECT_ROOT / "RESULT_SUMMARY.md"
    out.write_text(text, encoding="utf-8")
    return out


def write_failure_report(stage: str, exc: Exception | None, started: datetime,
                         finished: datetime, extra: dict | None = None) -> Path:
    text = f"""# 인도네시아 해운 BI - 실행 실패

- 단계: {stage}
- 시작: {started.strftime('%Y-%m-%d %H:%M:%S')} UTC
- 종료: {finished.strftime('%Y-%m-%d %H:%M:%S')} UTC
- 예외: {repr(exc) if exc else '(none)'}

## traceback

```
{traceback.format_exc() if exc else '(none)'}
```

## 추가 정보

```json
{json.dumps(extra or {}, indent=2, ensure_ascii=False, default=str)}
```
"""
    out = PROJECT_ROOT / "FAILURE_REPORT.md"
    out.write_text(text, encoding="utf-8")
    log.error("Failure report written to %s", out)
    return out


# ------------------------- monthly orchestrator -------------------------

def run_monthly_auto(skip_sample: bool = False, resume: bool = False,
                     fleet: bool = True, cargo: bool = True,
                     validate: bool = True) -> int:
    init_db()
    started = datetime.utcnow()
    month = current_snapshot_month()
    log.info("=== Monthly run starting (snapshot=%s) ===", month)

    if not skip_sample:
        if not phase_sample():
            finished = datetime.utcnow()
            write_failure_report("sample", None, started, finished,
                                 {"reason": "sample failed 3 times"})
            return 2

    fleet_summary = {"total_codes": 0, "total_records": 0, "succeeded": 0,
                     "failed": 0, "failed_codes": []}
    cargo_summary = {"ports": 0, "months": 0, "kinds": 0, "total_targets": 0,
                     "succeeded": 0, "empty": 0, "failed": 0, "failed_targets": []}
    try:
        if fleet:
            if resume and _has_recent_fleet(month):
                log.info("Resume: skipping fleet phase (already has data for %s)", month)
                fleet_summary = _existing_fleet_summary(month)
            else:
                fleet_summary = phase_fleet(month)
        if validate:
            phase_validate(month)
        if cargo:
            cargo_summary = phase_cargo(month)
        if validate:
            phase_validate_cargo(month)
        diffs = phase_diff(month)
        report = phase_report(month)
    except Exception as exc:
        finished = datetime.utcnow()
        write_failure_report("ingest/diff/report", exc, started, finished,
                             {"fleet": fleet_summary, "cargo": cargo_summary})
        log.exception("Monthly run aborted")
        return 3

    finished = datetime.utcnow()
    write_summary(month, started, finished, fleet_summary, cargo_summary, diffs, report)
    log.info("=== Monthly run done in %s ===", finished - started)
    return 0


def _has_recent_fleet(month: str) -> bool:
    with session_scope() as s:
        n = s.execute(
            select(func.count(VesselSnapshot.id))
            .where(VesselSnapshot.snapshot_month == month)
        ).scalar_one()
    return n > 1000


def _existing_fleet_summary(month: str) -> dict:
    with session_scope() as s:
        codes = s.execute(
            select(func.count(func.distinct(VesselSnapshot.search_code)))
            .where(VesselSnapshot.snapshot_month == month)
        ).scalar_one()
        records = s.execute(
            select(func.count(VesselSnapshot.id))
            .where(VesselSnapshot.snapshot_month == month)
        ).scalar_one()
    return {"total_codes": codes, "total_records": records, "succeeded": codes,
            "failed": 0, "failed_codes": []}


def cmd_audit_taxonomy(month: str | None = None,
                       coverage_threshold: float = 0.95) -> int:
    """Audit the vessel-type taxonomy against current DB content.

    Reports coverage on both label sources:
      * vessels_snapshot.raw_data.JenisDetailKet (vessel registry)
      * cargo_snapshot.raw_row['JENIS KAPAL'] (LK3 logs)

    And komoditi → vessel_class fallback coverage on:
      * cargo_snapshot.raw_row['BONGKAR/MUAT', 'KOMODITI']

    Returns exit code 1 if any source's coverage is below the threshold.
    """
    from sqlalchemy import text

    from backend.taxonomy import coverage as vessel_coverage, SECTOR_UNMAPPED
    from backend.cargo_classification import coverage_komoditi

    # Force UTF-8 stdout on Windows so non-ASCII output (Korean labels,
    # em-dashes) doesn't blow up the cp949 default codec.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    init_db()
    with engine.connect() as conn:
        m_v = month or conn.execute(text(
            "SELECT MAX(snapshot_month) FROM vessels_snapshot"
        )).scalar()
        m_c = month or conn.execute(text(
            "SELECT MAX(snapshot_month) FROM cargo_snapshot"
        )).scalar()
        if not m_v or not m_c:
            print("No snapshots found in DB.")
            return 1

        print(f"=== Vessel taxonomy audit (snapshot {m_v} / {m_c}) ===\n")

        # Vessel registry side (JenisDetailKet)
        v_rows = conn.execute(text(
            "SELECT json_extract(raw_data, '$.JenisDetailKet') AS lbl, COUNT(*) AS n "
            "FROM vessels_snapshot WHERE snapshot_month=:m GROUP BY lbl"
        ), {"m": m_v}).fetchall()
        v_cov = vessel_coverage((lbl, n) for (lbl, n) in v_rows)

        print(f"[1] vessels_snapshot.JenisDetailKet - total {int(v_cov['total']):,} 척")
        for s, w in sorted(v_cov["by_sector"].items(), key=lambda kv: -kv[1]):
            print(f"    {s:<18} {int(w):>8,}  ({w/v_cov['total']*100:5.1f}%)")
        print(f"    UNMAPPED 비중: {v_cov['unmapped_pct']:.2f}%")
        if v_cov["unmapped_tail"]:
            print("    [UNMAPPED tail - top 20]")
            for lbl, w in v_cov["unmapped_tail"][:20]:
                print(f"      {int(w):>6,}  {lbl}")

        # LK3 side (JENIS KAPAL)
        lk3_rows = conn.execute(text(
            "SELECT json_extract(raw_row, '$.\"(''JENIS KAPAL'', ''JENIS KAPAL'')\"') AS lbl, "
            "       COUNT(*) AS n "
            "FROM cargo_snapshot WHERE snapshot_month=:m GROUP BY lbl"
        ), {"m": m_c}).fetchall()
        l_cov = vessel_coverage((lbl, n) for (lbl, n) in lk3_rows)

        print(f"\n[2] cargo_snapshot.JENIS_KAPAL - total {int(l_cov['total']):,} LK3 행")
        for s, w in sorted(l_cov["by_sector"].items(), key=lambda kv: -kv[1]):
            print(f"    {s:<18} {int(w):>10,}  ({w/l_cov['total']*100:5.1f}%)")
        print(f"    UNMAPPED 비중: {l_cov['unmapped_pct']:.2f}%")
        if l_cov["unmapped_tail"]:
            print("    [UNMAPPED tail - top 20]")
            for lbl, w in l_cov["unmapped_tail"][:20]:
                print(f"      {int(w):>8,}  {lbl}")

        # Komoditi fallback coverage (ton-weighted, BONGKAR + MUAT combined)
        kom_rows = conn.execute(text(
            "SELECT k, SUM(t) AS ton FROM ("
            "  SELECT json_extract(raw_row, '$.\"(''BONGKAR'', ''KOMODITI'')\"') AS k, "
            "         COALESCE(CAST(NULLIF(json_extract(raw_row, "
            "                  '$.\"(''BONGKAR'', ''TON'')\"'), '-') AS REAL), 0) AS t "
            "  FROM cargo_snapshot WHERE snapshot_month=:m "
            "  UNION ALL "
            "  SELECT json_extract(raw_row, '$.\"(''MUAT'', ''KOMODITI'')\"'), "
            "         COALESCE(CAST(NULLIF(json_extract(raw_row, "
            "                  '$.\"(''MUAT'', ''TON'')\"'), '-') AS REAL), 0) "
            "  FROM cargo_snapshot WHERE snapshot_month=:m "
            ") WHERE k IS NOT NULL AND k != '' AND k != '-' AND t > 0 "
            "GROUP BY k"
        ), {"m": m_c}).fetchall()
        k_cov = coverage_komoditi((k, t) for (k, t) in kom_rows)

        print(f"\n[3] komoditi → vessel_class fallback - total {k_cov['total_ton']:,.0f} ton")
        for c, w in sorted(k_cov["by_class_ton"].items(), key=lambda kv: -kv[1]):
            print(f"    {c:<18} {w:>16,.0f}  ({w/k_cov['total_ton']*100:5.1f}%)")
        print(f"    OTHER 비중: {k_cov['other_pct']:.2f}%")
        if k_cov["other_tail"]:
            print("    [OTHER tail - top 20]")
            for lbl, w in k_cov["other_tail"][:20]:
                print(f"      {w:>14,.0f}  {lbl}")

    # Exit code reflects the worst coverage of the two vessel-type sources.
    worst = max(v_cov["unmapped_pct"], l_cov["unmapped_pct"]) / 100.0
    threshold = 1.0 - coverage_threshold
    print(f"\nWorst UNMAPPED ratio: {worst*100:.2f}%  (threshold ≤ {threshold*100:.0f}%)")
    return 0 if worst <= threshold else 1


def cmd_status() -> int:
    init_db()
    with session_scope() as s:
        v_count = s.execute(select(func.count(VesselSnapshot.id))).scalar_one()
        c_count = s.execute(select(func.count(CargoSnapshot.id))).scalar_one()
        port_count = s.execute(select(func.count(Port.kode_pelabuhan))).scalar_one()
        runs = s.query(IngestionRun).order_by(IngestionRun.id.desc()).limit(10).all()
    print(f"vessels_snapshot: {v_count} rows")
    print(f"cargo_snapshot:   {c_count} rows")
    print(f"ports:            {port_count}")
    print("recent ingestion_runs:")
    for r in runs:
        print(f"  #{r.id} {r.run_month} {r.task} {r.status} ({r.started_at} → {r.finished_at})")
    return 0


# ------------------------- CLI -------------------------

def main() -> int:
    parser = argparse.ArgumentParser(prog="backend.main")
    parser.add_argument("command", choices=[
        "test-fleet", "test-cargo", "run-fleet", "run-cargo", "run-all",
        "diff", "changes", "report", "monthly", "status", "schedule",
        "audit-taxonomy", "validate-fleet", "validate-cargo",
    ])
    parser.add_argument("--month")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--html", action="store_true")
    parser.add_argument("--no-validate", action="store_true",
                        help="monthly: skip the fleet re-validation phase")
    args = parser.parse_args()

    init_db()

    if args.command == "test-fleet":
        from backend.tests.test_kapal_sample import run_sample
        return 0 if run_sample() else 1
    if args.command == "test-cargo":
        from backend.tests.test_inaportnet_sample import run_sample
        return 0 if run_sample() else 1
    if args.command == "run-fleet":
        month = args.month or current_snapshot_month()
        phase_fleet(month)
        return 0
    if args.command == "run-cargo":
        month = args.month or current_snapshot_month()
        phase_cargo(month)
        return 0
    if args.command == "run-all":
        month = args.month or current_snapshot_month()
        phase_fleet(month)
        phase_cargo(month)
        return 0
    if args.command in ("diff", "changes"):
        month = args.month or current_snapshot_month()
        phase_diff(month)
        return 0
    if args.command == "report":
        month = args.month or current_snapshot_month()
        phase_report(month)
        return 0
    if args.command == "monthly":
        return run_monthly_auto(resume=args.resume, validate=not args.no_validate)
    if args.command == "validate-fleet":
        month = args.month or current_snapshot_month()
        phase_validate(month)
        return 0
    if args.command == "validate-cargo":
        month = args.month or current_snapshot_month()
        phase_validate_cargo(month)
        return 0
    if args.command == "audit-taxonomy":
        return cmd_audit_taxonomy(month=args.month)
    if args.command == "status":
        return cmd_status()
    if args.command == "schedule":
        from backend.scheduler import main as sched_main
        sched_main()
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
