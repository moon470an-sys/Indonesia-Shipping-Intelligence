"""Build the docs/derived/*.json payloads consumed by PR-C / PR-D / PR-E.

Per INSTRUCTIONS.md §3, this script transforms the already-aggregated
docs/data/*.json payloads (built by backend.build_static) plus a handful
of targeted SQL queries into six derived files:

    docs/derived/meta.json
    docs/derived/subclass_facts.json
    docs/derived/route_facts.json
    docs/derived/owner_profile.json
    docs/derived/recent_events.json
    docs/derived/owner_ticker_map.json

Outputs are pretty-printed (indent=2) — they are small enough that the
extra bytes are dominated by the JSON tree, not whitespace.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Console on Windows defaults to cp949 — force UTF-8 for our em-dashes etc.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA = DOCS / "data"
DERIVED = DOCS / "derived"
DB = ROOT / "data" / "shipping_bi.db"

# Make `import backend.taxonomy` work when the script is invoked directly
# from the repo root (PR-C: tanker fleet age aggregation).
sys.path.insert(0, str(ROOT))

# Manual seed map per INSTRUCTIONS.md §3. owner_ticker_map.json is the
# stable, hand-curated ticker → company-name list. The build copies it
# into docs/derived/ for static serving.
OWNER_TICKER_INITIAL: dict[str, list[str]] = {
    "BLTA": ["PT BERLIAN LAJU TANKER"],
    "BULL": ["PT BUANA LISTYA TAMA"],
    "SMDR": ["PT SAMUDERA INDONESIA"],
    "ELPI": ["PT PELITA SAMUDERA SHIPPING"],
    "SOCI": ["PT SOECHI LINES"],
    "GTSI": ["PT GTS INTERNASIONAL"],
    "HUMI": ["PT HUMPUSS MARITIM INTERNASIONAL"],
}

_PT_RE = re.compile(r"\bPT\.?\b", re.IGNORECASE)
_TBK_RE = re.compile(r"\b(TBK|PERSERO)\b", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[.,()/\\\-_]+")
_WS_RE = re.compile(r"\s+")


def _norm_company(s: str | None) -> str:
    """Match-friendly normalization: drops PT./Tbk/punct, collapses whitespace."""
    if not s:
        return ""
    s = s.upper()
    s = _PT_RE.sub(" ", s)
    s = _TBK_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> int:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    path.write_text(text, encoding="utf-8")
    return len(text)


# ----------------------------------------------------------------------
# 1. meta.json
# ----------------------------------------------------------------------
def build_meta() -> dict:
    src = _load_json(DATA / "meta.json")
    kpi = _load_json(DATA / "kpi_summary.json")

    series = kpi.get("monthly_series", [])
    partial = bool(kpi.get("latest_period_is_partial_data_dropped"))
    if partial and len(series) >= 2:
        latest_lk3 = series[-2]["period"]
    else:
        latest_lk3 = series[-1]["period"] if series else None

    return {
        "schema_version": 1,
        "build_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latest_lk3_month": latest_lk3,
        "latest_lk3_partial_dropped": partial,
        "latest_vessel_snapshot_month": src.get("latest"),
        "vessel_months": src.get("vessel_months", []),
        "cargo_months": src.get("cargo_months", []),
        "change_months": src.get("change_months", []),
        "data_sources": {
            "lk3": "monitoring-inaportnet.dephub.go.id",
            "vessel": "kapal.dephub.go.id",
            "financials": "IDX disclosure",
        },
    }


# ----------------------------------------------------------------------
# 2a. tanker fleet age stats (per subclass + overall)
#
# PR-C extension: scans vessels_snapshot for the latest snapshot, classifies
# each vessel via backend.taxonomy, and aggregates GT-weighted age + count
# per subclass. Output is merged into subclass_facts and exposed at the
# top level as `tanker_fleet_summary` for KPI cards.
# ----------------------------------------------------------------------
def build_tanker_age_stats(snapshot_month: str) -> tuple[dict, dict]:
    """Return ({subclass: stats}, overall_stats).

    Per-subclass stats:
      vessel_count, sum_gt, avg_age_gt_weighted, pct_age_25_plus
    Overall stats:
      vessel_count, sum_gt, avg_age_gt_weighted, foreign_pct (placeholder=null)
    """
    from backend.taxonomy import (
        CLS_TANKER,
        classify_tanker_subclass,
        classify_vessel_type,
    )

    current_year = datetime.now(timezone.utc).year

    per_sub: dict[str, dict] = defaultdict(lambda: {
        "vessel_count": 0,
        "sum_gt": 0.0,
        "sum_gt_age": 0.0,
        "count_age_25_plus": 0,
        "count_with_age": 0,
    })
    overall = {
        "vessel_count": 0,
        "sum_gt": 0.0,
        "sum_gt_age": 0.0,
        "count_with_age": 0,
    }

    with sqlite3.connect(DB) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT json_extract(raw_data, '$.JenisDetailKet') AS jenis_kapal,
                   json_extract(raw_data, '$.TahunPembuatan') AS tahun,
                   gt
              FROM vessels_snapshot
             WHERE snapshot_month = ?
            """,
            (snapshot_month,),
        )
        for jenis, tahun, gt in cur:
            if not jenis:
                continue
            _sector, vessel_class = classify_vessel_type(jenis)
            if vessel_class != CLS_TANKER:
                continue
            sub = classify_tanker_subclass(jenis) or "UNKNOWN"
            try:
                age = max(0, current_year - int(tahun))
            except (TypeError, ValueError):
                age = None
            try:
                gt_val = float(gt) if gt is not None else 0.0
            except (TypeError, ValueError):
                gt_val = 0.0

            d = per_sub[sub]
            d["vessel_count"] += 1
            d["sum_gt"] += gt_val
            if age is not None:
                d["sum_gt_age"] += gt_val * age
                d["count_with_age"] += 1
                if age >= 25:
                    d["count_age_25_plus"] += 1
            overall["vessel_count"] += 1
            overall["sum_gt"] += gt_val
            if age is not None:
                overall["sum_gt_age"] += gt_val * age
                overall["count_with_age"] += 1

    def _finalize_sub(d: dict) -> dict:
        avg_age = (d["sum_gt_age"] / d["sum_gt"]) if d["sum_gt"] > 0 else None
        pct_25_plus = (
            (d["count_age_25_plus"] / d["vessel_count"]) * 100
            if d["vessel_count"] else None
        )
        return {
            "vessel_count": d["vessel_count"],
            "sum_gt": round(d["sum_gt"], 1),
            "avg_age_gt_weighted": round(avg_age, 2) if avg_age is not None else None,
            "pct_age_25_plus": round(pct_25_plus, 2) if pct_25_plus is not None else None,
        }

    finalized = {sub: _finalize_sub(d) for sub, d in per_sub.items()}
    overall_avg = (
        (overall["sum_gt_age"] / overall["sum_gt"]) if overall["sum_gt"] > 0 else None
    )
    overall_out = {
        "vessel_count": overall["vessel_count"],
        "sum_gt": round(overall["sum_gt"], 1),
        "avg_age_gt_weighted": round(overall_avg, 2) if overall_avg is not None else None,
    }
    return finalized, overall_out


# ----------------------------------------------------------------------
# 2. subclass_facts.json
# ----------------------------------------------------------------------
def build_subclass_facts() -> dict:
    """Per-subclass 24M facts: CAGR, calls, operator count, HHI, fleet age."""
    tf = _load_json(DATA / "tanker_focus.json")
    kpi = _load_json(DATA / "kpi_summary.json")
    by_sub = {row["subclass"]: row for row in tf["by_subclass"]}
    monthly = tf["monthly_subclass"]
    age_stats, fleet_summary = build_tanker_age_stats(tf["snapshot_month"])

    period_sub_ton: dict[tuple[str, str], float] = defaultdict(float)
    period_sub_calls: dict[tuple[str, str], int] = defaultdict(int)
    periods: set[str] = set()
    for r in monthly:
        key = (r["period"], r["subclass"])
        period_sub_ton[key] += float(r.get("ton_total") or 0.0)
        period_sub_calls[key] += int(r.get("calls") or 0)
        periods.add(r["period"])

    sorted_periods = sorted(periods)
    if kpi.get("latest_period_is_partial_data_dropped") and sorted_periods:
        sorted_periods = sorted_periods[:-1]
    last12 = sorted_periods[-12:]
    prev12 = sorted_periods[-24:-12]

    # CAGR is only meaningful when both windows are equal-length 12-month
    # blocks. On a partial 23-month series, prev12 has only 11 entries — we
    # mark cagr null with a note so the frontend can render "Insufficient data".
    cagr_eligible = len(last12) == 12 and len(prev12) == 12

    rows = []
    for sub, summary in by_sub.items():
        ton_last = sum(period_sub_ton.get((p, sub), 0.0) for p in last12)
        ton_prev = sum(period_sub_ton.get((p, sub), 0.0) for p in prev12)
        if cagr_eligible and ton_prev > 0:
            cagr = (ton_last / ton_prev) ** 0.5 - 1
        else:
            cagr = None
        calls_last = sum(period_sub_calls.get((p, sub), 0) for p in last12)

        # HHI from owner subclass-counts (top-50 truncation = small bias).
        owner_counts = []
        for fo in tf["fleet_owners"]:
            cnt = (fo.get("subclass_counts") or {}).get(sub, 0)
            if cnt > 0:
                owner_counts.append(cnt)
        total = sum(owner_counts)
        if total > 0:
            shares = [c / total for c in owner_counts]
            hhi = sum(s * s for s in shares) * 10000
            op_count = len(owner_counts)
        else:
            hhi = None
            op_count = 0

        age = age_stats.get(sub, {})
        rows.append({
            "subclass": sub,
            "ton_last_12m": round(ton_last, 1),
            "ton_prev_12m": round(ton_prev, 1),
            "cagr_24m_pct": round(cagr * 100, 2) if cagr is not None else None,
            "calls_last_12m": calls_last,
            "ton_24m": summary.get("ton_total"),
            "calls_24m": summary.get("calls_total"),
            "avg_ton_per_call": summary.get("avg_ton_per_call"),
            "operator_count": op_count,
            "hhi": round(hhi, 1) if hhi is not None else None,
            "vessel_count": age.get("vessel_count"),
            "sum_gt": age.get("sum_gt"),
            "avg_age_gt_weighted": age.get("avg_age_gt_weighted"),
            "pct_age_25_plus": age.get("pct_age_25_plus"),
        })
    rows.sort(key=lambda r: r.get("ton_24m") or 0, reverse=True)
    return {
        "schema_version": 1,
        "snapshot_month": tf["snapshot_month"],
        "window_months": {"last_12m": last12, "prev_12m": prev12},
        "tanker_fleet_summary": fleet_summary,
        "subclasses": rows,
        "_notes": {
            "cagr_basis": (
                "annualized: (ton_last_12m / ton_prev_12m) ^ 0.5 - 1; "
                f"set to null unless both windows are exactly 12 months "
                f"(this build: last={len(last12)}M, prev={len(prev12)}M)"
            ),
            "hhi_basis": "Σ(share^2)*10000 over fleet_owners.subclass_counts (top-50 owner truncation)",
            "operator_count_caveat": "limited to fleet_owners list (top-50 by sum_gt)",
        },
    }


