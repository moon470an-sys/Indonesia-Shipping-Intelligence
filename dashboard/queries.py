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


def tankers_full(snapshot_month: str) -> pd.DataFrame:
    """Tanker-classified subset of the fleet with subclass annotation.

    Uses backend.taxonomy to keep classification logic in one place. The
    returned DataFrame is the same shape as ``vessels_full`` plus two extra
    columns:

    * ``vessel_class`` — taxonomy class ("Tanker" only — others filtered out)
    * ``tanker_subclass`` — Crude Oil | Product | Chemical | LPG | LNG |
      FAME / Vegetable Oil | Water | UNKNOWN
    """
    from backend.taxonomy import (
        CLS_TANKER, classify_tanker_subclass, classify_vessel_type,
    )

    df = vessels_full(snapshot_month)
    if df.empty:
        return df

    # Prefer the more descriptive jenis_detail label; fall back to jenis_kapal.
    label = df["jenis_detail"].fillna(df["jenis_kapal"])
    classified = label.map(lambda s: classify_vessel_type(s))
    df = df.assign(
        sector=classified.map(lambda t: t[0]),
        vessel_class=classified.map(lambda t: t[1]),
    )
    tk = df[df["vessel_class"] == CLS_TANKER].copy()
    tk["tanker_subclass"] = label[tk.index].map(classify_tanker_subclass)
    return tk


def cargo_vessels_full(snapshot_month: str) -> pd.DataFrame:
    """Cargo-sector vessels with class + tanker subclass annotation.

    Mirrors `vessels_full` shape and adds:
      * sector           — taxonomy sector (always 'CARGO' in this filter)
      * vessel_class     — Tanker | Container | Bulk Carrier | General Cargo |
                            Other Cargo
      * tanker_subclass  — Crude/Product/Chemical/LPG/LNG/FAME/Water/UNKNOWN
                            for vessel_class == 'Tanker'; empty string otherwise
      * age              — int(snapshot_year) - tahun_num (NaN if missing)

    Fishing / Passenger / Offshore-support / Non-commercial vessels are
    filtered out so downstream Fleet/Cargo views focus on commercial cargo.
    """
    from backend.taxonomy import (
        SECTOR_CARGO, CLS_TANKER, classify_tanker_subclass,
        classify_vessel_type,
    )

    df = vessels_full(snapshot_month)
    if df.empty:
        return df

    label = df["jenis_detail"].fillna(df["jenis_kapal"])
    classified = label.map(lambda s: classify_vessel_type(s))
    df = df.assign(
        sector=classified.map(lambda t: t[0]),
        vessel_class=classified.map(lambda t: t[1]),
    )
    cargo = df[df["sector"] == SECTOR_CARGO].copy()
    if cargo.empty:
        return cargo

    is_tanker = cargo["vessel_class"] == CLS_TANKER
    sub = pd.Series("", index=cargo.index, dtype=object)
    sub.loc[is_tanker] = label.loc[cargo.index[is_tanker]].map(classify_tanker_subclass)
    cargo["tanker_subclass"] = sub

    snap_yr = int(snapshot_month[:4]) if snapshot_month else None
    if snap_yr is not None:
        age = snap_yr - pd.to_numeric(cargo["tahun"], errors="coerce")
        cargo["age"] = age.where(age >= 0)
    else:
        cargo["age"] = pd.NA
    return cargo


