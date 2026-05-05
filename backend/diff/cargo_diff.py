"""Detect cargo (LK3) changes between two snapshot months and refresh summaries."""
from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import select, distinct, func, text

from backend.config import build_logger
from backend.db.database import session_scope, engine
from backend.db.models import CargoChange, CargoMonthlySummary, CargoSnapshot

log = build_logger("cargo_diff")

REVISION_PCT_THRESHOLD = 1.0   # absolute %
REVISION_ABS_THRESHOLD = 1.0   # absolute delta

NUMBER_RE = re.compile(r"-?\d[\d,\.]*")


def _to_number(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s = s.replace(",", "")
    m = NUMBER_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _all_snapshot_months() -> list[str]:
    with session_scope() as s:
        rows = s.execute(
            select(distinct(CargoSnapshot.snapshot_month)).order_by(CargoSnapshot.snapshot_month)
        ).all()
        return [r[0] for r in rows]


def _previous_month(month: str) -> str | None:
    months = _all_snapshot_months()
    if month not in months:
        return None
    i = months.index(month)
    return months[i - 1] if i > 0 else None


def _aggregate(month: str) -> dict[tuple, dict[str, float]]:
    """Sum numeric columns per (port, year, month, kind) for a given snapshot.
    Streams rows via the raw connection to keep memory bounded — 2M+ rows easily
    OOMs the ORM-instance path on 32-bit Python or constrained machines."""
    out: dict[tuple, dict[str, float]] = {}
    sql = (
        "SELECT kode_pelabuhan, data_year, data_month, kind, raw_row "
        "FROM cargo_snapshot WHERE snapshot_month = :m"
    )
    with engine.connect().execution_options(stream_results=True) as conn:
        result = conn.exec_driver_sql(
            "SELECT kode_pelabuhan, data_year, data_month, kind, raw_row "
            "FROM cargo_snapshot WHERE snapshot_month = ?", (month,),
        )
        # iterate in chunks to bound memory
        while True:
            chunk = result.fetchmany(5000)
            if not chunk:
                break
            for port, year, month_d, kind, raw in chunk:
                try:
                    d = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    continue
                key = (port, int(year), int(month_d), kind)
                bucket = out.setdefault(key, {"_rows": 0})
                bucket["_rows"] += 1
                for col, val in d.items():
                    num = _to_number(val)
                    if num is None:
                        continue
                    bucket[col] = bucket.get(col, 0.0) + num
    return out


def _refresh_summary(month: str, agg: dict[tuple, dict[str, float]]) -> int:
    now_month = month
    written = 0
    with session_scope() as s:
        for (port, y, m, k), metrics in agg.items():
            row = s.get(CargoMonthlySummary, (port, y, m, k))
            if row is None:
                row = CargoMonthlySummary(kode_pelabuhan=port, data_year=y,
                                          data_month=m, kind=k)
                s.add(row)
            row.vessel_calls = int(metrics.get("_rows", 0))
            # heuristic: pick most "ton-like" or "teu-like" columns
            ton = 0.0
            teu = 0.0
            for col, val in metrics.items():
                lc = col.lower()
                if "ton" in lc or "berat" in lc:
                    ton += val
                if "teu" in lc or "container" in lc or "kontainer" in lc:
                    teu += val
            row.total_cargo_ton = ton
            row.container_teu = teu
            row.extra_metrics = json.dumps({k2: v2 for k2, v2 in metrics.items() if k2 != "_rows"},
                                           ensure_ascii=False)
            row.last_updated_snapshot = now_month
            written += 1
    return written


def diff_month(month: str) -> dict:
    prev_month = _previous_month(month)
    log.info("Cargo diff: %s vs %s", month, prev_month)
    cur = _aggregate(month)
    prev = _aggregate(prev_month) if prev_month else {}

    added = sorted(set(cur) - set(prev))
    removed = sorted(set(prev) - set(cur))
    common = set(cur) & set(prev)

    revised_cells = 0
    revised_keys: set[tuple] = set()
    now = datetime.utcnow()

    with session_scope() as s:
        s.query(CargoChange).filter(CargoChange.change_month == month).delete()
        for k in added:
            port, y, m, kd = k
            s.add(CargoChange(
                change_month=month, kode_pelabuhan=port,
                data_year=y, data_month=m, kind=kd,
                change_type="ADDED", field_name=None,
                old_value=None, new_value=json.dumps(cur[k], default=str),
                delta=None, delta_pct=None, detected_at=now,
            ))
        for k in removed:
            port, y, m, kd = k
            s.add(CargoChange(
                change_month=month, kode_pelabuhan=port,
                data_year=y, data_month=m, kind=kd,
                change_type="REMOVED", field_name=None,
                old_value=json.dumps(prev[k], default=str), new_value=None,
                delta=None, delta_pct=None, detected_at=now,
            ))
        for k in common:
            port, y, m, kd = k
            metrics_cur = cur[k]
            metrics_prev = prev[k]
            for col in set(metrics_cur) | set(metrics_prev):
                old_v = float(metrics_prev.get(col, 0.0))
                new_v = float(metrics_cur.get(col, 0.0))
                delta = new_v - old_v
                if old_v == 0:
                    pct = 100.0 if new_v != 0 else 0.0
                else:
                    pct = (delta / old_v) * 100.0
                if abs(delta) < REVISION_ABS_THRESHOLD and abs(pct) < REVISION_PCT_THRESHOLD:
                    continue
                s.add(CargoChange(
                    change_month=month, kode_pelabuhan=port,
                    data_year=y, data_month=m, kind=kd,
                    change_type="REVISED", field_name=col,
                    old_value=str(old_v), new_value=str(new_v),
                    delta=delta, delta_pct=pct, detected_at=now,
                ))
                revised_cells += 1
                revised_keys.add(k)

    written = _refresh_summary(month, cur)

    summary = {
        "snapshot_month": month,
        "previous_month": prev_month,
        "added_keys": len(added),
        "removed_keys": len(removed),
        "revised_keys": len(revised_keys),
        "revised_cells": revised_cells,
        "summary_rows": written,
        "is_baseline": prev_month is None,
    }
    log.info("Cargo diff summary: %s", summary)
    return summary