# ----------------------------------------------------------------------
# 3. route_facts.json
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# Renewal v2: cargo_fleet.json (PR-4) — treemap + commodity bars + class donut + age bars
# ----------------------------------------------------------------------
def build_fleet_vessels(snapshot_month: str) -> dict:
    """Full per-vessel registry export for the Fleet tab's filter-list view.

    Includes **all sectors** (cargo + passenger + fishing + offshore +
    non-commercial) so the frontend filter can offer "전체" / "나머지 전부"
    selections. Each row uses a compact array format keyed off the
    `cols` schema.

    Columns (positional):
      nama        — vessel name
      owner       — NamaPemilik (truncated)
      sector      — taxonomy sector (CARGO / PASSENGER / FISHING / OFFSHORE_SUPPORT / NON_COMMERCIAL / UNMAPPED)
      vc          — vessel class (11 classes — see _VC_LABELS below)
      ts          — tanker subclass (Tanker only, else "")
      gt          — gross tonnage (number)
      loa         — length overall (m)
      tahun       — build year (int|null)
      age         — current year − tahun
      flag        — bendera asal ("" ≈ Indonesia)
      imo         — IMO (string, may be empty)
      call_sign   — call sign

    Source: kapal.dephub.go.id/ditkapel_service/data_kapal/ (vessels_snapshot).
    """
    from backend.taxonomy import (
        CLS_BULK, CLS_CONTAINER, CLS_DREDGER_SPECIAL, CLS_FERRY, CLS_FISHING,
        CLS_GENERAL, CLS_NONCOMM, CLS_OTHER_CARGO, CLS_PASSENGER_SHIP,
        CLS_TANKER, CLS_TUG_OSV, CLS_UNMAPPED,
        classify_tanker_subclass, classify_vessel_type,
    )
    # Visual-class labels — keeps stable display names independent of the
    # underlying taxonomy constants, so future renames don't break the UI.
    visual_map = {
        CLS_CONTAINER:       "Container",
        CLS_BULK:            "Bulk Carrier",
        CLS_TANKER:          "Tanker",
        CLS_GENERAL:         "General Cargo",
        CLS_OTHER_CARGO:     "Other Cargo",
        CLS_PASSENGER_SHIP:  "Passenger Ship",
        CLS_FERRY:           "Ferry",
        CLS_FISHING:         "Fishing Vessel",
        CLS_TUG_OSV:         "Tug/OSV/AHTS",
        CLS_DREDGER_SPECIAL: "Dredger/Special",
        CLS_NONCOMM:         "Government/Navy/Other",
        CLS_UNMAPPED:        "UNMAPPED",
    }

    cur_year = datetime.now(timezone.utc).year
    rows: list[list] = []
    with sqlite3.connect(DB) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT
              nama_kapal,
              json_extract(raw_data, '$.NamaPemilik')      AS pemilik,
              json_extract(raw_data, '$.JenisDetailKet')   AS jenis,
              gt,
              json_extract(raw_data, '$.LengthOfAll')      AS loa,
              panjang,
              json_extract(raw_data, '$.TahunPembuatan')   AS tahun,
              json_extract(raw_data, '$.BenderaAsal')      AS bendera,
              imo,
              call_sign
            FROM vessels_snapshot
            WHERE snapshot_month = ?
              AND raw_data IS NOT NULL
            """,
            (snapshot_month,),
        )
        for (nama, pemilik, jenis, gt, loa, panjang,
             tahun, bendera, imo, call_sign) in cur:
            if not jenis:
                continue
            sector, vclass = classify_vessel_type(jenis)
            # Keep ALL sectors — the frontend filter handles narrowing
            vc = visual_map.get(vclass, "UNMAPPED")
            ts = classify_tanker_subclass(jenis) if vclass == CLS_TANKER else ""
            try:
                gt_v = round(float(gt), 1) if gt is not None else 0.0
            except (TypeError, ValueError):
                gt_v = 0.0
            try:
                loa_v = float(loa) if loa is not None else None
                if not loa_v or loa_v <= 0:
                    loa_v = float(panjang) if panjang is not None else 0.0
                loa_v = round(loa_v, 1)
            except (TypeError, ValueError):
                loa_v = 0.0
            try:
                tahun_v = int(tahun) if tahun is not None else None
                if tahun_v and (tahun_v < 1900 or tahun_v > 2100):
                    tahun_v = None
            except (TypeError, ValueError):
                tahun_v = None
            age_v = (cur_year - tahun_v) if tahun_v is not None else None
            flag_v = "" if not bendera or str(bendera).strip() == "Indonesia" \
                       else str(bendera).strip()
            owner_v = (str(pemilik).strip() if pemilik else "(미상)")[:60]
            rows.append([
                (nama or "").strip(),
                owner_v,
                sector,
                vc,
                (jenis or "").strip(),         # PR — raw JenisDetailKet (no taxonomy grouping)
                ts or "",
                gt_v,
                loa_v,
                tahun_v,
                age_v,
                flag_v,
                (imo or "").strip(),
                (call_sign or "").strip(),
            ])

    # Pre-compute headline totals so the frontend doesn't need to scan rows
    # before drawing the KPI strip. by_jenis is keyed on raw JenisDetailKet
    # so the new searchable filter can show count + sector tag per type.
    from collections import Counter as _Counter, defaultdict as _dd
    sector_totals = _Counter(r[2] for r in rows)
    vc_totals = _Counter(r[3] for r in rows)
    jenis_agg: dict[str, dict] = {}
    for r in rows:
        jn = r[4] or "(blank)"
        d = jenis_agg.setdefault(jn, {"count": 0, "sector": r[2], "vc": r[3]})
        d["count"] += 1

    return {
        "schema_version": 3,                # PR — added raw `jenis` column
        "snapshot_month": snapshot_month,
        "source": "kapal.dephub.go.id/ditkapel_service/data_kapal/",
        "current_year": cur_year,
        "cols": ["nama", "owner", "sector", "vc", "jenis", "ts", "gt", "loa",
                  "tahun", "age", "flag", "imo", "call_sign"],
        "rows": rows,
        "totals": {
            "all_vessels": len(rows),
            "by_sector": dict(sector_totals),
            "by_class":  dict(vc_totals),
            "by_jenis":  jenis_agg,
        },
        "_notes": {
            "scope": "ALL sectors — CARGO + PASSENGER + FISHING + "
                     "OFFSHORE_SUPPORT + NON_COMMERCIAL + UNMAPPED",
            "flag_default": "empty string == Indonesia (>99% of fleet)",
            "row_count": len(rows),
            "jenis_distinct": len(jenis_agg),
        },
    }


def build_fleet_owners(snapshot_month: str, top_n: int = 25) -> dict:
    """Top owners across the FULL cargo fleet (not just tankers).

    Sourced directly from `vessels_snapshot` (kapal.dephub.go.id vessel
    registry). For each Indonesian-flagged vessel:

      1. Classify the JenisDetailKet label via backend.taxonomy.
      2. Keep only the CARGO sector (drops fishing/passenger/non-comm).
      3. Bucket each into one of 5 vessel classes (Container / Bulk /
         Tanker / General Cargo / Other Cargo).
      4. Aggregate by `NamaPemilik` -> total count + GT + per-class mix.

    Returns the top N owners ranked by total vessel count. Differs from
    `owner_profile.json` (tanker-only, LK3-cross-referenced) — this one
    is a pure registry view.
    """
    from backend.taxonomy import (
        CLS_BULK, CLS_CONTAINER, CLS_GENERAL, CLS_OTHER_CARGO, CLS_TANKER,
        SECTOR_CARGO, classify_tanker_subclass, classify_vessel_type,
    )
    visual_map = {
        CLS_CONTAINER: "Container",
        CLS_BULK:      "Bulk Carrier",
        CLS_TANKER:    "Tanker",
        CLS_GENERAL:   "General Cargo",
        CLS_OTHER_CARGO: "Other Cargo",
    }

    owners: dict[str, dict] = {}
    total_vessels = 0
    total_gt = 0.0
    class_totals: dict[str, int] = defaultdict(int)

    with sqlite3.connect(DB) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT
              json_extract(raw_data, '$.NamaPemilik')      AS pemilik,
              json_extract(raw_data, '$.JenisDetailKet')   AS jenis,
              gt,
              json_extract(raw_data, '$.TahunPembuatan')   AS tahun,
              json_extract(raw_data, '$.BenderaAsal')      AS bendera
            FROM vessels_snapshot
            WHERE snapshot_month = ?
              AND raw_data IS NOT NULL
            """,
            (snapshot_month,),
        )
        for pemilik, jenis, gt, tahun, bendera in cur:
            if not jenis:
                continue
            sector, vclass = classify_vessel_type(jenis)
            if sector != SECTOR_CARGO:
                continue                                    # cargo only
            class_label = visual_map.get(vclass, "Other Cargo")
            try:
                gt_val = float(gt) if gt is not None else 0.0
            except (TypeError, ValueError):
                gt_val = 0.0
            try:
                tahun_val = int(tahun) if tahun is not None else None
            except (TypeError, ValueError):
                tahun_val = None

            total_vessels += 1
            total_gt += gt_val
            class_totals[class_label] += 1

            owner_key = (pemilik or "(미상)").strip() or "(미상)"
            d = owners.setdefault(owner_key, {
                "owner": owner_key,
                "vessels": 0,
                "sum_gt": 0.0,
                "class_mix": defaultdict(int),
                "tanker_subclass_mix": defaultdict(int),
                "_sum_age_gt": 0.0,
                "_sum_age_w": 0.0,
                "_flag_counts": defaultdict(int),
            })
            d["vessels"] += 1
            d["sum_gt"] += gt_val
            d["class_mix"][class_label] += 1
            if vclass == CLS_TANKER:
                sub = classify_tanker_subclass(jenis) or "UNKNOWN"
                d["tanker_subclass_mix"][sub] += 1
            if tahun_val and 1900 < tahun_val < 2100:
                age = max(0, datetime.now(timezone.utc).year - tahun_val)
                d["_sum_age_gt"] += age * gt_val
                d["_sum_age_w"] += gt_val
            if bendera:
                d["_flag_counts"][str(bendera).strip()] += 1

    # Finalize: GT-weighted average age + top flag, drop temp keys
    finalized = []
    for d in owners.values():
        avg_age = (d["_sum_age_gt"] / d["_sum_age_w"]) if d["_sum_age_w"] > 0 else None
        top_flag = None
        if d["_flag_counts"]:
            top_flag = sorted(d["_flag_counts"].items(),
                               key=lambda kv: -kv[1])[0][0]
        finalized.append({
            "owner": d["owner"],
            "vessels": d["vessels"],
            "sum_gt": round(d["sum_gt"], 1),
            "avg_age_gt_weighted": round(avg_age, 1) if avg_age is not None else None,
            "top_flag": top_flag,
            "class_mix": dict(d["class_mix"]),
            "tanker_subclass_mix": dict(d["tanker_subclass_mix"]),
        })
    finalized.sort(key=lambda o: (-o["vessels"], -o["sum_gt"]))

    return {
        "schema_version": 1,
        "snapshot_month": snapshot_month,
        "source": "kapal.dephub.go.id/ditkapel_service/data_kapal/ (vessels_snapshot)",
        "totals": {
            "cargo_vessels": total_vessels,
            "total_gt": round(total_gt, 1),
            "unique_owners": len(finalized),
            "class_totals": dict(class_totals),
        },
        "owners": finalized[:top_n],
        "_notes": {
            "scope": "CARGO sector only via backend.taxonomy "
                     "(excludes fishing / passenger / offshore-support / non-commercial)",
            "ranking": "by vessel count then sum_gt; ties broken by name",
            "age_basis": "GT-weighted average — fleets weighted by capacity",
        },
    }