def cargo_flows(snapshot_month: str) -> pd.DataFrame:
    """Generic LK3 cargo flows — excludes fishing / passenger / pure tug /
    pleasure vessels.

    Mirrors the shape of `tanker_cargo_flows` (same columns) but covers all
    commercial cargo categories (tankers, container, bulk, general cargo,
    barge, etc.) — used by the dedicated Cargo tab with commodity filtering
    and OD-map rendering.

    Filtering is SQL-side via LIKE on the LK3 ``JENIS KAPAL`` field. We
    EXCLUDE labels containing keywords for non-cargo segments and accept
    anything else, so partially-classified rows are still surfaced.
    """
    def j(k: str) -> str:
        escaped = k.replace("'", "''")
        return f"json_extract(raw_row, '$.\"{escaped}\"')"

    n = lambda j_expr: f"CAST(NULLIF(NULLIF({j_expr}, '-'), '') AS REAL)"

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
    K_LOA   = "('UKURAN', 'LOA')"
    K_DRMAX = "('DRAFT', 'MAX')"
    K_TIBA  = "('TIBA', 'TANGGAL')"
    K_DEP   = "('BERANGKAT', 'TANGGAL')"

    # Exclude non-cargo segments by JENIS KAPAL keywords. Patterns mirror the
    # taxonomy "fishing / passenger / offshore / non-commercial" buckets but
    # are written for SQL LIKE.
    exclude_kws = (
        "%FISH%", "%IKAN%", "%FISHERY%", "%FISHING%",
        "%PURSE SEINER%", "%LIVESTOCK%", "%TERNAK%",
        "%PENUMPANG%", "%PASSENGER%", "%FERRY%", "%CRUISE%",
        "%KAPAL CEPAT%", "%WATER BUS%", "%CATAMARAN%",
        "%KAPAL PERANG%", "%PATROL%", "%PATROLI%", "%NAVY%",
        "%YACHT%", "%WISATA%", "%PILOT BOAT%", "%MEDICAL%",
        "%RESCUE%", "%MOORING BOAT%",
        # Pure tugs / dredgers / supply vessels — they carry no cargo of
        # interest for the LK3 commodity view. Keep barges (tongkang) since
        # they often haul oil / dry cargo.
        "%TUG BOAT%", "%MOTOR TUNDA%", "%PUSHER TUG%", "%HARBOUR TUG%",
        "%AHTS%", "%ANCHOR HANDLING%", "%PLATFORM SUPPLY%", "%PSV%",
        "%DREDGER%", "%HOPPER%", "%SUCTION%", "%KAPAL HISAP%",
        "%CABLE LAYING%", "%PIPE LAYING%", "%SEISMIC%", "%RESEARCH%",
        "%FLOATING STORAGE%",
    )
    pred_parts = " AND ".join([f"COALESCE({j(K_JK)}, '') NOT LIKE '{kw}'"
                                for kw in exclude_kws])

    sql = text(
        f"SELECT data_year, data_month, kind, kode_pelabuhan, "
        f"  {j(K_KAPAL)} AS kapal, {j(K_JK)} AS jenis_kapal, {j(K_OP)} AS operator, "
        f"  {j(K_ORIG)} AS origin, {j(K_DEST)} AS destination, "
        f"  {j(K_TIBA)} AS tiba_tanggal, {j(K_DEP)} AS berangkat_tanggal, "
        f"  {j(K_BK)} AS bongkar_kom, {n(j(K_BT))} AS bongkar_ton, "
        f"  {j(K_MK)} AS muat_kom, {n(j(K_MT))} AS muat_ton, "
        f"  {n(j(K_DWT))} AS dwt, {n(j(K_GT))} AS gt, "
        f"  {n(j(K_LOA))} AS loa, {n(j(K_DRMAX))} AS draft_max "
        f"FROM cargo_snapshot "
        f"WHERE snapshot_month = :m AND ({pred_parts})"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"m": snapshot_month})
    if df.empty:
        return df
    df["period"] = (df["data_year"].astype(str) + "-" +
                    df["data_month"].astype(int).map("{:02d}".format))
    return df


def tanker_cargo_flows(snapshot_month: str) -> pd.DataFrame:
    """Slim tanker-only cargo dataset for the Tanker Cargo Flow sub-tabs.

    Filters cargo_snapshot via SQL LIKE on the LK3 ``JENIS KAPAL`` field —
    keyword-based, deliberately broad. The returned DataFrame is a one-shot
    extract of the tanker rows for ``snapshot_month`` and is cheap to slice
    further in pandas (commodities / OD pairs / monthly seasonality).

    Columns
    -------
    data_year, data_month, kind, kode_pelabuhan
    kapal, jenis_kapal, operator
    origin, destination
    tiba_tanggal, berangkat_tanggal       (raw 'DD-MM-YYYY HH:MM:SS' strings)
    bongkar_kom, bongkar_ton
    muat_kom, muat_ton
    dwt, gt, loa, draft_max
    period         (YYYY-MM convenience derived from data_year/data_month)
    """
    # Tuple-style JSON keys (LK3 MultiIndex stringified as a Python tuple).
    # The keys themselves contain single quotes — when embedded inside a
    # SQL string literal they must be doubled, hence the .replace below.
    def j(k: str) -> str:
        escaped = k.replace("'", "''")
        return f"json_extract(raw_row, '$.\"{escaped}\"')"

    n = lambda j_expr: f"CAST(NULLIF(NULLIF({j_expr}, '-'), '') AS REAL)"

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
    K_LOA   = "('UKURAN', 'LOA')"
    K_DRMAX = "('DRAFT', 'MAX')"
    K_TIBA  = "('TIBA', 'TANGGAL')"
    K_DEP   = "('BERANGKAT', 'TANGGAL')"

    # Tanker keyword filter — SQL-side LIKE for speed.
    tanker_pred = (
        f"({j(K_JK)} LIKE '%TANKER%' OR {j(K_JK)} LIKE '%MINYAK%' OR "
        f" {j(K_JK)} LIKE '%KIMIA%' OR {j(K_JK)} LIKE '%CHEMICAL%' OR "
        f" {j(K_JK)} LIKE '%LPG%' OR {j(K_JK)} LIKE '%LNG%' OR "
        f" {j(K_JK)} LIKE '%GAS CARRIER%' OR {j(K_JK)} LIKE '%PENGANGKUT GAS%' OR "
        f" {j(K_JK)} LIKE '%LIQUEFIED%' OR {j(K_JK)} LIKE '%OIL BARGE%' OR "
        f" {j(K_JK)} LIKE '%VEGETABLE OIL%' OR {j(K_JK)} LIKE '%MINYAK NABATI%' OR "
        f" {j(K_JK)} LIKE '%FAME%' OR {j(K_JK)} LIKE '%ASPHALT%' OR "
        f" {j(K_JK)} LIKE '%TANGKI%' OR {j(K_JK)} LIKE '%SPOB%')"
    )

    sql = text(
        f"SELECT data_year, data_month, kind, kode_pelabuhan, "
        f"  {j(K_KAPAL)} AS kapal, {j(K_JK)} AS jenis_kapal, {j(K_OP)} AS operator, "
        f"  {j(K_ORIG)} AS origin, {j(K_DEST)} AS destination, "
        f"  {j(K_TIBA)} AS tiba_tanggal, {j(K_DEP)} AS berangkat_tanggal, "
        f"  {j(K_BK)} AS bongkar_kom, {n(j(K_BT))} AS bongkar_ton, "
        f"  {j(K_MK)} AS muat_kom, {n(j(K_MT))} AS muat_ton, "
        f"  {n(j(K_DWT))} AS dwt, {n(j(K_GT))} AS gt, "
        f"  {n(j(K_LOA))} AS loa, {n(j(K_DRMAX))} AS draft_max "
        f"FROM cargo_snapshot "
        f"WHERE snapshot_month = :m AND {tanker_pred}"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"m": snapshot_month})
    if df.empty:
        return df
    df["period"] = (df["data_year"].astype(str) + "-" +
                    df["data_month"].astype(int).map("{:02d}".format))
    return df


