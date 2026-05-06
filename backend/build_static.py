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
    """Compact list for client-side filter/search. Includes engine/flag/dimensions
    parsed from raw_data so the Fleet dashboard can recompute every chart and KPI
    purely from this payload as filters change.
    """
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT vessel_key, search_code, nama_kapal, call_sign, jenis_kapal, "
            "       nama_pemilik, gt, tahun, imo, length_of_all, panjang, lebar, dalam, raw_data "
            "FROM vessels_snapshot WHERE snapshot_month=:m"
        ), {"m": month}).fetchall()

    def _round1(x):
        if x is None:
            return None
        try:
            return round(float(x), 1)
        except (TypeError, ValueError):
            return None

    items = []
    for vk, sc, nm, cs, jk, ow, gt, th, imo, loa, panj, leb, dal, raw in rows:
        try:
            d = json.loads(raw) if raw else {}
        except Exception:
            d = {}
        eng = d.get("Mesin") or ""
        etp = d.get("MesinType") or ""
        flg = d.get("BenderaAsal") or ""
        # JenisKapal is a numeric code like "1.7.13"; JenisDetailKet has the
        # human-readable English category ("Tug Boat", "Bulk Carrier", ...).
        # Show the human label and fall back to the code only when missing.
        type_label = (d.get("JenisDetailKet") or jk or "").strip()
        loa_val = float(loa) if loa not in (None, "") and float(loa) > 0 else (
            float(panj) if panj not in (None, "") and float(panj) > 0 else None)
        items.append([
            vk or "",
            sc or "",
            nm or "",
            cs or "",
            type_label,
            ow or "",
            _round1(gt),
            th or "",
            imo or "",
            eng,
            etp,
            flg,
            _round1(loa_val),
            _round1(leb),
            _round1(dal),
        ])
    return {
        "snapshot_month": month,
        "schema": ["key", "code", "name", "call_sign", "type", "owner",
                   "gt", "year", "imo",
                   "engine", "engine_type", "flag",
                   "loa", "width", "depth"],
        "items": items,
    }