def build_fleet_class_counts(snapshot_month: str) -> dict:
    """Group vessels_snapshot.raw_data into 5 visual classes.

    Per spec section 6.3: Container · Bulk · Tanker · General · Other.
    Mapping uses backend.taxonomy.classify_vessel_type to fold the rich
    Indonesian/English vessel-type labels.
    """
    from backend.taxonomy import (
        CLS_BULK, CLS_CONTAINER, CLS_GENERAL, CLS_OTHER_CARGO, CLS_TANKER,
        classify_vessel_type,
    )
    visual_map = {
        CLS_CONTAINER: "Container",
        CLS_BULK:      "Bulk Carrier",
        CLS_TANKER:    "Tanker",
        CLS_GENERAL:   "General Cargo",
        CLS_OTHER_CARGO: "Other Cargo",
    }
    counts: dict[str, int] = defaultdict(int)
    with sqlite3.connect(DB) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT json_extract(raw_data, '$.JenisDetailKet') AS jenis,
                   COUNT(*) AS n
              FROM vessels_snapshot
             WHERE snapshot_month = ?
               AND raw_data IS NOT NULL
             GROUP BY jenis
            """,
            (snapshot_month,),
        )
        for jenis, n in cur:
            if not jenis:
                counts["Other"] += n
                continue
            _sec, vc = classify_vessel_type(jenis)
            label = visual_map.get(vc, "Other")
            counts[label] += n
    # Stable order matching spec
    order = ["Container", "Bulk Carrier", "Tanker", "General Cargo", "Other Cargo", "Other"]
    return [{"class": k, "count": counts.get(k, 0)} for k in order if counts.get(k, 0) > 0]


def build_fleet_age_bins(snapshot_month: str, current_year: int | None = None) -> dict:
    """5-year bins of vessel age, with 25+ flagged for color emphasis.

    Reads vessels_snapshot.raw_data.TahunPembuatan; falls back to skip
    rows with bad/missing build year.
    """
    if current_year is None:
        current_year = datetime.now(timezone.utc).year
    bins_def = [
        ("0-4 yr",    0,   4,  False),
        ("5-9 yr",    5,   9,  False),
        ("10-14 yr",  10,  14, False),
        ("15-19 yr",  15,  19, False),
        ("20-24 yr",  20,  24, False),
        ("25-29 yr",  25,  29, True),
        ("30-34 yr",  30,  34, True),
        ("35+ yr",    35,  999, True),
    ]
    counts = [0] * len(bins_def)
    with sqlite3.connect(DB) as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT json_extract(raw_data, '$.TahunPembuatan')
              FROM vessels_snapshot
             WHERE snapshot_month = ?
               AND raw_data IS NOT NULL
            """,
            (snapshot_month,),
        )
        for (tahun,) in cur:
            try:
                age = current_year - int(tahun)
                if age < 0 or age > 200:
                    continue
            except (TypeError, ValueError):
                continue
            for i, (_label, lo, hi, _flag) in enumerate(bins_def):
                if lo <= age <= hi:
                    counts[i] += 1
                    break
    return {
        "bins": [{"label": l, "count": c, "older": flag}
                 for c, (l, _lo, _hi, flag) in zip(counts, bins_def)],
        "current_year": current_year,
    }