def tanker_snapshot_kpis(snapshot_month: str) -> dict | None:
    """Single-snapshot summary KPIs used by the cross-snapshot trend chart.

    Returns a flat dict so the caller can stack rows from multiple snapshots
    into a DataFrame for line plotting. Returns ``None`` if the snapshot has
    no tanker data.
    """
    fleet = tankers_full(snapshot_month)
    flows = tanker_cargo_flows(snapshot_month)
    if fleet.empty and flows.empty:
        return None

    out: dict = {"snapshot": snapshot_month}
    cur_yr = int(snapshot_month[:4])

    # Fleet side
    out["fleet_count"] = int(len(fleet))
    gt = pd.to_numeric(fleet.get("gt"), errors="coerce").fillna(0)
    out["fleet_gt_sum"] = float(gt.sum())
    yrs = pd.to_numeric(fleet.get("tahun"), errors="coerce")
    age = (cur_yr - yrs).where(cur_yr - yrs >= 0)
    out["fleet_avg_age"] = float(age.mean()) if age.notna().any() else None
    out["aged_25_count"] = int((age >= 25).sum())

    # Subclass mix (counts)
    if "tanker_subclass" in fleet.columns:
        sub_counts = fleet["tanker_subclass"].value_counts().to_dict()
        for sub in ("Crude Oil", "Product", "Chemical", "LPG", "LNG",
                    "FAME / Vegetable Oil", "Water"):
            out[f"fleet_{sub.replace(' / ', '_').replace(' ', '_')}"] = int(
                sub_counts.get(sub, 0))

    # Cargo side
    if not flows.empty:
        bton = pd.to_numeric(flows["bongkar_ton"], errors="coerce").fillna(0)
        mton = pd.to_numeric(flows["muat_ton"], errors="coerce").fillna(0)
        out["cargo_rows"] = int(len(flows))
        out["cargo_total_ton"] = float((bton + mton).sum())
        out["cargo_unique_kapal"] = int(flows["kapal"].nunique())
        out["cargo_unique_operators"] = int(flows["operator"].nunique())
        out["cargo_unique_ports"] = int(flows["kode_pelabuhan"].nunique())

        # Top1 operator ton share
        op_ton = (flows.assign(ton=bton + mton)
                       .dropna(subset=["operator"])
                       .groupby("operator")["ton"].sum())
        if not op_ton.empty:
            out["top_op_share_pct"] = float(
                op_ton.max() / op_ton.sum() * 100) if op_ton.sum() > 0 else 0.0
            out["top_op_name"] = op_ton.idxmax()

        # Per-commodity tons (selected key buckets only — keep schema stable)
        kom_buckets = {
            "Crude": ("CRUDE", "MENTAH"),
            "BBM_Gasoline": ("PERTALITE", "PERTAMAX", "GASOLINE", "BENZIN"),
            "BBM_Diesel": ("SOLAR", "DIESEL", "BIOSOLAR", "GASOIL"),
            "BBM_Avtur": ("AVTUR", "JET A"),
            "CPO_Palm": ("CPO", "PALM OIL", "MINYAK SAWIT", "OLEIN", "STEARIN"),
            "LPG": ("LPG", "ELPIJI"),
            "LNG": ("LNG", "NATURAL GAS"),
            "Chemical": ("CHEMICAL", "KIMIA"),
            "FAME": ("FAME", "BIODIESEL", "METIL ESTER"),
        }
        kom_text = (flows["bongkar_kom"].fillna("").astype(str)
                     + " " + flows["muat_kom"].fillna("").astype(str))
        kom_text = kom_text.str.upper()
        ton_total = bton + mton
        for label, kws in kom_buckets.items():
            mask = kom_text.apply(lambda s: any(k in s for k in kws))
            out[f"ton_{label}"] = float(ton_total[mask].sum())
    else:
        out.update({
            "cargo_rows": 0, "cargo_total_ton": 0.0,
            "cargo_unique_kapal": 0, "cargo_unique_operators": 0,
            "cargo_unique_ports": 0, "top_op_share_pct": 0.0,
            "top_op_name": None,
        })

    return out


