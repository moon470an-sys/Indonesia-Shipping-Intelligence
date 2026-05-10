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
    if unmatched:
        log_path = DERIVED / "unmatched.log"
        log_path.write_text("\n".join(unmatched) + "\n", encoding="utf-8")
        print(f"    → unmatched.log ({len(unmatched)} entries)")

    ev = build_recent_events()
    bytes_total += _write_json(DERIVED / "recent_events.json", ev)
    print(f"  recent_events.json — {len(ev['events'])} events")

    print(f"Done. Total bytes: {bytes_total:,}")


if __name__ == "__main__":
    main()