def build_cargo_yearly() -> dict:
    """Per calendar-year cargo cuts (treemap + commodities), for the Cargo tab.

    Replaces the "rolling 24M" framing with explicit (2024 / 2025 / 2026)
    buckets. Queries `cargo_snapshot` directly via JSON-extract on the
    BONGKAR/MUAT/KOMODITI/JENIS keys (Indonesian tuple-stringified MultiIndex).

    Partial years (12개월 미만) are flagged via `months_per_year` so the
    client can render a hatched pattern on those bars and avoid spurious
    YoY comparisons.

    Returned shape:
        {
          schema_version, snapshot_month,
          years: [str, ...],
          months_per_year: {year: int_month_count},
          by_year: {
              year: {
                  total_ton: float,
                  treemap_categories: [{category, ton_total, calls}, ...],
                  top_commodities:    [{name,     ton_total}, ...],
              }
          }
        }
    """
    src_meta = _load_json(DATA / "meta.json")
    snap = src_meta.get("latest")

    # Embed-safe JSON path encoder for keys like ('BONGKAR', 'TON')
    def _path(key: str) -> str:
        return ('$."' + key + '"').replace("'", "''")

    P_J_B = _path("('BONGKAR', 'JENIS')")
    P_T_B = _path("('BONGKAR', 'TON')")
    P_K_B = _path("('BONGKAR', 'KOMODITI')")
    P_J_M = _path("('MUAT', 'JENIS')")
    P_T_M = _path("('MUAT', 'TON')")
    P_K_M = _path("('MUAT', 'KOMODITI')")
    P_ORIG = _path("('TIBA', 'DARI')")
    P_DEST = _path("('BERANGKAT', 'KE')")
    ton = lambda p: f"COALESCE(CAST(NULLIF(json_extract(raw_row, '{p}'), '-') AS REAL), 0)"

    # ---- Port-coord lookup from previously-built map_flow.json --------------
    # We re-use the 60 normalized ports + lat/lon already produced by the
    # tanker_flow_map pipeline. Anything we cannot resolve simply drops out of
    # the map (kept in the table view via the raw origin/destination strings).
    try:
        from backend.build_static import _flow_normalize_port  # type: ignore
    except Exception:
        # Fallback: trivial normalizer if build_static can't be imported.
        def _flow_normalize_port(s):
            if not s:
                return None
            t = str(s).upper().strip()
            t = t.split("(", 1)[0].split("/", 1)[0].split(",", 1)[0].strip()
            return t if len(t) >= 3 else None

    port_coords: dict[str, tuple[float, float]] = {}
    try:
        mf = _load_json(DERIVED / "map_flow.json")
        for p in mf.get("ports", []):
            nm = p.get("name")
            if nm and p.get("lat") is not None and p.get("lon") is not None:
                port_coords[nm.upper()] = (float(p["lat"]), float(p["lon"]))
    except FileNotFoundError:
        pass

    # PR-37: supplement the tanker-focused map_flow.ports list with dry-bulk,
    # nickel, and palm hubs that dominate non-tanker OD flow. Without these
    # the year-cut OD map drops many top routes (e.g. SAMARINDA, MOLAWE,
    # KUALA TANJUNG), skewing the category mix toward Product/BBM.
    # Coordinates picked from public geographic sources, accurate to ~1km
    # which is plenty for an archipelago-scale map. Don't add entries
    # already present in map_flow.json (would just be overwritten with the
    # same value).
    _EXTRA_PORT_COORDS: dict[str, tuple[float, float]] = {
        # ----- Kalimantan coal export hubs -----
        "SAMARINDA":       (-0.50,  117.15),   # E. Kalimantan
        "BANJARMASIN":     (-3.32,  114.59),   # S. Kalimantan
        "TANJUNG BARA":    (-0.42,  117.55),   # KPC coal terminal
        "KOTABARU":        (-3.30,  116.20),   # S. Kalimantan
        "BONTANG":         ( 0.13,  117.49),   # E. Kalimantan LNG + coal
        "MUARA SATUI":     (-3.85,  115.50),
        "TANAH GROGOT":    (-1.91,  116.20),
        "BATULICIN":       (-3.30,  116.20),
        "TARJUN":          (-3.65,  116.04),
        "SANGATTA":        ( 0.38,  117.55),
        # ----- Sulawesi nickel hubs -----
        "WEDA":            ( 0.36,  127.93),   # Halmahera (technically Maluku Utara)
        "MOLAWE":          (-3.96,  121.95),   # Konawe nickel
        "POMALAA":         (-4.18,  121.62),
        "MOROWALI":        (-2.85,  121.85),
        "OBI ISLAND":      (-1.42,  127.85),   # N. Maluku nickel
        "OBI":             (-1.42,  127.85),
        "KENDARI":         (-3.97,  122.52),
        "KOLAKA":          (-4.04,  121.60),
        "KONAWE":          (-3.96,  122.60),
        # ----- Sumatra palm + nickel + coal export -----
        "KUALA TANJUNG":   ( 3.40,   99.45),   # N. Sumatra deepsea
        "LUBUK GAUNG":     ( 1.65,  101.40),   # Riau palm
        "SUNGAI PAKNING":  ( 1.39,  102.13),
        # ----- Java + general additions -----
        "TANJUNG PERAK":   (-7.20,  112.74),   # Surabaya (alias)
        "PROBOLINGGO":     (-7.74,  113.21),
        "PASURUAN":        (-7.65,  112.91),
        "CILACAP":         (-7.73,  109.02),
        # ----- Papua / Maluku -----
        "TANGGUH":         (-2.13,  133.51),   # W. Papua LNG
        "AMAMAPARE":       (-4.83,  136.88),   # Freeport Indonesia (copper)
        "TIMIKA":          (-4.55,  136.89),
        "MERAUKE":         (-8.49,  140.39),
        # ----- Sumbawa nickel / mining -----
        "BENETE":          (-9.00,  116.83),   # Newmont (Sumbawa)
        "MEKAR PUTIH":     (-8.59,  116.43),
    }
    for name, (lat, lon) in _EXTRA_PORT_COORDS.items():
        port_coords.setdefault(name, (lat, lon))

    with sqlite3.connect(DB) as con:
        cur = con.cursor()

        # Year scaffolding (years + months covered per year)
        cur.execute(
            "SELECT data_year, COUNT(DISTINCT data_month) "
            "FROM cargo_snapshot WHERE snapshot_month=? "
            "GROUP BY data_year ORDER BY 1",
            (snap,),
        )
        years_meta = [(str(int(y)), int(n)) for y, n in cur if y is not None]

        by_year: dict[str, dict] = {}

        for y, _mc in years_meta:
            yr_int = int(y)

            # Total ton (BONGKAR + MUAT)
            cur.execute(
                f"SELECT SUM({ton(P_T_B)}) + SUM({ton(P_T_M)}) "
                f"FROM cargo_snapshot WHERE snapshot_month=? AND data_year=?",
                (snap, yr_int),
            )
            row = cur.fetchone()
            total = float((row[0] if row and row[0] is not None else 0.0))

            # Treemap categories (jenis) — combine BONGKAR + MUAT, top 15
            cur.execute(
                f"SELECT j, SUM(t) AS ton, COUNT(*) AS calls FROM ("
                f"  SELECT json_extract(raw_row, '{P_J_B}') AS j, {ton(P_T_B)} AS t "
                f"  FROM cargo_snapshot WHERE snapshot_month=? AND data_year=? "
                f"  UNION ALL "
                f"  SELECT json_extract(raw_row, '{P_J_M}') AS j, {ton(P_T_M)} AS t "
                f"  FROM cargo_snapshot WHERE snapshot_month=? AND data_year=? "
                f") WHERE j IS NOT NULL AND j != '' AND j != '-' AND t > 0 "
                f"GROUP BY j ORDER BY ton DESC LIMIT 15",
                (snap, yr_int, snap, yr_int),
            )
            treemap_rows = [
                {"category": j, "ton_total": round(float(t), 1), "calls": int(c)}
                for j, t, c in cur
            ]

            # Top commodities (komoditi) — combine BONGKAR + MUAT, top 10
            cur.execute(
                f"SELECT k, SUM(t) AS ton FROM ("
                f"  SELECT json_extract(raw_row, '{P_K_B}') AS k, {ton(P_T_B)} AS t "
                f"  FROM cargo_snapshot WHERE snapshot_month=? AND data_year=? "
                f"  UNION ALL "
                f"  SELECT json_extract(raw_row, '{P_K_M}') AS k, {ton(P_T_M)} AS t "
                f"  FROM cargo_snapshot WHERE snapshot_month=? AND data_year=? "
                f") WHERE k IS NOT NULL AND k != '' AND k != '-' AND t > 0 "
                f"GROUP BY k ORDER BY ton DESC LIMIT 10",
                (snap, yr_int, snap, yr_int),
            )
            commodity_rows = [
                {"name": k, "ton_total": round(float(t), 1)}
                for k, t in cur
            ]

            # Per-(origin, destination) ton + calls for this year. The raw
            # strings are kept; coord lookup happens after normalization.
            cur.execute(
                f"SELECT json_extract(raw_row, '{P_ORIG}') AS o, "
                f"       json_extract(raw_row, '{P_DEST}') AS d, "
                f"       SUM({ton(P_T_B)} + {ton(P_T_M)}) AS t, "
                f"       COUNT(*) AS c "
                f"FROM cargo_snapshot "
                f"WHERE snapshot_month=? AND data_year=? "
                f"AND o IS NOT NULL AND o != '' AND o != '-' "
                f"AND d IS NOT NULL AND d != '' AND d != '-' "
                f"GROUP BY o, d HAVING t > 0",
                (snap, yr_int),
            )
            od_rows_raw = cur.fetchall()

            # PR-36: per-(o, d, komoditi) ton so we can attach a dominant
            # category to each year-cut route. The Home map's year-mode then
            # regains color parity with 24M mode.
            cur.execute(
                f"SELECT o, d, kom, SUM(t) AS s FROM ( "
                f"  SELECT json_extract(raw_row, '{P_ORIG}') AS o, "
                f"         json_extract(raw_row, '{P_DEST}') AS d, "
                f"         json_extract(raw_row, '{P_K_B}') AS kom, "
                f"         {ton(P_T_B)} AS t "
                f"  FROM cargo_snapshot WHERE snapshot_month=? AND data_year=? "
                f"  UNION ALL "
                f"  SELECT json_extract(raw_row, '{P_ORIG}') AS o, "
                f"         json_extract(raw_row, '{P_DEST}') AS d, "
                f"         json_extract(raw_row, '{P_K_M}') AS kom, "
                f"         {ton(P_T_M)} AS t "
                f"  FROM cargo_snapshot WHERE snapshot_month=? AND data_year=? "
                f") WHERE o IS NOT NULL AND o != '' AND o != '-' "
                f"  AND d IS NOT NULL AND d != '' AND d != '-' "
                f"  AND kom IS NOT NULL AND kom != '' AND kom != '-' "
                f"  AND t > 0 "
                f"GROUP BY o, d, kom",
                (snap, yr_int, snap, yr_int),
            )
            od_kom_raw = cur.fetchall()

            # Normalize, look up coords, split into top routes vs STS hubs.
            od_agg: dict = {}
            sts_agg: dict = {}
            for o, d, t, c in od_rows_raw:
                on = _flow_normalize_port(o)
                dn = _flow_normalize_port(d)
                if not on or not dn:
                    continue
                t = float(t or 0); c = int(c)
                if on == dn:
                    if on not in sts_agg:
                        sts_agg[on] = [0.0, 0]
                    sts_agg[on][0] += t
                    sts_agg[on][1] += c
                else:
                    key = (on, dn)
                    if key not in od_agg:
                        od_agg[key] = [0.0, 0]
                    od_agg[key][0] += t
                    od_agg[key][1] += c

            # PR-36: fold (o, d, kom) into normalized (on, dn) -> category_ton
            # so each route can be tagged with its dominant commodity category.
            try:
                from backend.build_static import _flow_classify_kom  # type: ignore
            except Exception:
                def _flow_classify_kom(label):
                    if not label:
                        return "기타"
                    s = str(label).upper()
                    if "CRUDE" in s or "MENTAH" in s:
                        return "Crude"
                    if "CPO" in s or "PALM OIL" in s or "MINYAK SAWIT" in s:
                        return "CPO/팜오일"
                    if "LNG" in s or "NATURAL GAS" in s:
                        return "LNG"
                    if "LPG" in s or "ELPIJI" in s:
                        return "LPG"
                    return "기타"

            od_cat: dict[tuple[str, str], dict[str, float]] = {}
            for o, d, kom, t in od_kom_raw:
                on = _flow_normalize_port(o)
                dn = _flow_normalize_port(d)
                if not on or not dn:
                    continue
                bucket = _flow_classify_kom(kom)
                category = _bucket_to_category(bucket)
                if not category:
                    continue
                key = (on, dn)
                if key not in od_cat:
                    od_cat[key] = {}
                od_cat[key][category] = od_cat[key].get(category, 0.0) + float(t or 0)

            # Top 30 OD routes (mappable preferred — keep all then sort)
            route_rows = []
            for (on, dn), (tv, cv) in sorted(
                od_agg.items(), key=lambda kv: -kv[1][0])[:120]:
                op = port_coords.get(on)
                dp = port_coords.get(dn)
                # PR-36: dominant commodity category for this OD pair
                cats = od_cat.get((on, dn), {})
                dominant = max(cats, key=cats.get) if cats else None
                category_ton = {c: round(t, 1) for c, t in cats.items()}
                route_rows.append({
                    "origin": on,
                    "destination": dn,
                    "lat_o": op[0] if op else None,
                    "lon_o": op[1] if op else None,
                    "lat_d": dp[0] if dp else None,
                    "lon_d": dp[1] if dp else None,
                    "ton": round(tv, 1),
                    "calls": cv,
                    "mappable": bool(op and dp),
                    "category": dominant,
                    "category_ton": category_ton,
                })
            # Prefer mappable routes for the headline Top 30; fall back to
            # non-mappable if mappable count is short.
            mappable_routes = [r for r in route_rows if r["mappable"]][:30]
            top_routes = mappable_routes if len(mappable_routes) >= 10 else route_rows[:30]

            top_sts = []
            for p, (tv, cv) in sorted(
                sts_agg.items(), key=lambda kv: -kv[1][0])[:15]:
                lp = port_coords.get(p)
                top_sts.append({
                    "port": p,
                    "lat": lp[0] if lp else None,
                    "lon": lp[1] if lp else None,
                    "ton": round(tv, 1),
                    "calls": cv,
                })

            by_year[y] = {
                "total_ton": round(total, 1),
                "treemap_categories": treemap_rows,
                "top_commodities": commodity_rows,
                "top_routes": top_routes,
                "top_sts": top_sts,
            }

    return {
        "schema_version": 2,                                          # PR-38
        "snapshot_month": snap,
        "years": [y for y, _ in years_meta],
        "months_per_year": {y: m for y, m in years_meta},
        # PR-38: full 8-category palette so the Home map legend can render
        # year-mode colors without falling back to map_flow's 5-category set.
        "categories": [
            {"name": name, "color": color}
            for (name, color, _sources) in MAP_CATEGORIES
        ],
        "by_year": by_year,
        "_notes": {
            "source": "cargo_snapshot — raw_row JSON via SQL json_extract",
            "scope": "BONGKAR + MUAT combined; SELF/foreign/coastal not separated here",
            "category_set": "PR-38 — 8 categories incl. Coal / Nickel-Mineral / Container",
        },
    }