def tanker_snapshot_trend() -> pd.DataFrame:
    """Stack `tanker_snapshot_kpis` for every available snapshot.

    Returns an empty DataFrame if no snapshots exist. Used by the Trend
    sub-tab on the Tanker page.
    """
    snaps = vessel_snapshot_months()
    if not snaps:
        return pd.DataFrame()
    rows = []
    for s in snaps:
        k = tanker_snapshot_kpis(s)
        if k:
            rows.append(k)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("snapshot")
    return df


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

def validator_summary(snapshot_month: str | None = None) -> dict:
    """Aggregate validator activity for a snapshot (or all snapshots).

    Returns counts by validator table (fleet / cargo) and by field. Empty
    fields are absent from the dict — the consumer should treat missing as 0.
    """
    where_v = "WHERE 1=1" if snapshot_month is None else "WHERE snapshot_month = :m"
    where_c = "WHERE 1=1" if snapshot_month is None else "WHERE snapshot_month = :m"
    params: dict = {} if snapshot_month is None else {"m": snapshot_month}
    out: dict = {"fleet": {}, "cargo": {}}
    with engine.connect() as conn:
        # fleet
        try:
            for r in conn.execute(text(
                f"SELECT field, COUNT(*) AS n FROM vessels_validation_log "
                f"{where_v} GROUP BY field ORDER BY n DESC"), params):
                out["fleet"][r[0]] = int(r[1])
        except Exception:
            pass
        # cargo
        try:
            for r in conn.execute(text(
                f"SELECT field, COUNT(*) AS n FROM cargo_validation_log "
                f"{where_c} GROUP BY field ORDER BY n DESC"), params):
                out["cargo"][r[0]] = int(r[1])
        except Exception:
            pass
    return out


def validator_recent_fixes(table: str, snapshot_month: str | None = None,
                           limit: int = 200) -> pd.DataFrame:
    """Recent validator corrections for fleet ('vessels') or cargo."""
    if table not in ("vessels", "cargo"):
        raise ValueError(f"unknown table {table!r}")
    tbl = "vessels_validation_log" if table == "vessels" else "cargo_validation_log"
    key_col = "vessel_key" if table == "vessels" else "cargo_row_id"
    where = "WHERE 1=1" if snapshot_month is None else "WHERE snapshot_month = :m"
    params: dict = {"limit": limit}
    if snapshot_month is not None:
        params["m"] = snapshot_month
    sql = text(
        f"SELECT snapshot_month, {key_col} AS key, field, "
        f"       original_value, corrected_value, rule, applied_at "
        f"FROM {tbl} {where} "
        f"ORDER BY id DESC LIMIT :limit"
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params=params)


def coverage_status(snapshot_month: str) -> dict:
    """Compute coverage gaps for a snapshot.

    Returns:
      * fleet_codes_present / expected — set sizes
      * cargo_period_count — number of (data_year, data_month) periods
      * cargo_port_count   — distinct ports with cargo rows
      * port_master_count  — distinct ports in `ports` master
      * cargo_key_count    — (port × period × kind) combinations seen
      * cargo_key_expected — (master_ports × periods × 2 kinds)
    """
    from backend.config import SEARCH_CODES

    out: dict = {
        "fleet_codes_expected": len(SEARCH_CODES),
        "fleet_codes_present": 0,
        "fleet_codes_missing": [],
        "cargo_period_count": 0,
        "cargo_port_count": 0,
        "port_master_count": 0,
        "cargo_key_count": 0,
        "cargo_key_expected": 0,
        "cargo_periods": [],
    }
    with engine.connect() as conn:
        codes = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT search_code FROM vessels_snapshot "
            "WHERE snapshot_month = :m AND search_code IS NOT NULL"
        ), {"m": snapshot_month}) if r[0]]
        present = set(codes)
        out["fleet_codes_present"] = len(present)
        out["fleet_codes_missing"] = sorted(set(SEARCH_CODES) - present)

        out["port_master_count"] = conn.execute(text(
            "SELECT COUNT(*) FROM ports")).scalar_one() or 0

        periods_rows = conn.execute(text(
            "SELECT data_year, data_month, COUNT(*) AS n "
            "FROM cargo_snapshot WHERE snapshot_month = :m "
            "GROUP BY data_year, data_month "
            "ORDER BY data_year, data_month"
        ), {"m": snapshot_month}).fetchall()
        out["cargo_periods"] = [
            {"year": r[0], "month": r[1], "rows": r[2]} for r in periods_rows
        ]
        out["cargo_period_count"] = len(periods_rows)
        out["cargo_port_count"] = conn.execute(text(
            "SELECT COUNT(DISTINCT kode_pelabuhan) FROM cargo_snapshot "
            "WHERE snapshot_month = :m"
        ), {"m": snapshot_month}).scalar_one() or 0
        out["cargo_key_count"] = conn.execute(text(
            "SELECT COUNT(DISTINCT kode_pelabuhan || '|' || data_year "
            "       || '-' || data_month || '|' || kind) "
            "FROM cargo_snapshot WHERE snapshot_month = :m"
        ), {"m": snapshot_month}).scalar_one() or 0
        out["cargo_key_expected"] = (out["port_master_count"]
                                      * out["cargo_period_count"] * 2)
    return out


