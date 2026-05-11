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

    Schema columns 15..16 (sector, vessel_class) come from
    ``backend.taxonomy`` and let the Fleet tab group by sector without
    reclassifying client-side.
    """
    from backend.taxonomy import classify_vessel_type

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
        sector, vessel_class = classify_vessel_type(type_label)
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
            sector,
            vessel_class,
        ])
    return {
        "snapshot_month": month,
        "schema": ["key", "code", "name", "call_sign", "type", "owner",
                   "gt", "year", "imo",
                   "engine", "engine_type", "flag",
                   "loa", "width", "depth",
                   "sector", "vessel_class"],
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


def sector_taxonomy_payload() -> dict:
    """Static taxonomy payload: canonical sector/class lists + colors.

    Frontend uses this to keep palette consistent across charts and to
    populate filter dropdowns without recomputing.
    """
    from backend.taxonomy import (
        ALL_CLASSES, ALL_SECTORS,
        CLS_BULK, CLS_CONTAINER, CLS_FERRY, CLS_FISHING, CLS_GENERAL,
        CLS_NONCOMM, CLS_OTHER_CARGO, CLS_PASSENGER_SHIP, CLS_TANKER,
        CLS_TUG_OSV, CLS_DREDGER_SPECIAL, SECTOR_CARGO, SECTOR_FISHING,
        SECTOR_NONCOMM, SECTOR_OFFSHORE, SECTOR_PASSENGER, SECTOR_PALETTE,
    )
    sector_to_classes = {
        SECTOR_PASSENGER: [CLS_PASSENGER_SHIP, CLS_FERRY],
        SECTOR_CARGO:     [CLS_CONTAINER, CLS_BULK, CLS_TANKER, CLS_GENERAL, CLS_OTHER_CARGO],
        SECTOR_FISHING:   [CLS_FISHING],
        SECTOR_OFFSHORE:  [CLS_TUG_OSV, CLS_DREDGER_SPECIAL],
        SECTOR_NONCOMM:   [CLS_NONCOMM],
    }
    return {
        "sectors": list(ALL_SECTORS),
        "classes": list(ALL_CLASSES),
        "sector_to_classes": sector_to_classes,
        "palette": SECTOR_PALETTE,
        "tanker_subclasses": [
            "Crude Oil", "Product", "Chemical", "LPG", "LNG",
            "FAME / Vegetable Oil", "Water", "UNKNOWN",
        ],
    }


def cargo_sector_monthly_payload(month: str) -> dict:
    """Per-(period, kind, sector, vessel_class) ton/calls aggregations.

    Pulls aggregated rows grouped by LK3 JENIS KAPAL label, then folds
    them into the canonical (sector, vessel_class) buckets in Python.
    Only ~2-3k aggregated rows leave SQLite, so memory is fine.
    """
    import collections

    from backend.taxonomy import classify_vessel_type, classify_tanker_subclass

    def _sql_path(key: str) -> str:
        return ('$."' + key + '"').replace("'", "''")

    P_J_LK3 = _sql_path("('JENIS KAPAL', 'JENIS KAPAL')")
    P_T_B = _sql_path("('BONGKAR', 'TON')")
    P_T_M = _sql_path("('MUAT', 'TON')")
    P_K_B = _sql_path("('BONGKAR', 'KOMODITI')")
    P_K_M = _sql_path("('MUAT', 'KOMODITI')")

    def _ton_expr(path: str) -> str:
        return f"COALESCE(CAST(NULLIF(json_extract(raw_row, '{path}'), '-') AS REAL), 0)"

    with engine.connect() as conn:
        log.info("sector: by (period, kind, JENIS_KAPAL)")
        rows = conn.execute(text(
            f"SELECT data_year, data_month, kind, "
            f"       json_extract(raw_row, '{P_J_LK3}') AS jk, "
            f"       SUM({_ton_expr(P_T_B)}), SUM({_ton_expr(P_T_M)}), COUNT(*) "
            "FROM cargo_snapshot WHERE snapshot_month=:m "
            "GROUP BY data_year, data_month, kind, jk"
        ), {"m": month}).fetchall()

        log.info("sector: by tanker subclass (period, kind, JENIS_KAPAL)")
        # Tanker subclass detail uses the same JENIS_KAPAL column — no
        # extra groupings needed because subclass is also derived from
        # the label. We re-use the rows above.
        pass

    # Aggregate into (period, kind, sector, vessel_class) buckets.
    bucket: dict = collections.defaultdict(
        lambda: {"ton_b": 0.0, "ton_m": 0.0, "calls": 0}
    )
    tanker_bucket: dict = collections.defaultdict(
        lambda: {"ton_b": 0.0, "ton_m": 0.0, "calls": 0}
    )
    for yr, mo, kind, jk, tb, tm, n in rows:
        sector, vclass = classify_vessel_type(jk)
        period = f"{int(yr)}-{int(mo):02d}"
        key = (period, kind, sector, vclass)
        bucket[key]["ton_b"] += float(tb or 0)
        bucket[key]["ton_m"] += float(tm or 0)
        bucket[key]["calls"] += int(n or 0)
        # If this label maps to Tanker, bucket the tanker subclass too.
        if vclass == "Tanker":
            sub = classify_tanker_subclass(jk)
            sub_key = (period, kind, sub)
            tanker_bucket[sub_key]["ton_b"] += float(tb or 0)
            tanker_bucket[sub_key]["ton_m"] += float(tm or 0)
            tanker_bucket[sub_key]["calls"] += int(n or 0)

    sector_rows = [
        {
            "period": p, "kind": k, "sector": s, "vessel_class": vc,
            "ton_bongkar": round(v["ton_b"], 1),
            "ton_muat":    round(v["ton_m"], 1),
            "ton_total":   round(v["ton_b"] + v["ton_m"], 1),
            "calls": v["calls"],
        }
        for (p, k, s, vc), v in sorted(bucket.items())
    ]
    tanker_rows = [
        {
            "period": p, "kind": k, "subclass": s,
            "ton_bongkar": round(v["ton_b"], 1),
            "ton_muat":    round(v["ton_m"], 1),
            "ton_total":   round(v["ton_b"] + v["ton_m"], 1),
            "calls": v["calls"],
        }
        for (p, k, s), v in sorted(tanker_bucket.items())
    ]
    return {
        "snapshot_month": month,
        "schema_version": 1,
        "rows": sector_rows,
        "tanker_subclass_rows": tanker_rows,
    }


def kpi_summary_payload(month: str, change_month: str | None) -> dict:
    """Headline KPIs for the Overview hero strip.

    Includes:
      * total fleet (latest snapshot)
      * vessels added/removed in change_month
      * total cargo ton in latest data month + MoM% + YoY%
      * top-3 sector ton share (latest data month)

    All values are pre-aggregated so the Overview tab can render the
    KPIs without further joins. MoM = vs previous data month, YoY = vs
    same data month one year ago, both within the latest snapshot.
    """
    from backend.taxonomy import classify_vessel_type

    def _sql_path(key: str) -> str:
        return ('$."' + key + '"').replace("'", "''")

    P_J_LK3 = _sql_path("('JENIS KAPAL', 'JENIS KAPAL')")
    P_T_B = _sql_path("('BONGKAR', 'TON')")
    P_T_M = _sql_path("('MUAT', 'TON')")

    def _ton_expr(path: str) -> str:
        return f"COALESCE(CAST(NULLIF(json_extract(raw_row, '{path}'), '-') AS REAL), 0)"

    with engine.connect() as conn:
        fleet_total = conn.execute(text(
            "SELECT COUNT(*) FROM vessels_snapshot WHERE snapshot_month=:m"
        ), {"m": month}).scalar() or 0

        added = removed = modified = 0
        if change_month:
            for ct, n in conn.execute(text(
                "SELECT change_type, COUNT(*) FROM vessels_changes "
                "WHERE change_month=:m GROUP BY change_type"
            ), {"m": change_month}).fetchall():
                if ct == "ADDED":
                    added = int(n)
                elif ct == "REMOVED":
                    removed = int(n)
                elif ct == "MODIFIED":
                    modified = int(n)
        # Baseline = the only snapshot is the current one, so every vessel
        # appears as ADDED. The dashboard hides ADDED counts in baseline mode.
        is_baseline = (added == fleet_total and removed == 0 and modified == 0
                       and fleet_total > 0)

        # Monthly ton series (sums across kinds and sectors). Use the
        # latest cargo snapshot since periods come from inside the most
        # recent monthly run.
        monthly = conn.execute(text(
            f"SELECT data_year, data_month, "
            f"       SUM({_ton_expr(P_T_B)} + {_ton_expr(P_T_M)}) AS ton "
            "FROM cargo_snapshot WHERE snapshot_month=:m "
            "GROUP BY data_year, data_month ORDER BY 1, 2"
        ), {"m": month}).fetchall()
        monthly_series = [
            {"period": f"{int(y)}-{int(m_):02d}", "ton": float(t or 0)}
            for (y, m_, t) in monthly
        ]

        # Latest fully-loaded data month — Inaportnet's most-recent period
        # is often partial (we scrape mid-month), so the trailing entry
        # may have only a fraction of a normal month's ton. Treat any
        # trailing period with < 50% of the prior period as partial and
        # step back. ``is_partial_latest`` flags this for the dashboard
        # so it can label the KPI ("최근 완성 월 vs 직전 월" wording).
        latest_idx = -1
        is_partial_latest = False
        if len(monthly_series) >= 2:
            last_ton = monthly_series[-1]["ton"]
            prev_ton_ = monthly_series[-2]["ton"]
            if last_ton > 0 and (prev_ton_ == 0 or last_ton >= 0.5 * prev_ton_):
                latest_idx = len(monthly_series) - 1
            else:
                latest_idx = len(monthly_series) - 2
                is_partial_latest = True
        elif len(monthly_series) == 1 and monthly_series[0]["ton"] > 0:
            latest_idx = 0
        latest_ton = monthly_series[latest_idx]["ton"] if latest_idx >= 0 else 0
        latest_period = monthly_series[latest_idx]["period"] if latest_idx >= 0 else None
        prev_ton = monthly_series[latest_idx - 1]["ton"] if latest_idx > 0 else 0
        mom_pct = ((latest_ton - prev_ton) / prev_ton * 100.0) if prev_ton else None
        yoy_pct = None
        if latest_period:
            ly_period = f"{int(latest_period[:4]) - 1}-{latest_period[5:7]}"
            ly_row = next((r for r in monthly_series if r["period"] == ly_period), None)
            if ly_row and ly_row["ton"]:
                yoy_pct = (latest_ton - ly_row["ton"]) / ly_row["ton"] * 100.0

        # Top sectors — latest period only. Both ton and calls metrics are
        # surfaced because ton heavily favors bulk cargo (passenger/fishing
        # vessels carry few tons), while calls tracks operational activity.
        sector_rows = []
        if latest_period:
            ly = int(latest_period[:4])
            lm = int(latest_period[5:7])
            for jk, tb, tm, n in conn.execute(text(
                f"SELECT json_extract(raw_row, '{P_J_LK3}'), "
                f"       SUM({_ton_expr(P_T_B)}), SUM({_ton_expr(P_T_M)}), COUNT(*) "
                "FROM cargo_snapshot WHERE snapshot_month=:m "
                "  AND data_year=:y AND data_month=:mo "
                "GROUP BY 1"
            ), {"m": month, "y": ly, "mo": lm}).fetchall():
                sector, _ = classify_vessel_type(jk)
                sector_rows.append((sector, float(tb or 0) + float(tm or 0), int(n)))

        sector_ton: dict[str, float] = {}
        sector_calls: dict[str, int] = {}
        for s, t, n in sector_rows:
            sector_ton[s] = sector_ton.get(s, 0.0) + t
            sector_calls[s] = sector_calls.get(s, 0) + n
        total_ton = sum(sector_ton.values()) or 1.0
        total_calls = sum(sector_calls.values()) or 1
        # Sort by ton; the dashboard can re-sort client-side if needed.
        sector_keys = sorted(set(sector_ton) | set(sector_calls),
                             key=lambda s: -sector_ton.get(s, 0))

    return {
        "snapshot_month": month,
        "change_month": change_month,
        "fleet_total": int(fleet_total),
        "is_baseline": is_baseline,
        "vessel_changes": {
            "added": added, "removed": removed, "modified_cells": modified,
        },
        "latest_period": latest_period,
        "latest_period_is_partial_data_dropped": is_partial_latest,
        "latest_ton": round(latest_ton, 1),
        "mom_pct": round(mom_pct, 2) if mom_pct is not None else None,
        "yoy_pct": round(yoy_pct, 2) if yoy_pct is not None else None,
        "monthly_series": [
            {"period": r["period"], "ton": round(r["ton"], 1)} for r in monthly_series
        ],
        "top_sectors": [
            {
                "sector": s,
                "ton": round(sector_ton.get(s, 0), 1),
                "pct_ton": round(sector_ton.get(s, 0) / total_ton * 100.0, 2),
                "calls": sector_calls.get(s, 0),
                "pct_calls": round(sector_calls.get(s, 0) / total_calls * 100.0, 2),
            }
            for s in sector_keys
        ],
    }


def tanker_focus_payload(month: str) -> dict:
    """Tanker-operator focused aggregations.

    Drills into the tanker subset of LK3 rows and produces views that
    matter for a tanker company:

      * by_subclass: ton + calls + avg ton/call per (subclass, kind)
      * monthly_subclass: per (period, kind, subclass) ton+calls
      * port_subclass: per (port, kind, subclass) ton+calls -- supports the
        port balance scatter and port-x-subclass heatmap
      * port_balance: per (port, kind) total tanker ton_b/ton_m -- for the
        bongkar/muat asymmetry view (loading vs discharge hubs)
      * komoditi_subclass: per (komoditi, subclass, kind) ton split into
        bongkar vs muat -- top tanker liquids
      * fleet_owners: top owners of tanker vessels from vessels_snapshot

    Filtering to tanker happens in Python because classify_vessel_type is
    rule-based; the SQL groups by raw JENIS_KAPAL and we fold non-tanker
    labels out before re-aggregating.
    """
    import collections

    from backend.taxonomy import (
        classify_tanker_subclass, classify_vessel_type,
        CLS_TANKER, SECTOR_CARGO,
    )

    def _sql_path(key: str) -> str:
        return ('$."' + key + '"').replace("'", "''")

    P_J_LK3 = _sql_path("('JENIS KAPAL', 'JENIS KAPAL')")
    P_T_B = _sql_path("('BONGKAR', 'TON')")
    P_T_M = _sql_path("('MUAT', 'TON')")
    P_K_B = _sql_path("('BONGKAR', 'KOMODITI')")
    P_K_M = _sql_path("('MUAT', 'KOMODITI')")

    def _ton_expr(path: str) -> str:
        return f"COALESCE(CAST(NULLIF(json_extract(raw_row, '{path}'), '-') AS REAL), 0)"

    def _is_tanker(jk: str) -> bool:
        sector, vclass = classify_vessel_type(jk)
        return sector == SECTOR_CARGO and vclass == CLS_TANKER

    with engine.connect() as conn:
        # Distinct tanker JENIS_KAPAL labels in this snapshot. Computing once
        # lets us narrow later queries with an IN (...) and keep memory tight.
        log.info("tanker: distinct labels")
        all_labels = [r[0] for r in conn.execute(text(
            f"SELECT DISTINCT json_extract(raw_row, '{P_J_LK3}') "
            "FROM cargo_snapshot WHERE snapshot_month=:m"
        ), {"m": month}).fetchall() if r[0]]
        tanker_labels = [l for l in all_labels if _is_tanker(l)]
        if not tanker_labels:
            log.warning("tanker: no tanker labels found in snapshot %s", month)
            return {"snapshot_month": month, "schema_version": 1, "empty": True}

        # Bind tanker labels for IN clauses
        tk_ph = ",".join(f":t{i}" for i in range(len(tanker_labels)))
        tk_params = {f"t{i}": l for i, l in enumerate(tanker_labels)}
        tk_params["m"] = month

        # 1) Monthly tanker subclass — port-agnostic ton + calls per
        # (period, kind, JENIS_KAPAL); we fold to subclass in Python.
        log.info("tanker: monthly by JENIS_KAPAL")
        monthly = collections.defaultdict(
            lambda: {"ton_b": 0.0, "ton_m": 0.0, "calls": 0})
        for yr, mo, kind, jk, tb, tm, n in conn.execute(text(
            f"SELECT data_year, data_month, kind, "
            f"       json_extract(raw_row, '{P_J_LK3}'), "
            f"       SUM({_ton_expr(P_T_B)}), SUM({_ton_expr(P_T_M)}), COUNT(*) "
            f"FROM cargo_snapshot WHERE snapshot_month=:m "
            f"  AND json_extract(raw_row, '{P_J_LK3}') IN ({tk_ph}) "
            f"GROUP BY 1,2,3,4"
        ), tk_params).fetchall():
            sub = classify_tanker_subclass(jk)
            period = f"{int(yr)}-{int(mo):02d}"
            key = (period, kind, sub)
            monthly[key]["ton_b"] += float(tb or 0)
            monthly[key]["ton_m"] += float(tm or 0)
            monthly[key]["calls"] += int(n or 0)

        # 2) Port × kind × JENIS_KAPAL → fold to (port, kind, subclass)
        log.info("tanker: port x JENIS_KAPAL")
        port_sub = collections.defaultdict(
            lambda: {"ton_b": 0.0, "ton_m": 0.0, "calls": 0})
        for port, kind, jk, tb, tm, n in conn.execute(text(
            f"SELECT cs.kode_pelabuhan, cs.kind, "
            f"       json_extract(cs.raw_row, '{P_J_LK3}'), "
            f"       SUM({_ton_expr(P_T_B)}), SUM({_ton_expr(P_T_M)}), COUNT(*) "
            f"FROM cargo_snapshot cs WHERE cs.snapshot_month=:m "
            f"  AND json_extract(cs.raw_row, '{P_J_LK3}') IN ({tk_ph}) "
            f"GROUP BY 1,2,3"
        ), tk_params).fetchall():
            sub = classify_tanker_subclass(jk)
            key = (port, kind, sub)
            port_sub[key]["ton_b"] += float(tb or 0)
            port_sub[key]["ton_m"] += float(tm or 0)
            port_sub[key]["calls"] += int(n or 0)

        # 3) Komoditi (BONGKAR + MUAT separately so we keep direction)
        log.info("tanker: komoditi BONGKAR")
        kom_sub = collections.defaultdict(
            lambda: {"ton_b": 0.0, "ton_m": 0.0, "calls_b": 0, "calls_m": 0})
        for jk, kind, kom, t, n in conn.execute(text(
            f"SELECT json_extract(raw_row, '{P_J_LK3}'), kind, "
            f"       json_extract(raw_row, '{P_K_B}'), "
            f"       SUM({_ton_expr(P_T_B)}), COUNT(*) "
            f"FROM cargo_snapshot WHERE snapshot_month=:m "
            f"  AND json_extract(raw_row, '{P_J_LK3}') IN ({tk_ph}) "
            f"  AND {_ton_expr(P_T_B)} > 0 "
            f"GROUP BY 1,2,3"
        ), tk_params).fetchall():
            if not kom or str(kom).strip() in ("", "-"):
                continue
            sub = classify_tanker_subclass(jk)
            key = (str(kom).strip(), sub, kind)
            kom_sub[key]["ton_b"] += float(t or 0)
            kom_sub[key]["calls_b"] += int(n or 0)
        log.info("tanker: komoditi MUAT")
        for jk, kind, kom, t, n in conn.execute(text(
            f"SELECT json_extract(raw_row, '{P_J_LK3}'), kind, "
            f"       json_extract(raw_row, '{P_K_M}'), "
            f"       SUM({_ton_expr(P_T_M)}), COUNT(*) "
            f"FROM cargo_snapshot WHERE snapshot_month=:m "
            f"  AND json_extract(raw_row, '{P_J_LK3}') IN ({tk_ph}) "
            f"  AND {_ton_expr(P_T_M)} > 0 "
            f"GROUP BY 1,2,3"
        ), tk_params).fetchall():
            if not kom or str(kom).strip() in ("", "-"):
                continue
            sub = classify_tanker_subclass(jk)
            key = (str(kom).strip(), sub, kind)
            kom_sub[key]["ton_m"] += float(t or 0)
            kom_sub[key]["calls_m"] += int(n or 0)

        # 4) Tanker fleet owners (vessels_snapshot)
        log.info("tanker: fleet owners")
        owner_rows = []
        for ow, jdk, n, sum_gt, max_gt in conn.execute(text(
            "SELECT nama_pemilik, "
            "       json_extract(raw_data, '$.JenisDetailKet') AS jdk, "
            "       COUNT(*), SUM(gt), MAX(gt) "
            "FROM vessels_snapshot WHERE snapshot_month=:m "
            "  AND nama_pemilik IS NOT NULL AND nama_pemilik != '' "
            "GROUP BY nama_pemilik, jdk"
        ), {"m": month}).fetchall():
            owner_rows.append((ow, jdk, int(n), float(sum_gt or 0), float(max_gt or 0)))

    # Fold owner_rows to tanker-only
    owner_tanker = collections.defaultdict(
        lambda: {"count": 0, "sum_gt": 0.0, "max_gt": 0.0,
                 "subclass_counts": collections.Counter()})
    for ow, jdk, n, sum_gt, max_gt in owner_rows:
        sector, vclass = classify_vessel_type(jdk)
        if sector != SECTOR_CARGO or vclass != CLS_TANKER:
            continue
        sub = classify_tanker_subclass(jdk)
        owner_tanker[ow]["count"] += n
        owner_tanker[ow]["sum_gt"] += sum_gt
        owner_tanker[ow]["max_gt"] = max(owner_tanker[ow]["max_gt"], max_gt)
        owner_tanker[ow]["subclass_counts"][sub] += n

    # Build outputs ----------------------------------------------------------
    # by_subclass — flatten across kinds (sum dn+ln)
    by_sub_agg = collections.defaultdict(
        lambda: {"dn": {"ton_b": 0.0, "ton_m": 0.0, "calls": 0},
                 "ln": {"ton_b": 0.0, "ton_m": 0.0, "calls": 0}})
    for (period, kind, sub), v in monthly.items():
        if kind not in ("dn", "ln"):
            continue
        by_sub_agg[sub][kind]["ton_b"] += v["ton_b"]
        by_sub_agg[sub][kind]["ton_m"] += v["ton_m"]
        by_sub_agg[sub][kind]["calls"] += v["calls"]
    by_subclass = []
    for sub, splits in by_sub_agg.items():
        ton_b_total = splits["dn"]["ton_b"] + splits["ln"]["ton_b"]
        ton_m_total = splits["dn"]["ton_m"] + splits["ln"]["ton_m"]
        calls_total = splits["dn"]["calls"] + splits["ln"]["calls"]
        ton_total = ton_b_total + ton_m_total
        avg_per_call = (ton_total / calls_total) if calls_total else 0
        by_subclass.append({
            "subclass": sub,
            "ton_bongkar_dn": round(splits["dn"]["ton_b"], 1),
            "ton_bongkar_ln": round(splits["ln"]["ton_b"], 1),
            "ton_muat_dn":    round(splits["dn"]["ton_m"], 1),
            "ton_muat_ln":    round(splits["ln"]["ton_m"], 1),
            "ton_total":      round(ton_total, 1),
            "calls_dn": int(splits["dn"]["calls"]),
            "calls_ln": int(splits["ln"]["calls"]),
            "calls_total": calls_total,
            "avg_ton_per_call": round(avg_per_call, 1),
        })
    by_subclass.sort(key=lambda r: -r["ton_total"])

    monthly_subclass = [
        {"period": p, "kind": k, "subclass": s,
         "ton_bongkar": round(v["ton_b"], 1),
         "ton_muat":    round(v["ton_m"], 1),
         "ton_total":   round(v["ton_b"] + v["ton_m"], 1),
         "calls":       int(v["calls"])}
        for (p, k, s), v in sorted(monthly.items())
    ]

    # Port aggregations: per (port, kind) total + per (port, subclass) ton
    port_balance_agg = collections.defaultdict(
        lambda: {"ton_b": 0.0, "ton_m": 0.0, "calls": 0})
    port_subclass_rows = []
    for (port, kind, sub), v in port_sub.items():
        port_balance_agg[(port, kind)]["ton_b"] += v["ton_b"]
        port_balance_agg[(port, kind)]["ton_m"] += v["ton_m"]
        port_balance_agg[(port, kind)]["calls"] += v["calls"]
        port_subclass_rows.append({
            "port": port, "kind": kind, "subclass": sub,
            "ton_bongkar": round(v["ton_b"], 1),
            "ton_muat":    round(v["ton_m"], 1),
            "ton_total":   round(v["ton_b"] + v["ton_m"], 1),
            "calls":       int(v["calls"]),
        })

    # Look up port names from the existing helper SQL
    name_map: dict[str, str] = {}
    with engine.connect() as conn:
        for k, n in conn.execute(text(
            "SELECT kode_pelabuhan, nama_pelabuhan FROM ports"
        )).fetchall():
            if n:
                name_map[k] = n

    port_balance = []
    for (port, kind), v in port_balance_agg.items():
        ton_total = v["ton_b"] + v["ton_m"]
        bongkar_ratio = (v["ton_b"] / ton_total) if ton_total else 0.0
        port_balance.append({
            "port": port,
            "name": name_map.get(port, ""),
            "kind": kind,
            "ton_bongkar": round(v["ton_b"], 1),
            "ton_muat":    round(v["ton_m"], 1),
            "ton_total":   round(ton_total, 1),
            "calls":       int(v["calls"]),
            "bongkar_share_pct": round(bongkar_ratio * 100.0, 2),
        })
    port_balance.sort(key=lambda r: -r["ton_total"])

    # Komoditi: top 200 by total ton across BONGKAR+MUAT, all kinds
    kom_agg = collections.defaultdict(
        lambda: {"ton_b": 0.0, "ton_m": 0.0, "calls_b": 0, "calls_m": 0,
                 "subclass": ""})
    for (kom, sub, kind), v in kom_sub.items():
        # Collapse kinds: store per (kom, sub)
        bucket = kom_agg[(kom, sub)]
        bucket["ton_b"] += v["ton_b"]
        bucket["ton_m"] += v["ton_m"]
        bucket["calls_b"] += v["calls_b"]
        bucket["calls_m"] += v["calls_m"]
        bucket["subclass"] = sub
    kom_rows = []
    for (kom, sub), v in kom_agg.items():
        kom_rows.append({
            "komoditi": kom,
            "subclass": sub,
            "ton_bongkar": round(v["ton_b"], 1),
            "ton_muat":    round(v["ton_m"], 1),
            "ton_total":   round(v["ton_b"] + v["ton_m"], 1),
            "calls":       int(v["calls_b"] + v["calls_m"]),
        })
    kom_rows.sort(key=lambda r: -r["ton_total"])
    kom_rows = kom_rows[:200]

    fleet_owners = []
    for ow, v in sorted(owner_tanker.items(), key=lambda kv: -kv[1]["sum_gt"])[:50]:
        sub_breakdown = dict(v["subclass_counts"])
        fleet_owners.append({
            "owner": ow,
            "tanker_count": int(v["count"]),
            "sum_gt": round(v["sum_gt"], 0),
            "max_gt": round(v["max_gt"], 0),
            "avg_gt": round(v["sum_gt"] / v["count"], 0) if v["count"] else 0,
            "subclass_counts": sub_breakdown,
        })

    return {
        "snapshot_month": month,
        "schema_version": 1,
        "by_subclass": by_subclass,
        "monthly_subclass": monthly_subclass,
        "port_subclass_rows": port_subclass_rows,
        "port_balance": port_balance,
        "komoditi_top": kom_rows,
        "fleet_owners": fleet_owners,
    }


def companies_financials_payload() -> dict:
    """Read data/companies_financials.yml and emit a chart-ready JSON.

    The YAML lives outside the snapshot pipeline because it's hand-curated
    -- IDX annual reports are released yearly, so we don't try to scrape
    them. The payload is denormalized to a flat list of {ticker, year,
    metric...} rows so the frontend can pivot client-side without
    re-implementing a YAML parser.

    Computed columns added per (company, year):
      net_margin     = net_income / revenue
      debt_to_assets = total_debt / total_assets
      roa            = net_income / total_assets
    """
    import yaml

    src = PROJECT_ROOT / "data" / "companies_financials.yml"
    if not src.exists():
        log.warning("companies_financials.yml not found at %s -- emitting empty payload",
                    src)
        return {"metadata": {}, "companies": [], "rows": []}

    with src.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    metadata = doc.get("metadata", {}) or {}
    companies_in = doc.get("companies", []) or []

    companies_out = []
    rows = []
    for c in companies_in:
        ticker = c.get("ticker") or "?"
        years = sorted((c.get("financials") or {}).keys())
        latest_year = years[-1] if years else None
        latest = (c.get("financials") or {}).get(latest_year, {}) if latest_year else {}
        companies_out.append({
            "ticker": ticker,
            "name": c.get("name") or "",
            "name_short": c.get("name_short") or c.get("name") or ticker,
            "ipo_year": c.get("ipo_year"),
            "sector_focus": c.get("sector_focus") or [],
            "homepage": c.get("homepage") or "",
            "data_quality": c.get("data_quality") or "unknown",
            "years": years,
            "latest_year": latest_year,
            "latest": latest,
        })
        for y in years:
            f_ = (c.get("financials") or {}).get(y) or {}
            rev = f_.get("revenue")
            ni = f_.get("net_income")
            ta = f_.get("total_assets")
            td = f_.get("total_debt")
            row = {
                "ticker": ticker,
                "name_short": c.get("name_short") or c.get("name") or ticker,
                "year": y,
                "revenue": rev,
                "net_income": ni,
                "total_assets": ta,
                "total_debt": td,
                "capex": f_.get("capex"),
                "fleet_count": f_.get("fleet_count"),
                "fleet_gt": f_.get("fleet_gt"),
                "net_margin": (ni / rev * 100.0) if (rev and ni is not None) else None,
                "debt_to_assets": (td / ta * 100.0) if (ta and td is not None) else None,
                "roa": (ni / ta * 100.0) if (ta and ni is not None) else None,
            }
            rows.append(row)

    return {
        "metadata": metadata,
        "companies": companies_out,
        "rows": rows,
    }


# ============================================================================
# Tanker cargo flow map payload
# ============================================================================
# Mirrors dashboard/app.py:_tanker_cargo_flow_map. Pre-aggregates origin →
# destination tanker lanes, port bubbles, and per-vessel rollups so the
# static client can render a Plotly Scattergeo without a server. The port
# coord lookup and komoditi → bucket palette duplicate the Streamlit copy
# rather than importing from `dashboard.*` (build_static.py must stay
# importable in CI without the dashboard's Streamlit deps).

_FLOW_PORT_COORDS: dict[str, tuple[float, float]] = {
    "IDBPN": (-1.27, 116.83), "IDDUM": (1.67, 101.45), "IDBTN": (-5.95, 106.05),
    "IDGRE": (-7.16, 112.65), "IDTRK": (3.30, 117.63), "IDTAN": (1.07, 104.21),
    "IDBAU": (-5.47, 122.62), "IDJKT": (-6.10, 106.88), "IDPNK": (-0.03, 109.34),
    "IDKBU": (-3.30, 116.20), "IDPNJ": (-5.45, 105.32), "IDSUB": (-7.20, 112.74),
    "IDPLM": (-2.99, 104.76), "IDTBR": (-1.00, 100.37), "IDAMQ": (-3.67, 128.18),
    "IDBNQ": (-6.87, 112.36), "IDBLW": (3.78, 98.69), "IDBIT": (1.44, 125.18),
    "IDPRN": (-7.71, 113.93), "IDSRI": (-0.50, 117.15), "IDPGX": (-2.10, 106.13),
    "IDMRA": (-6.10, 106.96), "IDDJB": (-1.65, 103.61), "IDCXP": (-7.73, 109.02),
    "IDSOQ": (-0.86, 131.25), "IDLUW": (-1.04, 122.79), "IDMAK": (-5.13, 119.41),
    "IDBTM": (1.12, 104.05), "IDSMQ": (-2.54, 112.94), "IDKUM": (-2.74, 111.74),
    "IDSRG": (-6.96, 110.42), "IDBJU": (-8.21, 114.37), "IDBXT": (0.13, 117.49),
    "IDIRU": (-6.33, 108.32), "IDLSW": (5.18, 97.15), "IDTMP": (3.22, 106.22),
    "IDNNX": (4.13, 117.66), "IDTTE": (0.79, 127.37), "IDTJB": (1.04, 103.39),
    "IDPBI": (-8.53, 115.51), "IDTRE": (2.15, 117.50), "IDTBO": (1.73, 128.00),
    "IDKOE": (-10.18, 123.61), "IDWED": (0.36, 127.93), "IDNTI": (-2.13, 133.51),
    "IDBOA": (-8.74, 115.21), "IDKDI": (-3.97, 122.52), "IDBNU": (-2.57, 121.94),
    "IDTLN": (-0.32, 103.16), "IDTJS": (2.85, 117.37), "IDSKI": (0.97, 117.95),
    "IDKTJ": (3.36, 99.45), "IDTUA": (-5.65, 132.74), "IDMOF": (-8.62, 122.20),
    "IDMKQ": (-8.49, 140.39), "IDLII": (-1.60, 127.50), "IDBYQ": (3.45, 117.85),
    "IDMKW": (-0.86, 134.06), "IDBIK": (-1.18, 136.08), "IDMUO": (-2.07, 105.16),
    "IDPAP": (-4.02, 119.62), "IDREO": (-8.30, 120.42), "IDSKL": (-6.13, 106.81),
    "IDBUI": (0.91, 128.32), "IDSTU": (-3.76, 115.29), "IDPKU": (0.50, 101.45),
    "IDKSB": (-5.74, 106.59), "IDKNL": (-2.05, 121.32), "IDBUT": (1.20, 102.30),
    "IDSUQ": (-0.48, 103.48), "IDSQN": (-2.05, 125.99), "IDWGP": (-9.66, 120.27),
    "IDBKS": (-3.79, 102.26), "IDBMU": (-8.45, 118.72), "IDPTL": (-0.86, 119.85),
    "IDSXK": (-7.97, 131.30), "IDWCI": (-5.32, 123.59), "IDMEN": (-8.33, 116.10),
    "IDLMA": (-1.13, 116.92),
}


_FLOW_PORT_ALIASES: dict[str, tuple[float, float] | None] = {
    # Foreign hubs (off-map; tagged "international")
    "SINGAPORE": None, "PORT KLANG": None, "PASIR GUDANG": None, "JOHOR": None,
    "TANJUNG PELEPAS": None, "TANJONG BIN": None, "MALAYSIA": None, "MELAKA": None,
    "PENGERANG": None, "MAP TA PHUT": None, "SRIRACHA": None, "KAOHSIUNG": None,
    "HONG KONG": None, "ZHOUSHAN": None, "ZHOUSHAN PT": None, "XIUYU": None,
    "XIUYU PT": None, "YEOSU": None, "BUSAN": None, "MUHAMMAD BIN QASIM": None,
    "CHATTOGRAM": None, "CHITTAGONG": None, "OFFSHORE FUJAIRAH": None,
    "FUJAIRAH": None, "RAS TANURA": None, "PORT LOUIS": None, "FREEPORT": None,
    "HOUSTON": None, "NEDERLAND": None, "ROTTERDAM": None, "BAA": None,
    "SOYO": None, "RAS LAFFAN": None, "DAMPIER": None, "HALDIA": None,
    "SOHAR": None, "RUWAIS": None, "RUWAIS PORT": None, "DAVAO": None,
    "GIRASSOL": None, "DOHA": None, "JEBEL ALI": None,
    # Indonesian terminals not in ports.nama_pelabuhan
    "MARUNDA": (-6.10, 106.96), "MUARA BARU": (-6.10, 106.81),
    "TANJUNG SEKONG": (-5.98, 106.05), "TANJUNG GEREM": (-5.95, 106.05),
    "MERAK": (-5.93, 106.00), "CILEGON": (-5.98, 106.05),
    "ANYER": (-6.06, 105.93), "KABIL": (1.06, 104.10),
    "WAYAME": (-3.62, 128.13), "BLANG LANCANG": (5.18, 97.15),
    "PLAJU": (-3.00, 104.78), "TUBAN": (-6.90, 112.05),
    "TUBAN TUKS PERTAMINA": (-6.90, 112.05), "BALONGAN": (-6.32, 108.39),
    "BALONGAN TERMINAL": (-6.32, 108.39), "AMPENAN": (-8.57, 116.08),
    "TUA PEJAT": (-2.07, 99.59), "BOOM BARU": (-2.99, 104.76),
    "TELUK KABUNG": (-1.05, 100.41), "TELUK SEMANGKA": (-5.85, 104.65),
    "TELUK JAKARTA": (-6.10, 106.88), "BAU-BAU": (-5.47, 122.62),
    "MALINAU": (3.59, 116.65), "TANJUNG MANGGIS": (-8.57, 115.55),
    "TELUK BAYUR": (-1.00, 100.37), "TANJUNG WANGI": (-8.21, 114.37),
    "JAKARTA": (-6.12, 106.88), "TG. PRIOK": (-6.10, 106.88),
    "PRIOK": (-6.10, 106.88), "SEMARANG": (-6.96, 110.42),
    "SURABAYA": (-7.20, 112.74), "SEMAMPIR": (-7.20, 112.74),
    "PADANG": (-1.00, 100.37), "MEDAN": (3.78, 98.69),
    "LHOKSEUMAWE": (5.18, 97.15), "BANGKA": (-2.10, 106.13),
    "PANGKAL BALAM": (-2.10, 106.13), "TANJUNG REDEP": (2.15, 117.50),
    "KAMPUNG BARU": (-1.27, 116.83), "BANJARMASIN": (-3.32, 114.59),
    "KOTABARU": (-3.30, 116.20), "KALBUT": (-7.74, 113.86),
    "KALBUT SITUBONDO": (-7.74, 113.86), "TARAHAN": (-5.55, 105.36),
    "TARJUN": (-3.65, 116.04), "CINTA": (-5.95, 106.20),
    "ARJUNA": (-5.95, 107.50), "SUNGAI PAKNING": (1.39, 102.13),
    "KENDAWANGAN": (-2.55, 110.21), "MEKAR PUTIH": (-8.59, 116.43),
    "MOROWALI": (-2.85, 121.85), "LAWE-LAWE": (-1.13, 116.92),
    "PATIMBAN": (-6.31, 107.91), "TANAH GROGOT": (-1.91, 116.20),
    "JABUNG TERMINAL": (-1.10, 104.30), "JABUNG": (-1.10, 104.30),
    "TANJUNG BARA": (-0.42, 117.55), "BUKIT TUA": (-6.27, 113.20),
    "POLEKO": (-3.97, 122.52), "PT. TIMAH": (-2.10, 106.13),
    "SENIPAH": (-0.95, 117.00), "PULANG PISAU": (-2.74, 114.07),
    "SAMPIT": (-2.54, 112.94), "BATULICIN": (-3.30, 116.20),
    "MUARA SATUI": (-3.85, 115.50), "BUNGUS": (-1.05, 100.41),
    "TANJUNG BUTON": (1.07, 102.30),
}


_FLOW_TERMINAL_KW_TAILS = (
    "TUKS PT", "TUKS PERTAMINA", "TUKS",
    "TERSUS PT", "TERSUS PERTAMINA", "TERSUS",
    "STS PERTAMINA", "STS PT", "STS",
    "PT. PERTAMINA", "PT PERTAMINA", "PERTAMINA",
    "TERMINAL KHUSUS", "TERMINAL", "JV",
)


def _flow_normalize_port(s) -> str | None:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    t = str(s).upper().strip()
    if not t:
        return None
    t = t.split("(", 1)[0].strip()
    t = t.split("/", 1)[0].strip()
    t = t.split(",", 1)[0].strip()
    for kw in _FLOW_TERMINAL_KW_TAILS:
        idx = t.find(" " + kw)
        if idx > 0:
            t = t[:idx].strip()
    return t if len(t) >= 3 else None


def _flow_classify_kom(label) -> str:
    if not label:
        return "기타"
    s = str(label).upper()
    # ----- Tanker liquids (existing buckets, order matters) -----
    if "CRUDE" in s or "MENTAH" in s:                                 return "Crude"
    if "CPO" in s or "PALM OIL" in s or "MINYAK SAWIT" in s:          return "CPO/팜오일"
    if "LNG" in s or "NATURAL GAS" in s or "GAS ALAM" in s:           return "LNG"
    if any(k in s for k in ("LPG", "ELPIJI", "PROPANE", "BUTANE")):   return "LPG"
    if any(k in s for k in ("PERTALITE", "PERTAMAX", "GASOLINE", "BENZIN", "MOGAS")):
        return "BBM-가솔린"
    if any(k in s for k in ("SOLAR", "DIESEL", "BIOSOLAR", "GASOIL", "GAS OIL")):
        return "BBM-디젤"
    if "AVTUR" in s or "JET" in s or "AVGAS" in s:                    return "BBM-항공유"
    if "BBM" in s:                                                    return "BBM-기타"
    if "CHEMICAL" in s or "KIMIA" in s:                               return "Chemical"
    if any(k in s for k in ("FAME", "BIODIESEL", "METHYL ESTER", "METIL ESTER")):
        return "FAME"
    if "ASPHALT" in s or "ASPAL" in s:                                return "아스팔트"
    if any(k in s for k in ("RBD", "OLEIN", "STEARIN", "PKO", "CPKO", "PKS")):
        return "팜 파생"
    if "MINYAK" in s or "VEGETABLE OIL" in s:                         return "기타 식용유"
    if "FUEL OIL" in s or "BUNKER" in s:                              return "벙커유"
    if "NAPHTHA" in s or "NAFTA" in s:                                return "Naphtha"
    if "KEROSEN" in s:                                                return "Kerosene"
    # ----- PR-38: dry-bulk + minerals + container (new buckets) -----
    # Coal — handles both Indonesian (BATU BARA, BATUBARA) and English
    # variants plus the common "STEAM COAL" / "STEAM COAL IN BULK".
    if any(k in s for k in ("BATU BARA", "BATUBARA", "STEAM COAL", "COAL")):
        return "Coal"
    if any(k in s for k in ("NICKEL", "NIKEL", "BIJIH NIKEL")):       return "Nickel"
    if any(k in s for k in ("BAUXITE", "BAUKSIT", "BIJIH BAUKSIT")):  return "Bauxite"
    if any(k in s for k in ("IRON ORE", "BIJIH BESI", "BESI BIJIH")): return "Iron Ore"
    if any(k in s for k in ("PETIKEMAS", "KONTAINER", "CONTAINER", "TEU")):
        return "Container"
    if any(k in s for k in ("CEMENT", "SEMEN", "KLINKER", "CLINKER")):
        return "Cement"
    if any(k in s for k in ("GENERAL CARGO", "GEN CARGO", "MUATAN UMUM", "BARANG UMUM")):
        return "General Cargo"
    return "기타"


_FLOW_KOM_PALETTE = {
    "Crude": "#0f172a",
    "BBM-가솔린": "#b91c1c",
    "BBM-디젤": "#92400e",
    "BBM-항공유": "#0e7490",
    "BBM-기타": "#6b7280",
    "벙커유": "#3f3f46",
    "CPO/팜오일": "#16a34a",
    "팜 파생": "#84cc16",
    "기타 식용유": "#65a30d",
    "FAME": "#a3e635",
    "LNG": "#0891b2",
    "LPG": "#f59e0b",
    "Chemical": "#7c3aed",
    "Naphtha": "#1e40af",
    "Kerosene": "#3b82f6",
    "아스팔트": "#27272a",
    "기타": "#9ca3af",
}


def tanker_flow_map_payload(month: str) -> dict:
    """Pre-aggregate tanker OD lanes for the docs/ Cargo tab map.

    Output schema (schema_version 1):
      buckets_ranked   — bucket names sorted by total ton DESC
      bucket_palette   — bucket → CSS color hex
      lanes            — [{o, d, lat_o, lon_o, lat_d, lon_d, bucket, dir, ton, calls, vessels}]
                         only mappable lanes (both endpoints have ID coords, no foreign,
                         self-loops dropped)
      ports            — [{port, lat, lon, ton}] with total ton across mapped lanes
      vessels          — top ~1500 ships by total ton, with by_bucket nested rollup so
                         the JS client can re-aggregate when bucket/direction filters change
      totals           — {plot_ton, intl_ton, unknown_ton}
    """
    import collections

    def jx(k: str) -> str:
        esc = k.replace("'", "''")
        return f"json_extract(raw_row, '$.\"{esc}\"')"

    def numexpr(jexpr: str) -> str:
        return f"CAST(NULLIF(NULLIF({jexpr}, '-'), '') AS REAL)"

    K_JK    = "('JENIS KAPAL', 'JENIS KAPAL')"
    K_KAPAL = "('KAPAL', 'KAPAL')"
    K_OP    = "('PERUSAHAAN', 'PERUSAHAAN')"
    K_ORIG  = "('TIBA', 'DARI')"
    K_DEST  = "('BERANGKAT', 'KE')"
    K_BK    = "('BONGKAR', 'KOMODITI')"
    K_BT    = "('BONGKAR', 'TON')"
    K_MK    = "('MUAT', 'KOMODITI')"
    K_MT    = "('MUAT', 'TON')"
    K_DWT   = "('UKURAN', 'DWT')"
    K_GT    = "('UKURAN', 'GT')"

    tanker_pred = (
        f"({jx(K_JK)} LIKE '%TANKER%' OR {jx(K_JK)} LIKE '%MINYAK%' OR "
        f" {jx(K_JK)} LIKE '%KIMIA%' OR {jx(K_JK)} LIKE '%CHEMICAL%' OR "
        f" {jx(K_JK)} LIKE '%LPG%' OR {jx(K_JK)} LIKE '%LNG%' OR "
        f" {jx(K_JK)} LIKE '%GAS CARRIER%' OR {jx(K_JK)} LIKE '%PENGANGKUT GAS%' OR "
        f" {jx(K_JK)} LIKE '%LIQUEFIED%' OR {jx(K_JK)} LIKE '%OIL BARGE%' OR "
        f" {jx(K_JK)} LIKE '%VEGETABLE OIL%' OR {jx(K_JK)} LIKE '%MINYAK NABATI%' OR "
        f" {jx(K_JK)} LIKE '%FAME%' OR {jx(K_JK)} LIKE '%ASPHALT%' OR "
        f" {jx(K_JK)} LIKE '%TANGKI%' OR {jx(K_JK)} LIKE '%SPOB%')"
    )

    sql = text(
        f"SELECT {jx(K_KAPAL)} AS kapal, {jx(K_JK)} AS jenis_kapal, "
        f"  {jx(K_OP)} AS operator, "
        f"  {jx(K_ORIG)} AS origin, {jx(K_DEST)} AS destination, "
        f"  {jx(K_BK)} AS bongkar_kom, {numexpr(jx(K_BT))} AS bongkar_ton, "
        f"  {jx(K_MK)} AS muat_kom, {numexpr(jx(K_MT))} AS muat_ton, "
        f"  {numexpr(jx(K_DWT))} AS dwt, {numexpr(jx(K_GT))} AS gt "
        f"FROM cargo_snapshot WHERE snapshot_month=:m AND {tanker_pred}"
    )

    log.info("flow map: build coord lookup")
    coord_map: dict[str, tuple[float, float]] = {}
    foreign: set[str] = set()
    with engine.connect() as conn:
        ports_rows = conn.execute(text(
            "SELECT kode_pelabuhan, nama_pelabuhan FROM ports"
        )).fetchall()
    for code, name in ports_rows:
        c = _FLOW_PORT_COORDS.get(code)
        if c and name:
            key = _flow_normalize_port(name)
            if key:
                coord_map[key] = c
    for k, v in _FLOW_PORT_ALIASES.items():
        if v is None:
            foreign.add(k)
        else:
            coord_map[k] = v

    log.info("flow map: load tanker rows")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"m": month})
    if df.empty:
        return {
            "snapshot_month": month, "schema_version": 1,
            "buckets_ranked": [], "bucket_palette": _FLOW_KOM_PALETTE,
            "lanes": [], "ports": [], "vessels": [],
            "totals": {"plot_ton": 0, "intl_ton": 0, "unknown_ton": 0},
        }

    # Long form: row per (kapal, origin, dest, kom, ton, dir)
    b = df[["kapal", "operator", "jenis_kapal", "origin", "destination",
            "bongkar_kom", "bongkar_ton", "gt", "dwt"]].rename(
        columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
    b["dir"] = "B"
    m = df[["kapal", "operator", "jenis_kapal", "origin", "destination",
            "muat_kom", "muat_ton", "gt", "dwt"]].rename(
        columns={"muat_kom": "kom", "muat_ton": "ton"})
    m["dir"] = "M"
    long = pd.concat([b, m], ignore_index=True)
    long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
    long = long[long["ton"] > 0].copy()
    long["bucket"] = long["kom"].map(_flow_classify_kom)
    long["o_norm"] = long["origin"].map(_flow_normalize_port)
    long["d_norm"] = long["destination"].map(_flow_normalize_port)
    long["o_coord"] = long["o_norm"].map(lambda k: coord_map.get(k))
    long["d_coord"] = long["d_norm"].map(lambda k: coord_map.get(k))
    long["o_foreign"] = long["o_norm"].isin(foreign)
    long["d_foreign"] = long["d_norm"].isin(foreign)

    has_o = long["o_coord"].notna()
    has_d = long["d_coord"].notna()
    intl = long["o_foreign"] | long["d_foreign"]

    intl_ton = float(long.loc[intl, "ton"].sum())
    plot = long.loc[has_o & has_d & ~intl].copy()
    plot_ton = float(plot["ton"].sum())
    unknown_ton = float(long["ton"].sum() - intl_ton - plot_ton)

    # Drop self-loops on map (origin == destination at port-name granularity)
    plot = plot[plot["o_norm"] != plot["d_norm"]].copy()

    # ---- Lanes: per (o, d, bucket, dir) ----
    if not plot.empty:
        plot["lat_o"] = plot["o_coord"].map(lambda c: c[0])
        plot["lon_o"] = plot["o_coord"].map(lambda c: c[1])
        plot["lat_d"] = plot["d_coord"].map(lambda c: c[0])
        plot["lon_d"] = plot["d_coord"].map(lambda c: c[1])
        lanes_g = (plot.groupby(
                        ["o_norm", "d_norm", "lat_o", "lon_o", "lat_d", "lon_d",
                         "bucket", "dir"])
                       .agg(ton=("ton", "sum"),
                            calls=("ton", "size"),
                            vessels=("kapal", "nunique"))
                       .reset_index())
        lanes = [
            {"o": r.o_norm, "d": r.d_norm,
             "lat_o": round(float(r.lat_o), 3), "lon_o": round(float(r.lon_o), 3),
             "lat_d": round(float(r.lat_d), 3), "lon_d": round(float(r.lon_d), 3),
             "bucket": r.bucket, "dir": r.dir,
             "ton": round(float(r.ton), 1),
             "calls": int(r.calls),
             "vessels": int(r.vessels)}
            for r in lanes_g.itertuples(index=False)
        ]
    else:
        lanes = []

    # ---- Ports: aggregate by port across mappable rows ----
    if not plot.empty:
        port_o = plot[["o_norm", "lat_o", "lon_o", "ton"]].rename(
            columns={"o_norm": "port", "lat_o": "lat", "lon_o": "lon"})
        port_d = plot[["d_norm", "lat_d", "lon_d", "ton"]].rename(
            columns={"d_norm": "port", "lat_d": "lat", "lon_d": "lon"})
        port_all = pd.concat([port_o, port_d], ignore_index=True)
        port_g = (port_all.groupby(["port", "lat", "lon"])["ton"].sum()
                              .reset_index()
                              .sort_values("ton", ascending=False))
        ports_out = [
            {"port": r.port,
             "lat": round(float(r.lat), 3), "lon": round(float(r.lon), 3),
             "ton": round(float(r.ton), 1)}
            for r in port_g.itertuples(index=False)
        ]
    else:
        ports_out = []

    # ---- Vessels: per kapal × bucket × dir (filter-aware re-aggregation in JS) ----
    vsel = long.dropna(subset=["kapal"]).copy()
    vessels_out: list = []
    if not vsel.empty:
        # Top route per (kapal, dir) — most frequent OD label
        vsel["route_label"] = (vsel["origin"].fillna("?").astype(str)
                                + " → "
                                + vsel["destination"].fillna("?").astype(str))
        top_route_idx: dict = {}
        for (kp, di), grp in vsel.groupby(["kapal", "dir"]):
            top_counts = grp["route_label"].value_counts()
            if not top_counts.empty:
                top_route_idx[(kp, di)] = (
                    f"{top_counts.index[0]} ({int(top_counts.iloc[0])}회)"
                )

        def _safe_max(s):
            v = pd.to_numeric(s, errors="coerce").max()
            return 0.0 if pd.isna(v) else float(v)

        def _safe_mode(s):
            d = s.dropna()
            if d.empty:
                return ""
            mo = d.mode()
            return str(mo.iloc[0]) if not mo.empty else ""

        meta_g = (vsel.groupby("kapal")
                       .agg(operator=("operator", _safe_mode),
                            jenis_kapal=("jenis_kapal", _safe_mode),
                            gt=("gt", _safe_max),
                            dwt=("dwt", _safe_max),
                            ton_total=("ton", "sum"))
                       .reset_index()
                       .sort_values("ton_total", ascending=False)
                       .head(1500))
        kept = set(meta_g["kapal"])

        bd_g = (vsel[vsel["kapal"].isin(kept)]
                     .groupby(["kapal", "bucket", "dir"])
                     .agg(ton=("ton", "sum"), calls=("ton", "size"))
                     .reset_index())

        by_bk: dict = collections.defaultdict(dict)
        for r in bd_g.itertuples(index=False):
            slot = by_bk[r.kapal].setdefault(
                r.bucket, {"B": {"ton": 0.0, "calls": 0},
                           "M": {"ton": 0.0, "calls": 0}})
            slot[r.dir] = {"ton": round(float(r.ton), 1), "calls": int(r.calls)}

        for r in meta_g.itertuples(index=False):
            kp = r.kapal
            vessels_out.append({
                "kapal": kp,
                "operator": r.operator or "",
                "jenis_kapal": r.jenis_kapal or "",
                "gt": round(float(r.gt), 0) if r.gt else 0,
                "dwt": round(float(r.dwt), 0) if r.dwt else 0,
                "by_bucket": by_bk.get(kp, {}),
                "top_route_b": top_route_idx.get((kp, "B"), ""),
                "top_route_m": top_route_idx.get((kp, "M"), ""),
            })

    # ---- Bucket ranking (across all tanker ton, for legend ordering) ----
    bucket_ton = long.groupby("bucket")["ton"].sum().sort_values(ascending=False)
    buckets_ranked = [str(b) for b in bucket_ton.index.tolist()]

    return {
        "snapshot_month": month,
        "schema_version": 1,
        "buckets_ranked": buckets_ranked,
        "bucket_palette": _FLOW_KOM_PALETTE,
        "lanes": lanes,
        "ports": ports_out,
        "vessels": vessels_out,
        "totals": {
            "plot_ton": round(plot_ton, 1),
            "intl_ton": round(intl_ton, 1),
            "unknown_ton": round(unknown_ton, 1),
        },
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
        "sector_taxonomy.json": sector_taxonomy_payload(),
        "cargo_sector_monthly.json": cargo_sector_monthly_payload(month),
        "kpi_summary.json": kpi_summary_payload(month, change_month),
        "tanker_focus.json": tanker_focus_payload(month),
        "tanker_flow_map.json": tanker_flow_map_payload(month),
        "companies_financials.json": companies_financials_payload(),
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
