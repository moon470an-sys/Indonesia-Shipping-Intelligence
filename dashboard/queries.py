"""Read-only data access for the Streamlit dashboard.

All queries are cached at the Streamlit layer (see app.py). DB writes never happen
here — the dashboard is a passive consumer of the snapshot/changes tables.
"""
from __future__ import annotations

import json
from typing import Optional

import pandas as pd
from sqlalchemy import text

from backend.db.database import engine


# ------------------------- snapshot months -------------------------

def vessel_snapshot_months() -> list[str]:
    sql = "SELECT DISTINCT snapshot_month FROM vessels_snapshot ORDER BY snapshot_month DESC"
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(text(sql)).fetchall()]


def cargo_snapshot_months() -> list[str]:
    sql = "SELECT DISTINCT snapshot_month FROM cargo_snapshot ORDER BY snapshot_month DESC"
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(text(sql)).fetchall()]


def change_months() -> list[str]:
    """Months that have at least one change record (vessel or cargo)."""
    sql = (
        "SELECT change_month FROM ("
        "SELECT DISTINCT change_month FROM vessels_changes "
        "UNION "
        "SELECT DISTINCT change_month FROM cargo_changes"
        ") ORDER BY change_month DESC"
    )
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(text(sql)).fetchall()]


# ------------------------- KPI tiles -------------------------

def vessel_overview(snapshot_month: str) -> dict:
    sql = text(
        """
        SELECT
          COUNT(*)                   AS total,
          COUNT(DISTINCT search_code) AS codes,
          AVG(gt)                    AS avg_gt,
          MAX(gt)                    AS max_gt
        FROM vessels_snapshot
        WHERE snapshot_month = :m
        """
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"m": snapshot_month}).fetchone()
    return {
        "total": int(row[0] or 0),
        "codes": int(row[1] or 0),
        "avg_gt": float(row[2] or 0),
        "max_gt": float(row[3] or 0),
    }


def cargo_overview(snapshot_month: str) -> dict:
    sql = text(
        """
        SELECT
          COUNT(*) AS rows_total,
          COUNT(DISTINCT kode_pelabuhan) AS ports,
          COUNT(DISTINCT (kode_pelabuhan || '|' || data_year || '-' || data_month || '|' || kind)) AS keys
        FROM cargo_snapshot
        WHERE snapshot_month = :m
        """
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"m": snapshot_month}).fetchone()
    return {
        "rows": int(row[0] or 0),
        "ports": int(row[1] or 0),
        "keys": int(row[2] or 0),
    }


def change_kpis(month: str) -> dict:
    with engine.connect() as conn:
        v = conn.execute(text(
            "SELECT change_type, COUNT(*) FROM vessels_changes "
            "WHERE change_month = :m GROUP BY change_type"
        ), {"m": month}).fetchall()
        c = conn.execute(text(
            "SELECT change_type, COUNT(*) FROM cargo_changes "
            "WHERE change_month = :m GROUP BY change_type"
        ), {"m": month}).fetchall()
    out = {
        "vessel_added": 0, "vessel_removed": 0, "vessel_modified_cells": 0,
        "cargo_added": 0, "cargo_removed": 0, "cargo_revised_cells": 0,
    }
    for t, n in v:
        if t == "ADDED":    out["vessel_added"] = int(n)
        if t == "REMOVED":  out["vessel_removed"] = int(n)
        if t == "MODIFIED": out["vessel_modified_cells"] = int(n)
    for t, n in c:
        if t == "ADDED":    out["cargo_added"] = int(n)
        if t == "REMOVED":  out["cargo_removed"] = int(n)
        if t == "REVISED":  out["cargo_revised_cells"] = int(n)
    return out


# ------------------------- vessels -------------------------