def _load_idx_issuers() -> list[dict]:
    """Read the hand-curated IDX shipping issuer list from YAML.

    Source: ``data/companies_financials.yml``. Returns a list of dicts
    with ticker, name, name_short, sector_focus, financials. Empty list
    if the file is missing.
    """
    import yaml
    from backend.config import PROJECT_ROOT
    src = PROJECT_ROOT / "data" / "companies_financials.yml"
    if not src.exists():
        return []
    try:
        with src.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        return doc.get("companies", []) or []
    except Exception:
        return []


# Match keywords per ticker (uppercase, substring against nama_pemilik).
# Tightened to actual owner-name patterns observed in vessels_snapshot —
# loose substrings like "SAMUDERA" hit dozens of unrelated PT *SAMUDERA*
# entities that aren't part of SMDR group.
_IDX_MATCH_KEYWORDS = {
    "SMDR": ("PT. SAMUDERA INDONESIA TBK", "PT SAMUDERA INDONESIA TBK"),
    "TMAS": ("TEMPURAN EMAS", "TEMASLINE"),
    "PSSI": ("PELITA SAMUDERA",),
    "HITS": ("HUMPUSS",),  # broad — catches HUMPUSS TRANSPORTASI KIMIA etc.
    "BULL": ("BUANA LINTAS LAUTAN",),
    "SOCI": ("SOECHI",),
    "MBSS": ("MITRABAHTERA SEGARA",),
    "NELY": ("NELLY DWI PUTRI", "PELAYARAN NELLY"),
    "WINS": ("WINTERMAR",),
}


def idx_listed_tanker_match(snapshot_month: str) -> pd.DataFrame:
    """Cross-reference IDX-listed shipping issuers against the tanker fleet.

    Returns a DataFrame with one row per matched (ticker, vessel) — useful
    for surfacing tradable equity vehicles for tanker investment routing.
    Matching is via uppercase substring of ``_IDX_MATCH_KEYWORDS`` against
    ``nama_pemilik``.
    """
    fleet = tankers_full(snapshot_month)
    if fleet.empty:
        return fleet

    issuers = {c["ticker"]: c for c in _load_idx_issuers()}
    if not issuers:
        return pd.DataFrame()

    fleet = fleet.assign(
        owner_upper=fleet["nama_pemilik"].fillna("").astype(str).str.upper()
    )

    matched_rows = []
    for ticker, kws in _IDX_MATCH_KEYWORDS.items():
        if ticker not in issuers:
            continue
        info = issuers[ticker]
        mask = pd.Series(False, index=fleet.index)
        for kw in kws:
            mask = mask | fleet["owner_upper"].str.contains(
                kw, regex=False, na=False)
        sub = fleet[mask].copy()
        if sub.empty:
            continue
        sub["ticker"] = ticker
        sub["issuer_name"] = info.get("name_short") or info.get("name") or ticker
        sub["sector_focus"] = ", ".join(info.get("sector_focus") or [])
        sub["ipo_year"] = info.get("ipo_year")
        matched_rows.append(sub)

    if not matched_rows:
        return pd.DataFrame()
    return pd.concat(matched_rows, ignore_index=True)


def publicly_listed_tanker_owners(snapshot_month: str) -> pd.DataFrame:
    """All tanker owners with 'Tbk' suffix — broad publicly-listed surface.

    Catches owners that may not be in the curated YAML — Tbk is the standard
    Indonesian indicator for an IDX-listed company. Useful as a complementary
    surface to ``idx_listed_tanker_match`` when the YAML lookup is incomplete.
    """
    fleet = tankers_full(snapshot_month)
    if fleet.empty:
        return fleet
    owner_u = fleet["nama_pemilik"].fillna("").astype(str).str.upper()
    has_tbk = owner_u.str.contains(r"\bTBK\b", regex=True, na=False)
    return fleet[has_tbk].copy()


# All known Pertamina entity name patterns observed in vessels_snapshot.
# Owner-side (nama_pemilik) catches ~all subsidiary variants; operator-side
# (LK3 PERUSAHAAN) is dominated by a single name "PT. PERTAMINA TRANS KONTINENTAL".
_PERTAMINA_OWNER_KEYWORDS = ("PERTAMINA",)


def pertamina_fleet(snapshot_month: str) -> pd.DataFrame:
    """All tankers in the Pertamina ecosystem (any PERTAMINA name in owner)."""
    fleet = tankers_full(snapshot_month)
    if fleet.empty:
        return fleet
    own_u = fleet["nama_pemilik"].fillna("").astype(str).str.upper()
    mask = pd.Series(False, index=fleet.index)
    for kw in _PERTAMINA_OWNER_KEYWORDS:
        mask = mask | own_u.str.contains(kw, regex=False, na=False)
    return fleet[mask].copy()


