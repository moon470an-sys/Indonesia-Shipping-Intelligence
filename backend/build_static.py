"""Extract SQLite snapshots into compact JSON for GitHub Pages.

Outputs to ``docs/data/*.json``. Data is denormalised and pre-aggregated so
the site can render without a server. Keep individual files <50 MB to stay
inside GitHub's recommended page size budget.
"""
from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import text

from backend.config import PROJECT_ROOT, build_logger
from backend.db.database import engine

log = build_logger("build_static")
DOCS = PROJECT_ROOT / "docs"
DATA = DOCS / "data"
DATA.mkdir(parents=True, exist_ok=True)


def _write(name: str, payload) -> Path:
    out = DATA / name
    text_data = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    out.write_text(text_data, encoding="utf-8")
    return out


def snapshot_months_meta() -> dict:
    with engine.connect() as conn:
        v = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT snapshot_month FROM vessels_snapshot ORDER BY 1 DESC")).fetchall()]
        c = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT snapshot_month FROM cargo_snapshot ORDER BY 1 DESC")).fetchall()]
        ch = [r[0] for r in conn.execute(text(
            "SELECT change_month FROM ("
            "SELECT DISTINCT change_month FROM vessels_changes "
            "UNION SELECT DISTINCT change_month FROM cargo_changes) ORDER BY 1 DESC")).fetchall()]
    return {
        "vessel_months": v,
        "cargo_months": c,
        "change_months": ch,
        "latest": v[0] if v else None,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def overview_payload(month: str) -> dict:
    with engine.connect() as conn:
        vrow = conn.execute(text(
            "SELECT COUNT(*), COUNT(DISTINCT search_code), AVG(gt), MAX(gt), SUM(gt) "
            "FROM vessels_snapshot WHERE snapshot_month = :m"
        ), {"m": month}).fetchone()
        crow = conn.execute(text(
            "SELECT COUNT(*), COUNT(DISTINCT kode_pelabuhan) FROM cargo_snapshot "
            "WHERE snapshot_month = :m"
        ), {"m": month}).fetchone()
        port_count = conn.execute(text("SELECT COUNT(*) FROM ports")).scalar()
        keys = conn.execute(text(
            "SELECT COUNT(*) FROM (SELECT DISTINCT kode_pelabuhan, data_year, data_month, kind "
            "FROM cargo_snapshot WHERE snapshot_month = :m)"
        ), {"m": month}).scalar()

        monthly = conn.execute(text(
            "SELECT data_year, data_month, kind, COUNT(*) AS rows, "
            "       COUNT(DISTINCT kode_pelabuhan) AS ports "
            "FROM cargo_snapshot WHERE snapshot_month = :m "
            "GROUP BY data_year, data_month, kind ORDER BY data_year, data_month"
        ), {"m": month}).fetchall()
        top_ports = conn.execute(text(
            "SELECT cs.kode_pelabuhan, p.nama_pelabuhan, "
            "       SUM(CASE WHEN cs.kind='dn' THEN 1 ELSE 0 END) AS dn, "
            "       SUM(CASE WHEN cs.kind='ln' THEN 1 ELSE 0 END) AS ln, "
            "       COUNT(*) AS total "
            "FROM cargo_snapshot cs LEFT JOIN ports p ON p.kode_pelabuhan=cs.kode_pelabuhan "
            "WHERE cs.snapshot_month = :m "
            "GROUP BY cs.kode_pelabuhan, p.nama_pelabuhan ORDER BY total DESC LIMIT 30"
        ), {"m": month}).fetchall()
    return {
        "snapshot_month": month,
        "vessel_total": int(vrow[0] or 0),
        "vessel_codes": int(vrow[1] or 0),
        "vessel_avg_gt": float(vrow[2] or 0),
        "vessel_max_gt": float(vrow[3] or 0),
        "vessel_sum_gt": float(vrow[4] or 0),
        "cargo_rows": int(crow[0] or 0),
        "cargo_ports": int(crow[1] or 0),
        "ports_total": int(port_count or 0),
        "cargo_keys": int(keys or 0),
        "cargo_keys_theoretical": 267 * 24 * 2,
        "monthly_traffic": [
            {"period": f"{y}-{m:02d}", "kind": k, "rows": int(n), "ports": int(p)}
            for (y, m, k, n, p) in monthly
        ],
        "top_ports": [
            {"port": p, "name": n, "dn": int(d), "ln": int(l), "total": int(t)}
            for (p, n, d, l, t) in top_ports
        ],
    }


def fleet_payload(month: str) -> dict:
    with engine.connect() as conn:
        types = conn.execute(text(
            "SELECT jenis_kapal, COUNT(*), AVG(gt), SUM(gt) FROM vessels_snapshot "
            "WHERE snapshot_month=:m AND jenis_kapal IS NOT NULL AND jenis_kapal != '' "
            "GROUP BY jenis_kapal ORDER BY 2 DESC LIMIT 50"
        ), {"m": month}).fetchall()
        owners = conn.execute(text(
            "SELECT nama_pemilik, COUNT(*), SUM(gt), AVG(gt) FROM vessels_snapshot "
            "WHERE snapshot_month=:m AND nama_pemilik IS NOT NULL AND nama_pemilik != '' "
            "GROUP BY nama_pemilik ORDER BY 2 DESC LIMIT 50"
        ), {"m": month}).fetchall()
        ages = conn.execute(text(
            "SELECT tahun, COUNT(*) FROM vessels_snapshot "
            "WHERE snapshot_month=:m AND tahun IS NOT NULL AND tahun != '' "
            "GROUP BY tahun ORDER BY tahun"
        ), {"m": month}).fetchall()
        codes = conn.execute(text(
            "SELECT search_code, COUNT(*) FROM vessels_snapshot "
            "WHERE snapshot_month=:m AND search_code IS NOT NULL "
            "GROUP BY search_code ORDER BY 2 DESC"
        ), {"m": month}).fetchall()
        # GT histogram (log-binned)
        gts = [r[0] for r in conn.execute(text(
            "SELECT gt FROM vessels_snapshot WHERE snapshot_month=:m AND gt IS NOT NULL AND gt > 0"
        ), {"m": month}).fetchall()]
    bins = [0, 100, 500, 1000, 5000, 10000, 50000, 100000, 1_000_000]
    buckets = [0] * (len(bins) - 1)
    for g in gts:
        for i in range(len(bins) - 1):
            if bins[i] <= g < bins[i + 1]:
                buckets[i] += 1
                break
    return {
        "snapshot_month": month,
        "types": [
            {"type": t, "count": int(n), "avg_gt": float(a or 0), "sum_gt": float(s or 0)}
            for (t, n, a, s) in types
        ],
        "owners": [
            {"owner": o, "fleet": int(f), "sum_gt": float(s or 0), "avg_gt": float(a or 0)}
            for (o, f, s, a) in owners
        ],
        "ages": [
            {"year": int(y) if y and str(y).isdigit() else None, "count": int(n)}
            for (y, n) in ages if y and str(y).strip().isdigit()
        ],
        "codes": [{"code": c, "count": int(n)} for (c, n) in codes],
        "gt_histogram": {
            "bins": [
                f"{bins[i]:,}–{bins[i+1]:,}" for i in range(len(bins) - 1)
            ],
            "counts": buckets,
        },
    }


def vessels_search_payload(month: str) -> dict:
    """Compact list for client-side filter/search. Keep <15 MB raw → ~3 MB gzip."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT vessel_key, search_code, nama_kapal, call_sign, jenis_kapal, "
            "       nama_pemilik, gt, tahun, imo "
            "FROM vessels_snapshot WHERE snapshot_month=:m"
        ), {"m": month}).fetchall()
    items = []
    for vk, sc, nm, cs, jk, ow, gt, th, imo in rows:
        items.append([
            vk or "",
            sc or "",
            nm or "",
            cs or "",
            jk or "",
            ow or "",
            float(gt) if gt is not None else None,
            th or "",
            imo or "",
        ])
    return {
        "snapshot_month": month,
        "schema": ["key", "code", "name", "call_sign", "type", "owner", "gt", "year", "imo"],
        "items": items,
    }


def cargo_payload(month: str) -> dict:
    with engine.connect() as conn:
        port_traffic = conn.execute(text(
            "SELECT cs.kode_pelabuhan, p.nama_pelabuhan, cs.kind, "
            "       cs.data_year, cs.data_month, COUNT(*) "
            "FROM cargo_snapshot cs LEFT JOIN ports p ON p.kode_pelabuhan=cs.kode_pelabuhan "
            "WHERE cs.snapshot_month=:m "
            "GROUP BY cs.kode_pelabuhan, p.nama_pelabuhan, cs.kind, cs.data_year, cs.data_month"
        ), {"m": month}).fetchall()

    rows = []
    name_map: dict[str, str] = {}
    for port, nama, kind, y, m, n in port_traffic:
        rows.append({
            "port": port,
            "kind": kind,
            "period": f"{int(y)}-{int(m):02d}",
            "rows": int(n),
        })
        if nama:
            name_map[port] = nama
    return {
        "snapshot_month": month,
        "ports": name_map,
        "traffic": rows,
    }


def changes_payload(month: str) -> dict:
    with engine.connect() as conn:
        v_kpi = dict(conn.execute(text(
            "SELECT change_type, COUNT(*) FROM vessels_changes WHERE change_month=:m "
            "GROUP BY change_type"
        ), {"m": month}).fetchall())
        c_kpi = dict(conn.execute(text(
            "SELECT change_type, COUNT(*) FROM cargo_changes WHERE change_month=:m "
            "GROUP BY change_type"
        ), {"m": month}).fetchall())
        v_field = dict(conn.execute(text(
            "SELECT field_name, COUNT(*) FROM vessels_changes "
            "WHERE change_month=:m AND change_type='MODIFIED' "
            "GROUP BY field_name ORDER BY 2 DESC"
        ), {"m": month}).fetchall())
        # samples for the table — bounded so JSON stays small
        v_samples = conn.execute(text(
            "SELECT change_type, vessel_key, field_name, old_value, new_value "
            "FROM vessels_changes WHERE change_month=:m "
            "ORDER BY change_type, vessel_key LIMIT 5000"
        ), {"m": month}).fetchall()
        c_samples = conn.execute(text(
            "SELECT change_type, kode_pelabuhan, data_year, data_month, kind, field_name, "
            "       old_value, new_value, delta, delta_pct "
            "FROM cargo_changes WHERE change_month=:m "
            "ORDER BY ABS(COALESCE(delta_pct,0)) DESC LIMIT 5000"
        ), {"m": month}).fetchall()
    return {
        "change_month": month,
        "vessel_kpi": {k: int(v) for k, v in v_kpi.items()},
        "cargo_kpi": {k: int(v) for k, v in c_kpi.items()},
        "vessel_modified_fields": {k: int(v) for k, v in v_field.items()},
        "vessel_samples": [
            {"type": t, "vessel_key": vk, "field": fn, "old": ov, "new": nv}
            for (t, vk, fn, ov, nv) in v_samples
        ],
        "cargo_samples": [
            {
                "type": t, "port": p, "year": int(y), "month": int(m_), "kind": k,
                "field": fn, "old": ov, "new": nv,
                "delta": float(d) if d is not None else None,
                "delta_pct": float(dp) if dp is not None else None,
            }
            for (t, p, y, m_, k, fn, ov, nv, d, dp) in c_samples
        ],
    }


def main() -> int:
    log.info("=== Build static site bundle ===")
    meta = snapshot_months_meta()
    if not meta["latest"]:
        log.error("No vessel snapshots found — DB empty")
        return 1
    month = meta["latest"]
    change_month = meta["change_months"][0] if meta["change_months"] else month

    pieces = {
        "meta.json": meta,
        "overview.json": overview_payload(month),
        "fleet.json": fleet_payload(month),
        "vessels_search.json": vessels_search_payload(month),
        "cargo.json": cargo_payload(month),
        "changes.json": changes_payload(change_month),
    }
    sizes: dict[str, int] = {}
    for name, payload in pieces.items():
        path = _write(name, payload)
        sizes[name] = path.stat().st_size
        log.info("wrote %s (%.2f MB)", name, sizes[name] / 1024 / 1024)
    (DATA / "_sizes.json").write_text(
        json.dumps({k: v for k, v in sizes.items()}, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