def build_cargo_fleet() -> dict:
    """Renewal v2 PR-4: treemap + commodity bars + class donut + age bars."""
    cargo = _load_json(DATA / "cargo.json")
    src_meta = _load_json(DATA / "meta.json")
    snap = src_meta.get("latest")

    # 6.1 Treemap data — cargo categories (jenis) by 24M ton
    treemap_rows = []
    for j in (cargo.get("jenis_top") or [])[:15]:
        treemap_rows.append({
            "category": j["jenis"],
            "ton_total": round(j.get("ton_total") or 0, 1),
            "calls": (j.get("calls_dn") or 0) + (j.get("calls_ln") or 0),
        })

    # 6.2 Top 10 commodities (cross-sector, not just tanker)
    top_commodities = []
    for k in (cargo.get("komoditi_top") or [])[:10]:
        top_commodities.append({
            "name": k["komoditi"],
            "ton_total": round(k.get("ton_total") or 0, 1),
        })

    # 6.3 Class donut + 6.4 Age bars (one snapshot pass each)
    class_counts = build_fleet_class_counts(snap)
    age_bins = build_fleet_age_bins(snap)

    return {
        "schema_version": 1,
        "snapshot_month": snap,
        "treemap_categories": treemap_rows,
        "top_commodities": top_commodities,
        "class_counts": class_counts,
        "age_bins": age_bins,
    }


# ----------------------------------------------------------------------
# Renewal v2: home_kpi.json + timeseries.json + tanker_subclass.json + tanker_top.json
# ----------------------------------------------------------------------
SECTOR_PALETTE_5 = {
    "CARGO":           "#1A3A6B",   # navy (per spec §9.2)
    "PASSENGER":       "#0d9488",
    "OFFSHORE_SUPPORT":"#475569",
    "FISHING":         "#d97706",
    "NON_COMMERCIAL":  "#6b7280",
    "UNMAPPED":        "#dc2626",
}


def _sum_period(series, periods, key="ton") -> float:
    return sum((r.get(key) or 0.0) for r in series if r.get("period") in periods)


def build_home_kpi() -> dict:
    """Renewal v2: KPI 4 hero. Total / Tanker 12M ton + YoY, fleet count + age, freshness."""
    kpi = _load_json(DATA / "kpi_summary.json")
    tf = _load_json(DATA / "tanker_focus.json")
    src_meta = _load_json(DATA / "meta.json")

    # ---- Total Indonesia 12M ton + YoY (from kpi_summary.monthly_series) ----
    series = kpi.get("monthly_series", [])
    if kpi.get("latest_period_is_partial_data_dropped"):
        series_eff = series[:-1]
    else:
        series_eff = series[:]
    last12 = series_eff[-12:]
    prev12 = series_eff[-24:-12]
    total_last = sum((r.get("ton") or 0) for r in last12)
    total_prev = sum((r.get("ton") or 0) for r in prev12)
    total_yoy = ((total_last - total_prev) / total_prev * 100) if total_prev > 0 else None

    # ---- Tanker 12M ton + YoY (sum tanker_focus.monthly_subclass) ----
    monthly_sub = tf.get("monthly_subclass", [])
    period_ton = defaultdict(float)
    for r in monthly_sub:
        period_ton[r["period"]] += float(r.get("ton_total") or 0)
    sorted_periods = sorted(period_ton.keys())
    if kpi.get("latest_period_is_partial_data_dropped") and sorted_periods:
        sorted_periods = sorted_periods[:-1]
    tank_last12 = sum(period_ton[p] for p in sorted_periods[-12:])
    tank_prev12 = sum(period_ton[p] for p in sorted_periods[-24:-12])
    tank_yoy = ((tank_last12 - tank_prev12) / tank_prev12 * 100) if tank_prev12 > 0 else None

    # ---- PR-32: per-calendar-year cuts so KPI cards can display
    # "2025년 총 물동량" instead of rolling "12M 총 물동량".  Reuses the
    # already-loaded series/period_ton dicts — no extra DB query. ----
    def _by_year(items: list, key_period: str, key_ton: str) -> tuple[dict, dict]:
        """Group items by year[:4] -> (total_ton_by_year, months_per_year)."""
        ton_by_year: dict[str, float] = defaultdict(float)
        months_by_year: dict[str, set] = defaultdict(set)
        for r in items:
            p = r.get(key_period)
            if not p or len(str(p)) < 7:
                continue
            y = str(p)[:4]
            ton_by_year[y] += float(r.get(key_ton) or 0)
            months_by_year[y].add(str(p)[:7])
        return (
            {y: round(t, 1) for y, t in ton_by_year.items()},
            {y: len(s) for y, s in months_by_year.items()},
        )

    total_by_year, total_months = _by_year(series_eff, "period", "ton")
    tanker_period_items = [{"period": p, "ton": v} for p, v in period_ton.items()]
    if kpi.get("latest_period_is_partial_data_dropped") and sorted_periods:
        # Drop the last partial period from tanker as well
        partial_p = max(period_ton.keys())
        tanker_period_items = [r for r in tanker_period_items if r["period"] != partial_p]
    tanker_by_year, _ = _by_year(tanker_period_items, "period", "ton")

    def _yoy(by_year: dict[str, float]) -> dict[str, float | None]:
        """YoY % per year vs the previous year — null when either side missing."""
        sorted_ys = sorted(by_year.keys())
        out: dict[str, float | None] = {}
        for i, y in enumerate(sorted_ys):
            if i == 0:
                out[y] = None
                continue
            prev = by_year.get(sorted_ys[i - 1])
            cur = by_year[y]
            if prev and prev > 0:
                out[y] = round((cur - prev) / prev * 100, 1)
            else:
                out[y] = None
        return out

    total_yoy_by_year = _yoy(total_by_year)
    tanker_yoy_by_year = _yoy(tanker_by_year)

    # ---- Tanker fleet (count + GT-weighted avg age) ----
    age_stats, fleet_summary = build_tanker_age_stats(src_meta.get("latest"))

    # Vessel-registry counts (kapal.dephub.go.id). Returns total fleet
    # across ALL sectors plus the CARGO subset, so the Home KPI can read
    # "선박 등록 척수 N / 그중 화물선 M · 그중 탱커 K".
    cargo_fleet_count = 0
    all_fleet_count = 0
    try:
        from backend.taxonomy import SECTOR_CARGO, classify_vessel_type
        with sqlite3.connect(DB) as _con:
            _cur = _con.cursor()
            _cur.execute(
                "SELECT json_extract(raw_data, '$.JenisDetailKet') AS j, COUNT(*) "
                "FROM vessels_snapshot WHERE snapshot_month = ? "
                "GROUP BY j",
                (src_meta.get("latest"),),
            )
            for j, n in _cur:
                if not j:
                    all_fleet_count += int(n)
                    continue
                sector, _vc = classify_vessel_type(j)
                all_fleet_count += int(n)
                if sector == SECTOR_CARGO:
                    cargo_fleet_count += int(n)
    except Exception:
        pass

    # ---- PR-16: 5-sector breakdown for Home sidebar mini-bars ----
    top_sectors = kpi.get("top_sectors") or []
    sector_breakdown = [
        {
            "sector": s.get("sector"),
            "ton": round(s.get("ton") or 0, 1),
            "pct_ton": round(s.get("pct_ton") or 0, 2),
            "color": SECTOR_PALETTE_5.get(s.get("sector"), "#6b7280"),
        }
        for s in top_sectors
        if s.get("sector") not in ("UNMAPPED",)
    ]

    return {
        "schema_version": 1,
        "snapshot_month": src_meta.get("latest"),
        "sector_breakdown": sector_breakdown,
        "kpis": [
            {
                "id": "total_12m_ton",
                "label": "12M 총 물동량 (인도네시아)",
                "value_ton": round(total_last, 1),
                "yoy_pct": round(total_yoy, 1) if total_yoy is not None else None,
                "window": [last12[0]["period"] if last12 else None,
                           last12[-1]["period"] if last12 else None],
                "source": "monitoring-inaportnet.dephub.go.id (LK3)",
                # PR-32: per-calendar-year drill-down so the card label can
                # become "2025년 총 물동량" via the Home year selector.
                "by_year": total_by_year,
                "yoy_by_year": total_yoy_by_year,
                "months_per_year": total_months,
            },
            {
                "id": "tanker_12m_ton",
                "label": "12M 탱커 물동량",
                "value_ton": round(tank_last12, 1),
                "yoy_pct": round(tank_yoy, 1) if tank_yoy is not None else None,
                "window": [sorted_periods[-12] if len(sorted_periods) >= 12 else None,
                           sorted_periods[-1] if sorted_periods else None],
                "source": "monitoring-inaportnet.dephub.go.id (LK3, tanker rows)",
                "by_year": tanker_by_year,
                "yoy_by_year": tanker_yoy_by_year,
                "months_per_year": total_months,
            },
            {
                "id": "tanker_fleet",
                "label": "선박 등록 척수",         # PR — full registry (all sectors)
                "value_count": all_fleet_count,   # total registry count
                "cargo_count": cargo_fleet_count,
                "tanker_count": fleet_summary["vessel_count"],
                "avg_age_gt_weighted": fleet_summary["avg_age_gt_weighted"],
                "source": "kapal.dephub.go.id/ditkapel_service/data_kapal/ (vessel registry)",
            },
            {
                "id": "data_freshness",
                "label": "데이터 기준일",
                "value_text": kpi.get("latest_period") if kpi.get("latest_period") else src_meta.get("latest"),
                "vessel_snapshot": src_meta.get("latest"),
                "partial_dropped": bool(kpi.get("latest_period_is_partial_data_dropped")),
                "source": "docs/derived/meta.json",
            },
        ],
        "_notes": {
            "yoy_basis": "((sum(last12) - sum(prev12)) / sum(prev12)) * 100; null when prev12 missing",
        },
    }