def pertamina_operator_activity(snapshot_month: str) -> pd.DataFrame:
    """LK3 rows where the operator (PERUSAHAAN) is a Pertamina entity."""
    flows = tanker_cargo_flows(snapshot_month)
    if flows.empty:
        return flows
    op_u = flows["operator"].fillna("").astype(str).str.upper()
    return flows[op_u.str.contains("PERTAMINA", regex=False, na=False)].copy()


def korean_affiliated_tankers(snapshot_month: str) -> pd.DataFrame:
    """Tankers with Korean affiliation (flag, owner name, or vessel name).

    Signals (any one matches → flagged, with `kr_reason` recording why):

    * **Korean Flag**  — ``bendera`` ∈ {Korea South, KR}
    * **Korean Owner** — ``nama_pemilik`` contains KORINDO, KOREA, HYUNDAI,
      SAMSUNG, HANJIN, HMM, POSCO, DAEWOO, KUKDONG, SHINHAN, etc.
    * **Korean Name**  — ``nama_kapal`` references Korean cities (BUSAN, SEOUL,
      ULSAN, INCHEON) or Korean conglomerate names

    Returns the full ``tankers_full`` columnset plus ``kr_reason`` (semicolon-
    joined) and ``kr_signal`` (most-specific category).
    """
    fleet = tankers_full(snapshot_month)
    if fleet.empty:
        return fleet

    bendera = fleet["bendera"].fillna("").astype(str).str.upper()
    owner = fleet["nama_pemilik"].fillna("").astype(str).str.upper()
    name = fleet["nama_kapal"].fillna("").astype(str).str.upper()

    # Owner signals — Korean conglomerates / Korean-Indonesian JVs
    OWNER_KW = (
        "KORINDO", "KOREA", "KOREAN", "HYUNDAI", "SAMSUNG", "HANJIN",
        "DAEWOO", "POSCO", "HMM", "KUKDONG", "SHINHAN", "DOOSAN",
        "HANARO", "DAESAN",
    )
    NAME_KW = (
        "BUSAN", "SEOUL", "ULSAN", "INCHEON", "DAEJEON", "GWANGJU",
    )
    FLAG_KW = ("KOREA SOUTH", "SOUTH KOREA", "KR")

    def reasons(b: str, o: str, n: str) -> tuple[str, str]:
        rs: list[str] = []
        signal = ""
        if any(k in b for k in FLAG_KW):
            rs.append("flag")
            signal = "Korean Flag"
        if any(k in o for k in OWNER_KW):
            rs.append("owner")
            signal = signal or "Korean Owner"
        if any(k in n for k in NAME_KW):
            rs.append("name")
            signal = signal or "Korean Name"
        return ";".join(rs), signal

    pairs = [reasons(b, o, n) for b, o, n in zip(bendera, owner, name)]
    fleet = fleet.assign(
        kr_reason=[p[0] for p in pairs],
        kr_signal=[p[1] for p in pairs],
    )
    return fleet[fleet["kr_reason"] != ""].copy()


def vessel_utilization(snapshot_month: str) -> pd.DataFrame:
    """Per-tanker LK3 activity intensity over the 24-month cargo window.

    Joins ``tankers_full`` (Indonesian-flag tanker fleet) to ``tanker_cargo_flows``
    by uppercase-stripped vessel name. Returns one row per tanker with:

    * activity_rows  — total LK3 rows attributed to this name
    * months_active  — distinct (data_year, data_month) periods seen
    * total_ton      — BONGKAR + MUAT cargo over the window
    * unique_operators / unique_ports
    * util_pct       — months_active / 24 × 100
    * status         — Idle / Light / Active / Heavy bucket

    Notes
    -----
    Matching is by name only (no IMO cross-check). False positives possible
    when multiple tankers share a name; false negatives when LK3 KAPAL field
    has subtle spelling differences from registered nama_kapal.
    """
    fleet = tankers_full(snapshot_month)
    flows = tanker_cargo_flows(snapshot_month)
    if fleet.empty:
        return pd.DataFrame()

    fleet = fleet.assign(
        kapal_norm=fleet["nama_kapal"].fillna("").str.upper().str.strip(),
    )

    if flows.empty:
        merged = fleet.copy()
        for col, default in (("activity_rows", 0), ("months_active", 0),
                              ("total_ton", 0.0), ("unique_operators", 0),
                              ("unique_ports", 0)):
            merged[col] = default
    else:
        flows = flows.assign(
            kapal_norm=flows["kapal"].fillna("").str.upper().str.strip(),
            ton_total=(pd.to_numeric(flows["bongkar_ton"], errors="coerce").fillna(0)
                        + pd.to_numeric(flows["muat_ton"], errors="coerce").fillna(0)),
        )
        activity = (flows.groupby("kapal_norm")
                          .agg(activity_rows=("kapal", "size"),
                               months_active=("period", "nunique"),
                               total_ton=("ton_total", "sum"),
                               unique_operators=("operator", "nunique"),
                               unique_ports=("kode_pelabuhan", "nunique"))
                          .reset_index())
        merged = fleet.merge(activity, on="kapal_norm", how="left").fillna({
            "activity_rows": 0, "months_active": 0, "total_ton": 0.0,
            "unique_operators": 0, "unique_ports": 0,
        })

    # Drop empty-name rows (kapal_norm == "") — can't match those
    merged = merged[merged["kapal_norm"] != ""].copy()

    merged["util_pct"] = (merged["months_active"] / 24.0 * 100).round(1)

    def _tier(pct: float) -> str:
        if pct >= 75:   return "Heavy (≥75%)"
        if pct >= 50:   return "Active (50–75%)"
        if pct >= 25:   return "Light (25–50%)"
        return "Idle (<25%)"

    merged["status"] = merged["util_pct"].map(_tier)
    return merged