def vessels(snapshot_month: str, search: str = "", search_code: str = "",
           jenis_kapal: str = "", limit: int = 1000) -> pd.DataFrame:
    where = ["snapshot_month = :m"]
    params: dict = {"m": snapshot_month, "limit": limit}
    if search:
        where.append(
            "(LOWER(nama_kapal) LIKE :q OR LOWER(call_sign) LIKE :q "
            "OR LOWER(nama_pemilik) LIKE :q OR LOWER(imo) LIKE :q)"
        )
        params["q"] = f"%{search.lower()}%"
    if search_code:
        where.append("search_code = :sc")
        params["sc"] = search_code
    if jenis_kapal:
        where.append("jenis_kapal = :jk")
        params["jk"] = jenis_kapal
    sql = (
        "SELECT search_code, nama_kapal, call_sign, jenis_kapal, nama_pemilik, "
        "       gt, panjang, lebar, dalam, imo, tahun, vessel_key "
        "FROM vessels_snapshot "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY gt DESC NULLS LAST "
        "LIMIT :limit"
    )
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def vessels_full(snapshot_month: str) -> pd.DataFrame:
    """Full vessel snapshot with selected fields parsed out of raw_data JSON.

    Used by the Fleet page to drive client-side filters and charts. Cached at
    the Streamlit layer because parsing JSON for ~100k rows is non-trivial.
    """
    sql = text(
        "SELECT search_code, vessel_key, nama_kapal, eks_nama_kapal, call_sign, "
        "       jenis_kapal, nama_pemilik, gt, isi_bersih, panjang, lebar, dalam, "
        "       length_of_all, imo, tahun, raw_data "
        "FROM vessels_snapshot WHERE snapshot_month = :m"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"m": snapshot_month})

    def _get(d: dict, *keys):
        for k in keys:
            v = d.get(k)
            if v not in (None, ""):
                return v
        return None

    def _parse(s):
        if not s:
            return {}
        try:
            return json.loads(s)
        except Exception:
            return {}

    parsed = df["raw_data"].map(_parse)
    df["mesin"] = parsed.map(lambda d: _get(d, "Mesin"))
    df["mesin_type"] = parsed.map(lambda d: _get(d, "MesinType"))
    df["bendera"] = parsed.map(lambda d: _get(d, "BenderaAsal"))
    df["jenis_detail"] = parsed.map(lambda d: _get(d, "JenisDetailKet"))
    df["bahan_utama"] = parsed.map(lambda d: _get(d, "BahanUtamaKapal"))
    df["kategori_kapal"] = parsed.map(lambda d: _get(d, "kategoriKapal"))
    df["daya"] = parsed.map(lambda d: _get(d, "Daya"))
    df["pelabuhan_pendaftaran"] = parsed.map(lambda d: _get(d, "PelabuhanPendaftaran"))
    df["tahun_num"] = pd.to_numeric(df["tahun"], errors="coerce")
    df["loa"] = df["length_of_all"].where(df["length_of_all"].notna() & (df["length_of_all"] > 0),
                                          df["panjang"])
    return df.drop(columns=["raw_data"])


def vessel_search_codes(snapshot_month: str) -> list[str]:
    sql = text(
        "SELECT search_code, COUNT(*) AS n FROM vessels_snapshot "
        "WHERE snapshot_month = :m AND search_code IS NOT NULL "
        "GROUP BY search_code ORDER BY n DESC"
    )
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(sql, {"m": snapshot_month}).fetchall()]


def vessel_types(snapshot_month: str, top: int = 30) -> pd.DataFrame:
    sql = text(
        "SELECT jenis_kapal AS type, COUNT(*) AS count, "
        "       AVG(gt) AS avg_gt, SUM(gt) AS sum_gt "
        "FROM vessels_snapshot "
        "WHERE snapshot_month = :m AND jenis_kapal IS NOT NULL AND jenis_kapal != '' "
        "GROUP BY jenis_kapal ORDER BY count DESC LIMIT :top"
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"m": snapshot_month, "top": top})


def vessel_owners(snapshot_month: str, top: int = 20) -> pd.DataFrame:
    sql = text(
        "SELECT nama_pemilik AS owner, COUNT(*) AS fleet, "
        "       SUM(gt) AS total_gt, AVG(gt) AS avg_gt "
        "FROM vessels_snapshot "
        "WHERE snapshot_month = :m AND nama_pemilik IS NOT NULL AND nama_pemilik != '' "
        "GROUP BY nama_pemilik ORDER BY fleet DESC LIMIT :top"
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"m": snapshot_month, "top": top})


def vessel_age_distribution(snapshot_month: str) -> pd.DataFrame:
    sql = text(
        "SELECT tahun, COUNT(*) AS count "
        "FROM vessels_snapshot "
        "WHERE snapshot_month = :m AND tahun IS NOT NULL AND tahun != '' "
        "GROUP BY tahun ORDER BY tahun"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"m": snapshot_month})
    df["tahun"] = pd.to_numeric(df["tahun"], errors="coerce")
    df = df.dropna(subset=["tahun"]).copy()
    df["tahun"] = df["tahun"].astype(int)
    return df.sort_values("tahun")


def gt_distribution(snapshot_month: str) -> pd.DataFrame:
    sql = text(
        "SELECT gt FROM vessels_snapshot "
        "WHERE snapshot_month = :m AND gt IS NOT NULL AND gt > 0"
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"m": snapshot_month})


# ------------------------- ports / cargo -------------------------

def ports() -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(
            "SELECT kode_pelabuhan, nama_pelabuhan FROM ports ORDER BY kode_pelabuhan"
        ), conn)