def build_timeseries() -> dict:
    """Renewal v2: 24M sector stacked area for Home."""
    csm = _load_json(DATA / "cargo_sector_monthly.json")
    rows = csm.get("rows", [])
    # Aggregate by (period, sector) summing ton across kinds + vessel classes
    period_sector: dict[tuple[str, str], float] = defaultdict(float)
    sectors: set[str] = set()
    periods: set[str] = set()
    for r in rows:
        period_sector[(r["period"], r["sector"])] += float(r.get("ton_total") or 0)
        sectors.add(r["sector"])
        periods.add(r["period"])

    # Stable sector ordering: by total ton desc
    sector_total = defaultdict(float)
    for (_p, s), t in period_sector.items():
        sector_total[s] += t
    ordered_sectors = sorted(sector_total.keys(), key=lambda s: -sector_total[s])

    sorted_periods = sorted(periods)
    series = []
    for s in ordered_sectors:
        series.append({
            "sector": s,
            "color": SECTOR_PALETTE_5.get(s, "#6b7280"),
            "ton_by_period": [round(period_sector.get((p, s), 0.0), 1) for p in sorted_periods],
        })
    return {
        "schema_version": 1,
        "snapshot_month": csm.get("snapshot_month"),
        "periods": sorted_periods,
        "series": series,
        "_notes": {
            "scope": "24M monthly ton aggregated from cargo_sector_monthly.rows; "
                     "the latest period may be partial — kpi_summary's drop flag is honored downstream",
        },
    }


def _bucket_to_subclass(bucket: str | None) -> str | None:
    """Map a tanker_flow_map.lanes bucket label to a tanker subclass."""
    if not bucket:
        return None
    table = {
        "Crude":         "Crude Oil",
        "Naphtha":       "Product",
        "Kerosene":      "Product",
        "Chemical":      "Chemical",
        "LPG":           "LPG",
        "LNG":           "LNG",
        "FAME":          "FAME / Vegetable Oil",
        "기타 식용유":   "FAME / Vegetable Oil",
        "CPO/팜오일":    "FAME / Vegetable Oil",
    }
    if bucket in table:
        return table[bucket]
    if bucket.startswith("BBM"):
        return "Product"
    return None


def _top_route_per_subclass(lanes: list[dict]) -> dict[str, dict]:
    """Aggregate lanes -> top OD pair per subclass by ton."""
    agg: dict[tuple[str, str, str], dict] = defaultdict(
        lambda: {"ton": 0.0, "vessels": 0, "calls": 0}
    )
    for ln in lanes:
        sub = _bucket_to_subclass(ln.get("bucket"))
        if not sub:
            continue
        o, d = ln.get("o"), ln.get("d")
        if not o or not d or o == d:
            continue
        key = (sub, o, d)
        agg[key]["ton"] += float(ln.get("ton") or 0)
        agg[key]["vessels"] += int(ln.get("vessels") or 0)
        agg[key]["calls"] += int(ln.get("calls") or 0)
    out: dict[str, dict] = {}
    for (sub, o, d), v in agg.items():
        prev = out.get(sub)
        if not prev or v["ton"] > prev["ton"]:
            out[sub] = {"origin": o, "destination": d, **v}
    return out


def _top_operator_per_subclass(fleet_owners: list[dict]) -> dict[str, dict]:
    """Top operator per subclass by tanker_count for that subclass."""
    out: dict[str, dict] = {}
    for fo in fleet_owners:
        for sub, cnt in (fo.get("subclass_counts") or {}).items():
            if not cnt:
                continue
            prev = out.get(sub)
            if not prev or cnt > prev["count_in_subclass"]:
                out[sub] = {
                    "owner": fo["owner"],
                    "count_in_subclass": cnt,
                    "sum_gt": fo.get("sum_gt"),
                }
    return out


def build_tanker_subclass() -> dict:
    """Renewal v2: 6 subclass cards data + 24M monthly stacked area.

    PR-10 enrichment: top_route + top_operator per subclass.
    """
    tf = _load_json(DATA / "tanker_focus.json")
    sub_facts = _load_json(DERIVED / "subclass_facts.json")
    flow = _load_json(DATA / "tanker_flow_map.json")
    by_sub = {row["subclass"]: row for row in tf.get("by_subclass", [])}

    top_routes = _top_route_per_subclass(flow.get("lanes", []))
    top_operators = _top_operator_per_subclass(tf.get("fleet_owners", []))

    # ---- Card data per subclass (fact card §5.1) ----
    #
    # PR-33: also derive ton_by_year / yoy_by_year from the monthly_subclass
    # series so the Tanker Sector cards can render "2025년 ton" instead of
    # rolling 12M. The series is positionally aligned with `periods`, so
    # year folding is just a sum on period[:4].
    monthly_rows = tf.get("monthly_subclass", [])
    sub_year_ton: dict[tuple[str, str], float] = defaultdict(float)
    year_months: dict[str, set] = defaultdict(set)
    for r in monthly_rows:
        sub = r.get("subclass") or "UNKNOWN"
        if sub == "UNKNOWN":
            continue
        p = r.get("period") or ""
        if len(p) < 7:
            continue
        y = p[:4]
        sub_year_ton[(sub, y)] += float(r.get("ton_total") or 0)
        year_months[y].add(p[:7])
    months_per_year = {y: len(s) for y, s in year_months.items()}

    def _yoy_dict(sub: str) -> tuple[dict, dict]:
        years_sorted = sorted({y for (s, y) in sub_year_ton if s == sub})
        ton = {y: round(sub_year_ton[(sub, y)], 1) for y in years_sorted}
        yoy: dict[str, float | None] = {}
        for i, y in enumerate(years_sorted):
            if i == 0:
                yoy[y] = None
            else:
                prev = ton[years_sorted[i - 1]]
                yoy[y] = round((ton[y] - prev) / prev * 100, 1) if prev > 0 else None
        return ton, yoy

    cards = []
    for r in sub_facts.get("subclasses", []):
        sub = r["subclass"]
        if sub == "UNKNOWN":
            continue
        ton_last = r.get("ton_last_12m") or 0
        ton_prev = r.get("ton_prev_12m") or 0
        delta_pct = ((ton_last - ton_prev) / ton_prev * 100) if ton_prev > 0 else None
        ton_by_year, yoy_by_year = _yoy_dict(sub)
        cards.append({
            "subclass": sub,
            "ton_last_12m": ton_last,
            "yoy_pct": round(delta_pct, 1) if delta_pct is not None else None,
            "ton_by_year": ton_by_year,           # PR-33
            "yoy_by_year": yoy_by_year,           # PR-33
            "avg_age_gt_weighted": r.get("avg_age_gt_weighted"),
            "operator_count": r.get("operator_count"),
            "vessel_count": r.get("vessel_count"),
            "hhi": r.get("hhi"),
            "cagr_24m_pct": r.get("cagr_24m_pct"),
            "top_route": top_routes.get(sub),
            "top_operator": top_operators.get(sub),
        })
    cards.sort(key=lambda c: c.get("ton_last_12m") or 0, reverse=True)

    # ---- 24M monthly stacked: per (period, subclass) ton_total summed across kinds ----
    monthly = tf.get("monthly_subclass", [])
    periods_set: set[str] = set()
    subs_seen: set[str] = set()
    period_sub_ton: dict[tuple[str, str], float] = defaultdict(float)
    for r in monthly:
        if r["subclass"] == "UNKNOWN":
            continue
        period_sub_ton[(r["period"], r["subclass"])] += float(r.get("ton_total") or 0)
        periods_set.add(r["period"])
        subs_seen.add(r["subclass"])
    sorted_periods = sorted(periods_set)
    ordered_subs = [c["subclass"] for c in cards]   # stable card order
    series = [
        {
            "subclass": s,
            "ton_by_period": [round(period_sub_ton.get((p, s), 0.0), 1) for p in sorted_periods],
        }
        for s in ordered_subs
    ]

    return {
        "schema_version": 1,
        "snapshot_month": tf.get("snapshot_month"),
        "cards": cards,
        "monthly": {"periods": sorted_periods, "series": series},
        "months_per_year": months_per_year,  # PR-33: feeds the year selector
        "_notes": {
            "yoy_basis": "ton_by_year: calendar-year sums from monthly_subclass; "
                         "yoy_by_year: same-year vs previous-year (null if prev missing or zero); "
                         "ton_last_12m: legacy rolling 12M kept for backwards-compat",
            "top_route_per_subclass": "deferred — needs per-subclass OD aggregation",
        },
    }


def build_tanker_top() -> dict:
    """Renewal v2: Top 10 commodities + Top 15 operators with subclass mix + ticker."""
    tf = _load_json(DATA / "tanker_focus.json")
    tk_map = OWNER_TICKER_INITIAL
    rev = {}
    for ticker, names in tk_map.items():
        for n in names:
            rev[_norm_company(n)] = ticker

    kom = (tf.get("komoditi_top") or [])[:10]
    fleet_owners = (tf.get("fleet_owners") or [])
    fleet_owners_sorted = sorted(fleet_owners, key=lambda o: -(o.get("sum_gt") or 0))
    top_owners = []
    for o in fleet_owners_sorted[:15]:
        norm = _norm_company(o["owner"])
        ticker = rev.get(norm)
        top_owners.append({
            "owner": o["owner"],
            "ticker": ticker,
            "tankers": o["tanker_count"],
            "sum_gt": o["sum_gt"],
            "subclass_mix": o.get("subclass_counts", {}),
        })

    return {
        "schema_version": 1,
        "snapshot_month": tf.get("snapshot_month"),
        "top_commodities": [
            {
                "name": k["komoditi"],
                "subclass": k.get("subclass"),
                "ton_total": k.get("ton_total"),
                "calls": k.get("calls"),
            }
            for k in kom
        ],
        "top_operators": top_owners,
        "operator_total_gt": sum((o.get("sum_gt") or 0) for o in fleet_owners_sorted),
        "operator_top5_gt": sum((o.get("sum_gt") or 0) for o in fleet_owners_sorted[:5]),
    }


# ----------------------------------------------------------------------
# Renewal v2: map_flow.json — Home tab animated flow map data
# ----------------------------------------------------------------------
# Five visual categories rolled up from the granular bucket labels in
# tanker_flow_map.lanes. Order matters — color key is rendered top-down.
MAP_CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # (display name, hex color, bucket labels rolled into this category).
    # PR-38: split off Coal, Mineral Ore, Container/Gen Cargo into their own
    # top-level categories so the Home map colour-codes non-tanker bulk
    # routes distinctly. "기타" remains in Product/BBM as the last-resort
    # catch-all for unknown labels.
    ("Crude",                  "#92400e", ("Crude",)),
    ("Product / BBM",          "#0284c7", ("Naphtha", "Kerosene", "BBM-가솔린", "BBM-디젤", "BBM-항공유", "BBM-기타", "기타")),
    ("Chemical",               "#059669", ("Chemical",)),
    ("LPG / LNG",              "#7c3aed", ("LPG", "LNG")),
    ("FAME / Edible",          "#65a30d", ("FAME", "기타 식용유", "벙커유", "CPO/팜오일", "팜 파생", "아스팔트")),
    # PR-38: new bulk + container categories
    ("Coal",                   "#52525b", ("Coal",)),                                  # dark slate (coal-like)
    ("Nickel / Mineral Ore",   "#0e7490", ("Nickel", "Bauxite", "Iron Ore")),          # cyan (metal ore)
    ("Container / Gen Cargo",  "#9333ea", ("Container", "General Cargo", "Cement")),   # violet
)