def cargo_payload(month: str) -> dict:
    """LK3 vessel-call aggregations for the Cargo dashboard.

    Every aggregate carries a per-kind (dn/ln) split so the client can
    re-rank and re-render charts when the user changes the kind filter.
    The site computes "all" by summing dn+ln in JS.
    """
    import collections

    # JSON paths for the (BONGKAR/MUAT, FIELD) keys. The literal key contains
    # single quotes (Python tuple repr), so we double them to embed inside a
    # SQL string literal: 'foo''bar' → foo'bar.
    def _sql_path(key: str) -> str:
        return ('$."' + key + '"').replace("'", "''")

    P_J_B = _sql_path("('BONGKAR', 'JENIS')")
    P_T_B = _sql_path("('BONGKAR', 'TON')")
    P_K_B = _sql_path("('BONGKAR', 'KOMODITI')")
    P_J_M = _sql_path("('MUAT', 'JENIS')")
    P_T_M = _sql_path("('MUAT', 'TON')")
    P_K_M = _sql_path("('MUAT', 'KOMODITI')")

    def _ton_expr(path: str) -> str:
        return f"COALESCE(CAST(NULLIF(json_extract(raw_row, '{path}'), '-') AS REAL), 0)"

    KINDS = ("dn", "ln")
    _zero_f = lambda: {"dn": 0.0, "ln": 0.0}
    _zero_i = lambda: {"dn": 0, "ln": 0}

    with engine.connect() as conn:
        log.info("cargo: port_traffic")
        port_traffic = conn.execute(text(
            "SELECT cs.kode_pelabuhan, p.nama_pelabuhan, cs.kind, "
            "       cs.data_year, cs.data_month, COUNT(*) "
            "FROM cargo_snapshot cs LEFT JOIN ports p ON p.kode_pelabuhan=cs.kode_pelabuhan "
            "WHERE cs.snapshot_month=:m "
            "GROUP BY cs.kode_pelabuhan, p.nama_pelabuhan, cs.kind, cs.data_year, cs.data_month"
        ), {"m": month}).fetchall()

        log.info("cargo: jenis BONGKAR group (by kind)")
        jenis_b_ton: dict = collections.defaultdict(_zero_f)
        jenis_b_calls: dict = collections.defaultdict(_zero_i)
        for j, kn, n, t in conn.execute(text(
            f"SELECT json_extract(raw_row, '{P_J_B}') AS j, kind, COUNT(*), SUM({_ton_expr(P_T_B)}) "
            "FROM cargo_snapshot WHERE snapshot_month=:m GROUP BY j, kind"
        ), {"m": month}):
            if j is None or str(j).strip() in ("", "-") or kn not in KINDS:
                continue
            jenis_b_ton[str(j).strip()][kn] += float(t or 0)
            jenis_b_calls[str(j).strip()][kn] += int(n)

        log.info("cargo: jenis MUAT group (by kind)")
        jenis_m_ton: dict = collections.defaultdict(_zero_f)
        jenis_m_calls: dict = collections.defaultdict(_zero_i)
        for j, kn, n, t in conn.execute(text(
            f"SELECT json_extract(raw_row, '{P_J_M}') AS j, kind, COUNT(*), SUM({_ton_expr(P_T_M)}) "
            "FROM cargo_snapshot WHERE snapshot_month=:m GROUP BY j, kind"
        ), {"m": month}):
            if j is None or str(j).strip() in ("", "-") or kn not in KINDS:
                continue
            jenis_m_ton[str(j).strip()][kn] += float(t or 0)
            jenis_m_calls[str(j).strip()][kn] += int(n)

        log.info("cargo: komoditi group (by kind, BONGKAR + MUAT)")
        komoditi_ton: dict = collections.defaultdict(_zero_f)
        for k, kn, t in conn.execute(text(
            f"SELECT k, kind, SUM(t) FROM ("
            f"  SELECT json_extract(raw_row, '{P_K_B}') AS k, kind, {_ton_expr(P_T_B)} AS t "
            f"  FROM cargo_snapshot WHERE snapshot_month=:m "
            f"  UNION ALL "
            f"  SELECT json_extract(raw_row, '{P_K_M}') AS k, kind, {_ton_expr(P_T_M)} AS t "
            f"  FROM cargo_snapshot WHERE snapshot_month=:m "
            f") WHERE k IS NOT NULL AND k != '' AND k != '-' AND t > 0 "
            f"GROUP BY k, kind"
        ), {"m": month}):
            if kn not in KINDS:
                continue
            komoditi_ton[str(k)][kn] = float(t or 0)

        log.info("cargo: per-port totals (by kind)")
        port_ton_b: dict = collections.defaultdict(_zero_f)
        port_ton_m: dict = collections.defaultdict(_zero_f)
        port_calls: dict = collections.defaultdict(_zero_i)
        for p, kn, tb, tm, n in conn.execute(text(
            f"SELECT kode_pelabuhan, kind, SUM({_ton_expr(P_T_B)}), SUM({_ton_expr(P_T_M)}), COUNT(*) "
            "FROM cargo_snapshot WHERE snapshot_month=:m GROUP BY kode_pelabuhan, kind"
        ), {"m": month}):
            if kn not in KINDS:
                continue
            port_ton_b[p][kn] = float(tb or 0)
            port_ton_m[p][kn] = float(tm or 0)
            port_calls[p][kn] = int(n)

        log.info("cargo: monthly trend (by kind)")
        monthly_kind: dict[tuple, dict] = {}
        for yr, mo, kn, tb, tm, n in conn.execute(text(
            f"SELECT data_year, data_month, kind, SUM({_ton_expr(P_T_B)}), SUM({_ton_expr(P_T_M)}), COUNT(*) "
            "FROM cargo_snapshot WHERE snapshot_month=:m "
            "GROUP BY data_year, data_month, kind ORDER BY 1, 2"
        ), {"m": month}):
            if kn not in KINDS:
                continue
            period = f"{int(yr)}-{int(mo):02d}"
            monthly_kind[(period, kn)] = {"b": float(tb or 0), "m": float(tm or 0), "calls": int(n)}

        port_total_ton_pre = {
            p: sum(port_ton_b[p].values()) + sum(port_ton_m[p].values())
            for p in port_calls
        }
        top_ports_for_matrix = [
            p for p, _ in sorted(port_total_ton_pre.items(), key=lambda x: -x[1])[:15]
        ]

        log.info("cargo: port x jenis matrix (by kind)")
        port_jenis_ton: dict = collections.defaultdict(
            lambda: collections.defaultdict(_zero_f)
        )
        if top_ports_for_matrix:
            placeholders = ",".join(f":p{i}" for i in range(len(top_ports_for_matrix)))
            params = {f"p{i}": p for i, p in enumerate(top_ports_for_matrix)}
            params["m"] = month
            rows_ = conn.execute(text(
                f"SELECT port, kind, j, SUM(t) FROM ("
                f"  SELECT kode_pelabuhan AS port, kind, json_extract(raw_row, '{P_J_B}') AS j, "
                f"    {_ton_expr(P_T_B)} AS t "
                f"  FROM cargo_snapshot WHERE snapshot_month=:m AND kode_pelabuhan IN ({placeholders}) "
                f"  UNION ALL "
                f"  SELECT kode_pelabuhan, kind, json_extract(raw_row, '{P_J_M}'), {_ton_expr(P_T_M)} "
                f"  FROM cargo_snapshot WHERE snapshot_month=:m AND kode_pelabuhan IN ({placeholders}) "
                f") WHERE j IS NOT NULL AND j != '' AND j != '-' GROUP BY port, kind, j"
            ), params).fetchall()
            for p, kn, j, t in rows_:
                if kn not in KINDS:
                    continue
                port_jenis_ton[p][str(j).strip()][kn] = float(t or 0)

    # Build outputs ----------------------------------------------------------
    rows = []
    name_map: dict[str, str] = {}
    for port, nama, kind, y, m_, n in port_traffic:
        rows.append({
            "port": port,
            "kind": kind,
            "period": f"{int(y)}-{int(m_):02d}",
            "rows": int(n),
        })
        if nama:
            name_map[port] = nama

    # Rank jenis by combined ton (bongkar+muat, dn+ln)
    all_jenis_total = {}
    for j in set(jenis_b_ton) | set(jenis_m_ton):
        all_jenis_total[j] = (sum(jenis_b_ton.get(j, _zero_f()).values())
                              + sum(jenis_m_ton.get(j, _zero_f()).values()))
    top_jenis = sorted(all_jenis_total.items(), key=lambda x: -x[1])[:20]

    # Rank komoditi by combined ton across kinds
    komoditi_total = {k: sum(v.values()) for k, v in komoditi_ton.items()}
    top_komoditi = sorted(komoditi_total.items(), key=lambda x: -x[1])[:200]

    # All ports, ranked by combined ton
    port_total_ton = {
        p: sum(port_ton_b[p].values()) + sum(port_ton_m[p].values())
        for p in port_calls
    }
    all_ports_sorted = sorted(port_total_ton.items(), key=lambda x: -x[1])

    matrix_ports = [p for p, _ in all_ports_sorted[:15]]
    matrix_jenis = [j for j, _ in top_jenis[:10]]

    def _mat(kn: str) -> list:
        return [
            [round(port_jenis_ton.get(p, {}).get(j, _zero_f())[kn], 1) for j in matrix_jenis]
            for p in matrix_ports
        ]

    matrix_dn = _mat("dn")
    matrix_ln = _mat("ln")

    periods = sorted({p for (p, _) in monthly_kind})
    monthly_out = []
    for p in periods:
        dn = monthly_kind.get((p, "dn"), {"b": 0, "m": 0, "calls": 0})
        ln = monthly_kind.get((p, "ln"), {"b": 0, "m": 0, "calls": 0})
        monthly_out.append({
            "period": p,
            "ton_bongkar_dn": round(dn["b"], 1),
            "ton_bongkar_ln": round(ln["b"], 1),
            "ton_muat_dn":    round(dn["m"], 1),
            "ton_muat_ln":    round(ln["m"], 1),
            "calls_dn": int(dn["calls"]),
            "calls_ln": int(ln["calls"]),
        })

    def _z(d, k):
        return d.get(k, _zero_f())

    return {
        "snapshot_month": month,
        "schema_version": 2,
        "ports": name_map,
        "traffic": rows,
        "jenis_top": [
            {
                "jenis": j,
                "ton_total": round(all_jenis_total[j], 1),
                "ton_bongkar_dn": round(_z(jenis_b_ton, j)["dn"], 1),
                "ton_bongkar_ln": round(_z(jenis_b_ton, j)["ln"], 1),
                "ton_muat_dn":    round(_z(jenis_m_ton, j)["dn"], 1),
                "ton_muat_ln":    round(_z(jenis_m_ton, j)["ln"], 1),
                "calls_dn": int(jenis_b_calls.get(j, _zero_i())["dn"]
                                + jenis_m_calls.get(j, _zero_i())["dn"]),
                "calls_ln": int(jenis_b_calls.get(j, _zero_i())["ln"]
                                + jenis_m_calls.get(j, _zero_i())["ln"]),
            }
            for j, _ in top_jenis
        ],
        "komoditi_top": [
            {
                "komoditi": k,
                "ton_dn": round(_z(komoditi_ton, k)["dn"], 1),
                "ton_ln": round(_z(komoditi_ton, k)["ln"], 1),
                "ton_total": round(t, 1),
            }
            for k, t in top_komoditi
        ],
        "port_top": [
            {
                "port": p,
                "name": name_map.get(p, ""),
                "ton_bongkar_dn": round(_z(port_ton_b, p)["dn"], 1),
                "ton_bongkar_ln": round(_z(port_ton_b, p)["ln"], 1),
                "ton_muat_dn":    round(_z(port_ton_m, p)["dn"], 1),
                "ton_muat_ln":    round(_z(port_ton_m, p)["ln"], 1),
                "ton_total": round(t, 1),
                "calls_dn": int(port_calls.get(p, _zero_i())["dn"]),
                "calls_ln": int(port_calls.get(p, _zero_i())["ln"]),
            }
            for p, t in all_ports_sorted
        ],
        "monthly_ton": monthly_out,
        "port_jenis_matrix": {
            "ports": matrix_ports,
            "port_names": [name_map.get(p, "") for p in matrix_ports],
            "jenis": matrix_jenis,
            "ton_dn": matrix_dn,
            "ton_ln": matrix_ln,
        },
        "totals": {
            "ton_bongkar_dn": round(sum(s["dn"] for s in port_ton_b.values()), 1),
            "ton_bongkar_ln": round(sum(s["ln"] for s in port_ton_b.values()), 1),
            "ton_muat_dn":    round(sum(s["dn"] for s in port_ton_m.values()), 1),
            "ton_muat_ln":    round(sum(s["ln"] for s in port_ton_m.values()), 1),
            "calls_dn": int(sum(s["dn"] for s in port_calls.values())),
            "calls_ln": int(sum(s["ln"] for s in port_calls.values())),
            "ports": len(port_calls),
        },
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