def cargo_vessel_utilization(snapshot_month: str) -> pd.DataFrame:
    """Per-cargo-vessel LK3 activity intensity, across all cargo classes.

    Generalizes `vessel_utilization` (tanker-only) to the full cargo fleet
    by joining `cargo_vessels_full` to `cargo_flows` via uppercase-stripped
    vessel name. Returns one row per cargo vessel with the same activity
    columns plus the `vessel_class` and `tanker_subclass` annotations from
    the fleet side.

    Bucketing (24mo window):

    * Idle (<25%) ........ months_active < 6
    * Light (25–50%) ..... 6–12 months active
    * Active (50–75%) .... 12–18 months active
    * Heavy (≥75%) ....... ≥18 months active

    Notes
    -----
    Name-only matching (no IMO). Same caveats as `vessel_utilization`.
    """
    fleet = cargo_vessels_full(snapshot_month)
    flows = cargo_flows(snapshot_month)
    if fleet.empty:
        return pd.DataFrame()

    fleet = fleet.assign(
        kapal_norm=fleet["nama_kapal"].fillna("").str.upper().str.strip(),
    )

    if flows.empty:
        merged = fleet.copy()
        for col, default in (("activity_rows", 0), ("months_active", 0),
                              ("total_ton", 0.0), ("unique_operators", 0),
                              ("unique_ports", 0)):
            merged[col] = default
    else:
        flows = flows.assign(
            kapal_norm=flows["kapal"].fillna("").str.upper().str.strip(),
            ton_total=(pd.to_numeric(flows["bongkar_ton"], errors="coerce").fillna(0)
                        + pd.to_numeric(flows["muat_ton"], errors="coerce").fillna(0)),
        )
        activity = (flows.groupby("kapal_norm")
                          .agg(activity_rows=("kapal", "size"),
                               months_active=("period", "nunique"),
                               total_ton=("ton_total", "sum"),
                               unique_operators=("operator", "nunique"),
                               unique_ports=("kode_pelabuhan", "nunique"))
                          .reset_index())
        merged = fleet.merge(activity, on="kapal_norm", how="left").fillna({
            "activity_rows": 0, "months_active": 0, "total_ton": 0.0,
            "unique_operators": 0, "unique_ports": 0,
        })

    merged = merged[merged["kapal_norm"] != ""].copy()
    merged["util_pct"] = (merged["months_active"] / 24.0 * 100).round(1)

    def _tier(pct: float) -> str:
        if pct >= 75:   return "Heavy (≥75%)"
        if pct >= 50:   return "Active (50–75%)"
        if pct >= 25:   return "Light (25–50%)"
        return "Idle (<25%)"

    merged["status"] = merged["util_pct"].map(_tier)
    return merged