def _bucket_to_category(bucket: str | None) -> str | None:
    if not bucket:
        return None
    for name, _, sources in MAP_CATEGORIES:
        if bucket in sources:
            return name
    if bucket.startswith("BBM"):
        return "Product / BBM"
    return None


def build_map_flow() -> dict:
    """Renewal v2: produce a single payload covering ports + Top 30 routes
    grouped by category for the new Home flow map.

    Source = docs/data/tanker_flow_map.json (already 24M aggregate). The
    payload reshape is light (no SQL), so this is fast.
    """
    src = _load_json(DATA / "tanker_flow_map.json")
    raw_ports = src.get("ports", [])
    lanes = src.get("lanes", [])
    totals = src.get("totals", {})

    # ---- Aggregate per (origin, destination) -> ton + calls + categories ----
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"ton": 0.0, "calls": 0, "vessels": 0, "category_ton": defaultdict(float)}
    )
    for ln in lanes:
        o = ln.get("o"); d = ln.get("d")
        if not o or not d:
            continue
        key = (o, d)
        ton = float(ln.get("ton") or 0.0)
        agg[key]["ton"] += ton
        agg[key]["calls"] += int(ln.get("calls") or 0)
        agg[key]["vessels"] += int(ln.get("vessels") or 0)
        cat = _bucket_to_category(ln.get("bucket"))
        if cat:
            agg[key]["category_ton"][cat] += ton

    # ---- Top 30 routes by total ton (excluding self-loops) ----
    candidates = [(k, v) for k, v in agg.items() if k[0] != k[1]]
    candidates.sort(key=lambda kv: kv[1]["ton"], reverse=True)
    top30 = candidates[:30]

    # Look up port coords from the raw ports list
    port_idx = {p["port"]: p for p in raw_ports}

    routes_top30 = []
    for (o, d), v in top30:
        op = port_idx.get(o)
        dp = port_idx.get(d)
        if not op or not dp:
            continue
        # Pick dominant category by ton share
        cat_share = sorted(v["category_ton"].items(), key=lambda kv: -kv[1])
        primary_cat = cat_share[0][0] if cat_share else None
        routes_top30.append({
            "origin": o,
            "destination": d,
            "lat_o": op.get("lat"), "lon_o": op.get("lon"),
            "lat_d": dp.get("lat"), "lon_d": dp.get("lon"),
            "ton_24m": round(v["ton"], 1),
            "calls": v["calls"],
            "vessels": v["vessels"],
            "category": primary_cat,
            "category_ton": {k: round(t, 1) for k, t in cat_share},
        })

    # ---- Ports payload (sized by ton, sorted desc; cap at top 60 for clarity) ----
    ports_sorted = sorted(raw_ports, key=lambda p: p.get("ton") or 0, reverse=True)
    ports_out = [
        {
            "name": p["port"],
            "lat": p.get("lat"),
            "lon": p.get("lon"),
            "ton_24m": round(p.get("ton") or 0.0, 1),
        }
        for p in ports_sorted[:60]
        if p.get("lat") is not None and p.get("lon") is not None
    ]

    # ---- Foreign ports placeholder (intl_ton from totals only; per-port aggregation
    # would require parsing TIBA.DARI / BERANGKAT.KE in cargo_snapshot raw_row;
    # deferred to a follow-up since current tanker_flow_map already strips intl rows). ----
    foreign_ports = {
        "totals_intl_ton": totals.get("intl_ton"),
        "items": [],
        "note": (
            "Foreign-port breakdown deferred — needs LK3 raw_row parse "
            "for kind='ln' rows. Today only the aggregate intl_ton "
            "from tanker_flow_map.totals is exposed."
        ),
    }

    # ---- Insights (3 fact lines, rule-based, no value-judgement) ----
    total_top30 = sum(r["ton_24m"] for r in routes_top30) or 0.0
    biggest_port = ports_out[0] if ports_out else None
    biggest_route = routes_top30[0] if routes_top30 else None
    overall_ton = totals.get("plot_ton", 0) or 0
    intl_share = (
        (totals.get("intl_ton") or 0) /
        ((totals.get("plot_ton") or 0) + (totals.get("intl_ton") or 0))
    ) * 100 if (totals.get("plot_ton") and totals.get("intl_ton")) else None

    insights: list[str] = []
    if biggest_port and overall_ton > 0:
        share = (biggest_port["ton_24m"] / overall_ton) * 100
        insights.append(
            f"최대 거점 항구: {biggest_port['name']} "
            f"(24M ton의 {share:.1f}% 처리)"
        )
    if biggest_route:
        insights.append(
            f"최대 항로: {biggest_route['origin']} → {biggest_route['destination']} "
            f"({biggest_route['ton_24m']/1e6:.1f}M tons, "
            f"{biggest_route.get('vessels', 0)}척)"
        )
    if intl_share is not None:
        insights.append(
            f"국제(ln) 운항 ton 비중: {intl_share:.1f}% (24M 누계)"
        )

    # PR-12: top growing tanker subclass (12M-vs-prev-12M %)
    try:
        sub_facts_path = DERIVED / "subclass_facts.json"
        if sub_facts_path.exists():
            sf = json.loads(sub_facts_path.read_text(encoding="utf-8"))
            ranked = []
            for s in (sf.get("subclasses") or []):
                if s.get("subclass") == "UNKNOWN":
                    continue
                ton_last = s.get("ton_last_12m") or 0
                ton_prev = s.get("ton_prev_12m") or 0
                if ton_prev > 0:
                    ranked.append((s["subclass"], ((ton_last - ton_prev) / ton_prev) * 100))
            ranked.sort(key=lambda x: -x[1])
            if ranked:
                name, pct = ranked[0]
                insights.append(
                    f"가장 빠르게 증가한 subclass (12M vs 이전 12M): "
                    f"{name} ({'+' if pct >= 0 else ''}{pct:.1f}%)"
                )
    except Exception:
        pass

    # PR-12: average ton per Top 30 route — sense of route concentration
    if routes_top30:
        avg_route = sum(r["ton_24m"] for r in routes_top30) / len(routes_top30)
        insights.append(
            f"Top 30 항로당 평균 ton: {avg_route/1e6:.2f}M tons (24M 누계)"
        )

    return {
        "schema_version": 2,
        "snapshot_month": src.get("snapshot_month"),
        "categories": [
            {"name": name, "color": color}
            for name, color, _ in MAP_CATEGORIES
        ],
        "ports": ports_out,
        "routes_top30": routes_top30,
        "foreign_ports": foreign_ports,
        "insights": insights,
        "totals": {
            "domestic_ton": totals.get("plot_ton"),
            "intl_ton": totals.get("intl_ton"),
            "unknown_ton": totals.get("unknown_ton"),
        },
        "_notes": {
            "scope": "domestic Indonesian flows from tanker_flow_map.lanes (24M aggregate)",
            "foreign_ports": "aggregate ton only; per-port breakdown deferred",
            "category_assignment": "primary category = bucket with highest ton share per route",
        },
    }


def build_route_facts() -> dict:
    """Top 60 OD-pair routes aggregated from tanker_flow_map.lanes."""
    flow = _load_json(DATA / "tanker_flow_map.json")
    lanes = flow.get("lanes", [])
    agg: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"ton": 0.0, "calls": 0, "vessels": 0, "buckets": set()}
    )
    for ln in lanes:
        key = (ln.get("o"), ln.get("d"))
        agg[key]["ton"] += float(ln.get("ton") or 0.0)
        agg[key]["calls"] += int(ln.get("calls") or 0)
        agg[key]["vessels"] += int(ln.get("vessels") or 0)
        if ln.get("bucket"):
            agg[key]["buckets"].add(ln["bucket"])

    rows = [
        {
            "origin": o,
            "destination": d,
            "ton_24m": round(v["ton"], 1),
            "calls_24m": v["calls"],
            "vessels_seen": v["vessels"],
            "buckets": sorted(v["buckets"]),
            "is_self_loop": o == d,
        }
        for (o, d), v in agg.items()
    ]
    rows.sort(key=lambda r: r["ton_24m"], reverse=True)
    return {
        "schema_version": 1,
        "snapshot_month": flow["snapshot_month"],
        "top_n": 60,
        "routes": rows[:60],
        "_notes": {
            "source": "tanker_flow_map.lanes (24M aggregate)",
            "change_pct_24m": (
                "null in v0 — requires per-month OD aggregation; planned "
                "for PR-D iteration once a second snapshot lands"
            ),
        },
    }


# ----------------------------------------------------------------------
# 4. owner_profile.json
# ----------------------------------------------------------------------
def build_owner_profile(ticker_map: dict[str, list[str]]) -> tuple[dict, list[str]]:
    """Per-owner tanker profile + ticker linkage. Returns (payload, unmatched names)."""
    tf = _load_json(DATA / "tanker_focus.json")
    fleet_owners = tf["fleet_owners"]

    rev: dict[str, str] = {}
    for ticker, names in ticker_map.items():
        for n in names:
            rev[_norm_company(n)] = ticker

    matched: set[str] = set()
    profile = []
    for fo in fleet_owners:
        norm = _norm_company(fo["owner"])
        ticker = rev.get(norm)
        if ticker:
            matched.add(norm)
        profile.append({
            "owner": fo["owner"],
            "owner_norm": norm,
            "ticker": ticker,
            "tankers": fo["tanker_count"],
            "sum_gt": fo["sum_gt"],
            "avg_gt": fo["avg_gt"],
            "max_gt": fo.get("max_gt"),
            "subclass_mix": fo.get("subclass_counts", {}),
        })
    profile.sort(key=lambda x: x.get("sum_gt") or 0, reverse=True)

    unmatched = sorted(set(rev) - matched)
    payload = {
        "schema_version": 1,
        "snapshot_month": tf["snapshot_month"],
        "owners": profile,
        "_notes": {
            "scope": "Top tanker operators (tanker_focus.fleet_owners — currently top 50 by sum_gt)",
            "ticker_source": "owner_ticker_map.json",
            "top_routes": (
                "Per-owner top routes deferred to PR-D iteration "
                "(needs LK3 vessel-level join)"
            ),
        },
    }
    return payload, unmatched