def cargo_summary(snapshot_month: str) -> pd.DataFrame:
    """Per-(port, year, month, kind) aggregates for the dashboard.

    Computed from cargo_snapshot.raw_row at query time so we don't depend on
    cargo_monthly_summary being up to date.
    """
    sql = text(
        "SELECT kode_pelabuhan, data_year, data_month, kind, COUNT(*) AS rows "
        "FROM cargo_snapshot WHERE snapshot_month = :m "
        "GROUP BY kode_pelabuhan, data_year, data_month, kind"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"m": snapshot_month})
    if df.empty:
        return df
    df["period"] = df["data_year"].astype(str) + "-" + df["data_month"].astype(int).map("{:02d}".format)
    return df


def port_traffic(snapshot_month: str, top: int = 20) -> pd.DataFrame:
    sql = text(
        "SELECT cs.kode_pelabuhan, p.nama_pelabuhan, "
        "       SUM(CASE WHEN cs.kind='dn' THEN 1 ELSE 0 END) AS rows_dn, "
        "       SUM(CASE WHEN cs.kind='ln' THEN 1 ELSE 0 END) AS rows_ln, "
        "       COUNT(*) AS rows_total, "
        "       COUNT(DISTINCT cs.data_year || '-' || cs.data_month) AS months_covered "
        "FROM cargo_snapshot cs LEFT JOIN ports p ON p.kode_pelabuhan = cs.kode_pelabuhan "
        "WHERE cs.snapshot_month = :m "
        "GROUP BY cs.kode_pelabuhan, p.nama_pelabuhan "
        "ORDER BY rows_total DESC LIMIT :top"
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"m": snapshot_month, "top": top})


def monthly_traffic(snapshot_month: str) -> pd.DataFrame:
    sql = text(
        "SELECT data_year, data_month, kind, COUNT(*) AS rows, "
        "       COUNT(DISTINCT kode_pelabuhan) AS ports "
        "FROM cargo_snapshot WHERE snapshot_month = :m "
        "GROUP BY data_year, data_month, kind ORDER BY data_year, data_month"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"m": snapshot_month})
    if df.empty:
        return df
    df["period"] = df["data_year"].astype(str) + "-" + df["data_month"].astype(int).map("{:02d}".format)
    return df


# ------------------------- changes -------------------------

def vessel_changes(month: str, change_type: Optional[str] = None,
                   field_name: Optional[str] = None, search: str = "",
                   limit: int = 5000) -> pd.DataFrame:
    where = ["change_month = :m"]
    params: dict = {"m": month, "limit": limit}
    if change_type and change_type != "ALL":
        where.append("change_type = :ct")
        params["ct"] = change_type
    if field_name and field_name != "ALL":
        where.append("field_name = :fn")
        params["fn"] = field_name
    if search:
        where.append("(LOWER(vessel_key) LIKE :q OR LOWER(field_name) LIKE :q "
                     "OR LOWER(old_value) LIKE :q OR LOWER(new_value) LIKE :q)")
        params["q"] = f"%{search.lower()}%"
    sql = (
        "SELECT change_type, vessel_key, field_name, old_value, new_value, detected_at "
        "FROM vessels_changes "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY detected_at DESC, vessel_key LIMIT :limit"
    )
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def cargo_changes(month: str, change_type: Optional[str] = None,
                  port: Optional[str] = None, kind: Optional[str] = None,
                  limit: int = 5000) -> pd.DataFrame:
    where = ["change_month = :m"]
    params: dict = {"m": month, "limit": limit}
    if change_type and change_type != "ALL":
        where.append("change_type = :ct")
        params["ct"] = change_type
    if port and port != "ALL":
        where.append("kode_pelabuhan = :p")
        params["p"] = port
    if kind and kind != "ALL":
        where.append("kind = :k")
        params["k"] = kind
    sql = (
        "SELECT change_type, kode_pelabuhan, data_year, data_month, kind, "
        "       field_name, old_value, new_value, delta, delta_pct, detected_at "
        "FROM cargo_changes "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY ABS(COALESCE(delta_pct, 0)) DESC, kode_pelabuhan LIMIT :limit"
    )
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


# ------------------------- ingestion runs -------------------------

def ingestion_runs(limit: int = 30) -> pd.DataFrame:
    sql = text(
        "SELECT id, run_month, task, started_at, finished_at, status, "
        "       total_targets, succeeded, failed FROM ingestion_runs "
        "ORDER BY id DESC LIMIT :limit"
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"limit": limit})


def ingestion_run_notes(run_id: int) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT notes FROM ingestion_runs WHERE id = :i"),
                           {"i": run_id}).fetchone()
    if not row or not row[0]:
        return {}
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return {"raw": row[0]}