def vessel_lookup(name_q: str = "", imo_q: str = "",
                   limit: int = 50) -> pd.DataFrame:
    """Search ``vessels_snapshot`` across all snapshots.

    Returns one row per (vessel_key, snapshot_month). LIKE-based partial
    match on uppercased name + IMO. The result is intentionally small;
    intended for an interactive lookup, not bulk data export.
    """
    name_q = (name_q or "").strip().upper()
    imo_q = (imo_q or "").strip()
    if not name_q and not imo_q:
        return pd.DataFrame()

    where = []
    params: dict = {"limit": limit}
    if name_q:
        where.append(
            "(UPPER(nama_kapal) LIKE :nq OR UPPER(eks_nama_kapal) LIKE :nq "
            "OR UPPER(call_sign) LIKE :nq)"
        )
        params["nq"] = f"%{name_q}%"
    if imo_q:
        where.append("imo LIKE :iq")
        params["iq"] = f"%{imo_q}%"

    sql = (
        "SELECT snapshot_month, vessel_key, nama_kapal, eks_nama_kapal, "
        "       call_sign, jenis_kapal, nama_pemilik, gt, panjang, lebar, "
        "       dalam, length_of_all, imo, tahun, search_code "
        "FROM vessels_snapshot "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY snapshot_month DESC, gt DESC NULLS LAST "
        "LIMIT :limit"
    )
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def vessel_cargo_activity(name_q: str, snapshot_month: str | None = None,
                           limit: int = 500) -> pd.DataFrame:
    """LK3 activity rows whose ``KAPAL`` field matches ``name_q``.

    Uppercase substring match. Optionally restricted to one snapshot.
    Returns the slim columns useful for an "activity history" timeline.
    """
    name_q = (name_q or "").strip().upper()
    if not name_q:
        return pd.DataFrame()

    def j(k: str) -> str:
        escaped = k.replace("'", "''")
        return f"json_extract(raw_row, '$.\"{escaped}\"')"

    n = lambda j_expr: f"CAST(NULLIF(NULLIF({j_expr}, '-'), '') AS REAL)"

    K_KAPAL = "('KAPAL', 'KAPAL')"
    K_OP = "('PERUSAHAAN', 'PERUSAHAAN')"
    K_JK = "('JENIS KAPAL', 'JENIS KAPAL')"
    K_TIBA = "('TIBA', 'TANGGAL')"
    K_DEP = "('BERANGKAT', 'TANGGAL')"
    K_BTON = "('BONGKAR', 'TON')"
    K_BKOM = "('BONGKAR', 'KOMODITI')"
    K_MTON = "('MUAT', 'TON')"
    K_MKOM = "('MUAT', 'KOMODITI')"
    K_GT = "('UKURAN', 'GT')"
    K_DWT = "('UKURAN', 'DWT')"
    K_ORI = "('TIBA', 'DARI')"
    K_DEST_K = "('BERANGKAT', 'KE')"

    where = [
        f"UPPER({j(K_KAPAL)}) LIKE :nq",
    ]
    params: dict = {"nq": f"%{name_q}%", "limit": limit}
    if snapshot_month is not None:
        where.append("snapshot_month = :m")
        params["m"] = snapshot_month

    sql = text(
        f"SELECT snapshot_month, kode_pelabuhan, data_year, data_month, kind, "
        f"  {j(K_KAPAL)} AS kapal, {j(K_OP)} AS operator, "
        f"  {j(K_JK)} AS jenis_kapal, "
        f"  {j(K_ORI)} AS origin, {j(K_DEST_K)} AS destination, "
        f"  {j(K_TIBA)} AS tiba_tanggal, {j(K_DEP)} AS berangkat_tanggal, "
        f"  {j(K_BKOM)} AS bongkar_kom, {n(j(K_BTON))} AS bongkar_ton, "
        f"  {j(K_MKOM)} AS muat_kom, {n(j(K_MTON))} AS muat_ton, "
        f"  {n(j(K_GT))} AS gt, {n(j(K_DWT))} AS dwt "
        f"FROM cargo_snapshot "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY data_year DESC, data_month DESC "
        f"LIMIT :limit"
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params=params)


def validator_extreme_fixes(snapshot_month: str | None = None,
                              ratio_threshold: float = 1000.0,
                              limit: int = 200) -> pd.DataFrame:
    """Validator log rows where ``|original / corrected| ≥ threshold``.

    These are the most spectacular upstream typos — useful for diagnosing
    systematic source-data issues. Pulls from both fleet and cargo logs and
    tags ``source`` ('vessels' or 'cargo') so the caller can split.
    """
    rows = []
    where_v = "WHERE 1=1" if snapshot_month is None else "WHERE snapshot_month = :m"
    params: dict = {"limit": limit}
    if snapshot_month is not None:
        params["m"] = snapshot_month

    with engine.connect() as conn:
        for tbl, key, src in (
            ("vessels_validation_log", "vessel_key", "vessels"),
            ("cargo_validation_log", "cargo_row_id", "cargo"),
        ):
            try:
                sql = text(
                    f"SELECT snapshot_month, {key} AS key, field, "
                    f"  original_value, corrected_value, rule, applied_at "
                    f"FROM {tbl} {where_v} "
                    f"  AND ABS(corrected_value) > 0 "
                    f"  AND ABS(original_value / corrected_value) >= :rt "
                    f"ORDER BY ABS(original_value / corrected_value) DESC "
                    f"LIMIT :limit"
                )
                df = pd.read_sql(sql, conn, params={**params, "rt": ratio_threshold})
                if not df.empty:
                    df["source"] = src
                    rows.append(df)
            except Exception:
                continue

    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out["magnitude_x"] = (out["original_value"]
                           / out["corrected_value"].replace(0, pd.NA)).round(0)
    return out.sort_values("magnitude_x", ascending=False, key=abs)


def residual_fleet_anomalies(snapshot_month: str) -> pd.DataFrame:
    """Currently-implausible fleet values still in vessels_snapshot.

    Looks for values that violate the validator's absolute envelope after
    the validator has already run. These are bugs the validator failed to
    catch (e.g. iter #3 IDCXP LOA=535m case).
    """
    sql = text(
        """
        SELECT snapshot_month, vessel_key, nama_kapal, jenis_kapal,
               nama_pemilik, gt, panjang, lebar, dalam, length_of_all,
               imo, tahun
        FROM vessels_snapshot
        WHERE snapshot_month = :m
          AND (
            panjang > 500 OR length_of_all > 500
            OR lebar > 80 OR dalam > 40
            OR (panjang > 0 AND lebar > 0 AND lebar > panjang)
            OR (lebar > 0 AND dalam > 0 AND dalam > lebar * 1.2)
          )
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"m": snapshot_month})


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