# ----------------------------------------------------------------------
# 5. recent_events.json
# ----------------------------------------------------------------------
def build_recent_events() -> dict:
    """Surface notable events. v0: baseline-only — derives from vessels_changes
    ADDED + GT≥5000, capped to top 30 by GT, with a note explaining the
    full MoM event logic activates once a second snapshot lands.
    """
    events = []
    with sqlite3.connect(DB) as con:
        cur = con.cursor()
        # GT data lives in vessels_snapshot, not vessels_current (latter is null).
        cur.execute(
            """
            SELECT vc.change_month,
                   vs.vessel_key,
                   vs.nama_kapal,
                   vs.jenis_kapal,
                   vs.gt,
                   vs.nama_pemilik
              FROM vessels_changes vc
              JOIN vessels_snapshot vs
                ON vs.vessel_key = vc.vessel_key
               AND vs.snapshot_month = vc.change_month
             WHERE vc.change_type IN ('added', 'ADDED')
               AND vs.gt IS NOT NULL
               AND vs.gt >= 5000
             ORDER BY vs.gt DESC
             LIMIT 30
            """
        )
        for (cm, vk, name, jk, gt, owner) in cur.fetchall():
            events.append({
                "date": cm,
                "type": "new_registration",
                "summary": (
                    f"등록 선박: {name or '(이름 없음)'}  GT {int(gt or 0):,}  "
                    f"owner: {owner or 'N/A'}"
                ),
                "_meta": {
                    "vessel_key": vk,
                    "gt": gt,
                    "jenis_kapal_code": jk,
                },
                "chart_link": "#tab-fleet",
            })

    events.sort(key=lambda e: (e["date"], e["_meta"].get("gt") or 0), reverse=True)
    return {
        "schema_version": 1,
        "events": events,
        "_notes": {
            "v0_mode": (
                "Baseline-only snapshot (one cargo/vessel month). All vessels are "
                "ADDED records — the v0 surfaces top-30 by GT as a sample. "
                "Genuine MoM event detection (port_change, fleet_change, "
                "subclass volume_change) activates once a second snapshot lands."
            ),
            "thresholds_pending": {
                "new_registration": "GT ≥ 5,000 + tanker subclass",
                "port_change": "ABS(MoM ton delta_pct) ≥ 50%",
                "fleet_change": "owner ±3 vessels in 1 month",
                "volume_change": "subclass MoM ton delta_pct ≥ 30%",
            },
        },
    }


# ----------------------------------------------------------------------
# PR-D: 7. regulatory_notes.html (markdown -> minimal HTML)
# ----------------------------------------------------------------------
def md_to_html(md: str) -> str:
    """Tiny markdown subset converter: H1/H2/H3, lists, paragraphs,
    blockquotes, **bold**, `code`, [text](url), ---. Used to embed
    data/regulatory_notes.md into a collapsible block in PR-D.
    """
    def inline(s: str) -> str:
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2" target="_blank" rel="noopener" class="text-blue-600 hover:underline">\1</a>',
            s,
        )
        return s

    out: list[str] = []
    in_ul = False
    in_paragraph: list[str] = []

    def _flush_paragraph():
        if in_paragraph:
            out.append("<p>" + " ".join(in_paragraph) + "</p>")
            in_paragraph.clear()

    def _close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            _flush_paragraph()
            _close_ul()
            continue
        if line.startswith("# "):
            _flush_paragraph(); _close_ul()
            out.append(f"<h2>{inline(line[2:])}</h2>")
        elif line.startswith("## "):
            _flush_paragraph(); _close_ul()
            out.append(f"<h3>{inline(line[3:])}</h3>")
        elif line.startswith("### "):
            _flush_paragraph(); _close_ul()
            out.append(f"<h4>{inline(line[4:])}</h4>")
        elif line.startswith("---"):
            _flush_paragraph(); _close_ul()
            out.append("<hr>")
        elif line.startswith("> "):
            _flush_paragraph(); _close_ul()
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif line.startswith("- "):
            _flush_paragraph()
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(line[2:])}</li>")
        else:
            _close_ul()
            in_paragraph.append(inline(line))

    _flush_paragraph()
    _close_ul()
    return "\n".join(out)


def build_regulatory_notes() -> str | None:
    src = ROOT / "data" / "regulatory_notes.md"
    if not src.exists():
        return None
    html = md_to_html(src.read_text(encoding="utf-8"))
    out = DERIVED / "regulatory_notes.html"
    out.write_text(html, encoding="utf-8")
    return html


# ----------------------------------------------------------------------
# 6. owner_ticker_map.json
# ----------------------------------------------------------------------
def build_owner_ticker_map() -> dict:
    return {
        "schema_version": 1,
        "tickers": OWNER_TICKER_INITIAL,
        "_notes": {
            "source": "Manual seed list (INSTRUCTIONS.md §3). Verify against IDX corporate disclosures.",
            "matching": "Frontend + builds match by normalized owner name (PT/Tbk/punct stripped, case-folded).",
        },
    }


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
def main() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)
    print(f"Building derived JSON → {DERIVED}")

    bytes_total = 0

    meta = build_meta()
    bytes_total += _write_json(DERIVED / "meta.json", meta)
    print(f"  meta.json — latest_lk3={meta['latest_lk3_month']} "
          f"(partial_dropped={meta['latest_lk3_partial_dropped']})")

    sub = build_subclass_facts()
    bytes_total += _write_json(DERIVED / "subclass_facts.json", sub)
    print(f"  subclass_facts.json — {len(sub['subclasses'])} subclasses")

    rt = build_route_facts()
    bytes_total += _write_json(DERIVED / "route_facts.json", rt)
    print(f"  route_facts.json — top {len(rt['routes'])} routes")

    mp = build_map_flow()
    bytes_total += _write_json(DERIVED / "map_flow.json", mp)
    print(f"  map_flow.json — {len(mp['ports'])} ports + "
          f"{len(mp['routes_top30'])} routes (renewal v2)")

    # PR-3: Home + Subclass cards / Top widgets payloads
    hk = build_home_kpi()
    bytes_total += _write_json(DERIVED / "home_kpi.json", hk)
    print(f"  home_kpi.json — {len(hk['kpis'])} KPIs (renewal v2)")

    ts = build_timeseries()
    bytes_total += _write_json(DERIVED / "timeseries.json", ts)
    print(f"  timeseries.json — {len(ts['periods'])} periods × {len(ts['series'])} sectors")

    tsub = build_tanker_subclass()
    bytes_total += _write_json(DERIVED / "tanker_subclass.json", tsub)
    print(f"  tanker_subclass.json — {len(tsub['cards'])} subclass cards + "
          f"{len(tsub['monthly']['periods'])} months stacked")

    ttop = build_tanker_top()
    bytes_total += _write_json(DERIVED / "tanker_top.json", ttop)
    print(f"  tanker_top.json — {len(ttop['top_commodities'])} commodities + "
          f"{len(ttop['top_operators'])} operators")

    cf = build_cargo_fleet()
    bytes_total += _write_json(DERIVED / "cargo_fleet.json", cf)
    print(f"  cargo_fleet.json — {len(cf['treemap_categories'])} treemap + "
          f"{len(cf['top_commodities'])} commodities + {len(cf['class_counts'])} classes + "
          f"{len(cf['age_bins']['bins'])} age bins")

    cy = build_cargo_yearly()
    bytes_total += _write_json(DERIVED / "cargo_yearly.json", cy)
    _year_summary = ", ".join(
        f"{y}: {cy['months_per_year'][y]}mo" for y in cy["years"]
    )
    print(f"  cargo_yearly.json — {len(cy['years'])} years ({_year_summary})")

    tk = build_owner_ticker_map()
    bytes_total += _write_json(DERIVED / "owner_ticker_map.json", tk)
    print(f"  owner_ticker_map.json — {len(tk['tickers'])} tickers")
    # Canonical hand-edit copy at data/owner_ticker_map.json
    src_map_path = ROOT / "data" / "owner_ticker_map.json"
    src_map_path.write_text(
        json.dumps(tk, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  data/owner_ticker_map.json — manual-seed source")

    op, unmatched = build_owner_profile(tk["tickers"])
    bytes_total += _write_json(DERIVED / "owner_profile.json", op)
    print(f"  owner_profile.json — {len(op['owners'])} owners "
          f"(matched: {len(tk['tickers']) - len(unmatched)}/{len(tk['tickers'])} tickers)")

    # Full cargo-fleet owner ranking from vessels_snapshot (kapal.dephub.go.id).
    _snap = _load_json(DATA / "meta.json").get("latest")
    fo = build_fleet_owners(_snap)
    bytes_total += _write_json(DERIVED / "fleet_owners.json", fo)
    print(f"  fleet_owners.json — {fo['totals']['cargo_vessels']:,} cargo vessels · "
          f"{fo['totals']['unique_owners']:,} unique owners (top {len(fo['owners'])})")

    # Per-vessel registry export — drives the Fleet tab's filter+list view.
    fv = build_fleet_vessels(_snap)
    # The vessel-list file is much larger than other derived JSONs; emit
    # compact (no indentation) to halve its size.
    _path = DERIVED / "fleet_vessels.json"
    _text = json.dumps(fv, ensure_ascii=False, separators=(",", ":"), default=str)
    _path.write_text(_text, encoding="utf-8")
    bytes_total += len(_text)
    print(f"  fleet_vessels.json — {len(fv['rows']):,} vessels (compact)")
    if unmatched:
        log_path = DERIVED / "unmatched.log"
        log_path.write_text("\n".join(unmatched) + "\n", encoding="utf-8")
        print(f"    → unmatched.log ({len(unmatched)} entries)")

    # Renewal v2: Recent Events panel removed with the Changes tab. Drop the
    # stale payload if a previous build left it on disk.
    legacy = DERIVED / "recent_events.json"
    if legacy.exists():
        legacy.unlink()
        print(f"  recent_events.json — removed (Changes tab dropped in v2)")

    reg = build_regulatory_notes()
    if reg is not None:
        bytes_total += len(reg)
        print(f"  regulatory_notes.html — {len(reg):,} bytes")
    else:
        print("  regulatory_notes.html — skipped (data/regulatory_notes.md missing)")

    print(f"Done. Total bytes: {bytes_total:,}")


if __name__ == "__main__":
    main()
