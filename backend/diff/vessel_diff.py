"""Detect vessel-registry changes between two snapshot months."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from sqlalchemy import select, distinct

from backend.config import build_logger
from backend.db.database import session_scope, engine
from backend.db.models import VesselSnapshot, VesselChange, VesselCurrent

log = build_logger("vessel_diff")

COMPARE_FIELDS = [
    "nama_kapal", "eks_nama_kapal", "call_sign", "jenis_kapal",
    "nama_pemilik", "tpk", "panjang", "lebar", "dalam", "length_of_all",
    "gt", "isi_bersih", "imo", "tahun",
]


def _all_snapshot_months() -> list[str]:
    with session_scope() as s:
        rows = s.execute(
            select(distinct(VesselSnapshot.snapshot_month)).order_by(VesselSnapshot.snapshot_month)
        ).all()
        return [r[0] for r in rows]


def _previous_month(month: str) -> str | None:
    months = _all_snapshot_months()
    if month not in months:
        return None
    i = months.index(month)
    return months[i - 1] if i > 0 else None


def _load_snapshot(month: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with session_scope() as s:
        for v in s.query(VesselSnapshot).filter(VesselSnapshot.snapshot_month == month).all():
            out[v.vessel_key] = {f: getattr(v, f) for f in COMPARE_FIELDS} | {
                "content_hash": v.content_hash,
            }
    return out


def _record_change(s, change_month: str, vessel_key: str, change_type: str,
                   field_name: str | None, old_value, new_value, now: datetime) -> None:
    s.add(VesselChange(
        change_month=change_month,
        vessel_key=vessel_key,
        change_type=change_type,
        field_name=field_name,
        old_value=None if old_value is None else str(old_value),
        new_value=None if new_value is None else str(new_value),
        detected_at=now,
    ))


def _upsert_current(s, vessel_key: str, snapshot_month: str, data: dict,
                    status: str = "active") -> None:
    cur = s.get(VesselCurrent, vessel_key)
    if cur is None:
        cur = VesselCurrent(
            vessel_key=vessel_key,
            first_seen_month=snapshot_month,
        )
        s.add(cur)
    for f in ("nama_kapal", "call_sign", "jenis_kapal", "nama_pemilik",
              "gt", "tahun", "panjang", "lebar", "dalam", "imo"):
        if f in data:
            setattr(cur, f, data[f])
    cur.snapshot_month_latest = snapshot_month
    cur.last_seen_month = snapshot_month
    cur.status = status


def diff_month(month: str) -> dict:
    """Compare given snapshot_month vs the previous snapshot present in DB."""
    prev_month = _previous_month(month)
    log.info("Vessel diff: %s vs %s", month, prev_month)
    cur = _load_snapshot(month)
    prev = _load_snapshot(prev_month) if prev_month else {}

    added = sorted(set(cur) - set(prev))
    removed = sorted(set(prev) - set(cur))
    common = set(cur) & set(prev)
    modified: list[tuple[str, list[tuple[str, object, object]]]] = []
    for k in common:
        if cur[k]["content_hash"] != prev[k]["content_hash"]:
            field_diffs = []
            for f in COMPARE_FIELDS:
                if cur[k].get(f) != prev[k].get(f):
                    field_diffs.append((f, prev[k].get(f), cur[k].get(f)))
            if field_diffs:
                modified.append((k, field_diffs))

    now = datetime.utcnow()
    with session_scope() as s:
        # delete prior change rows for idempotency
        s.query(VesselChange).filter(VesselChange.change_month == month).delete()
        for k in added:
            _record_change(s, month, k, "ADDED", None, None, json.dumps(cur[k], default=str), now)
            _upsert_current(s, k, month, cur[k], status="active")
        for k in removed:
            _record_change(s, month, k, "REMOVED", None, json.dumps(prev[k], default=str), None, now)
            existing = s.get(VesselCurrent, k)
            if existing is not None:
                existing.status = "removed"
        for k, fields in modified:
            for f, ov, nv in fields:
                _record_change(s, month, k, "MODIFIED", f, ov, nv, now)
            _upsert_current(s, k, month, cur[k], status="active")
        # mark common with same hash as still active
        for k in common:
            if k not in {kk for kk, _ in modified}:
                existing = s.get(VesselCurrent, k)
                if existing is not None:
                    existing.last_seen_month = month
                    existing.status = "active"
                else:
                    _upsert_current(s, k, month, cur[k], status="active")

    summary = {
        "snapshot_month": month,
        "previous_month": prev_month,
        "added": len(added),
        "removed": len(removed),
        "modified": len(modified),
        "modified_fields": sum(len(fields) for _, fields in modified),
        "is_baseline": prev_month is None,
    }
    log.info("Vessel diff summary: %s", summary)
    return summary
