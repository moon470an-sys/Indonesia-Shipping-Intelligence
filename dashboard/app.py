"""Streamlit dashboard for the Indonesia Shipping BI system.

Run with:
    python -m streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# allow `import backend.*` when launched as `streamlit run dashboard/app.py`
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard import queries as q
from dashboard import format as fmt
from dashboard import theme

st.set_page_config(
    page_title="Indonesia Shipping BI",
    page_icon=":ship:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject Pretendard font + design tokens. Plotly "sti" template is registered
# at theme-module import time, so every chart picks it up automatically.
theme.apply()


# ------------------------- caching -------------------------
# small reference lookups: cache for an hour
@st.cache_data(ttl=3600)
def _vessel_months(): return q.vessel_snapshot_months()
@st.cache_data(ttl=3600)
def _cargo_months(): return q.cargo_snapshot_months()
@st.cache_data(ttl=3600)
def _change_months(): return q.change_months()
@st.cache_data(ttl=3600)
def _ports(): return q.ports()
@st.cache_data(ttl=3600)
def _vessel_codes(m): return q.vessel_search_codes(m)

# heavier rollups: cache for 30 min
@st.cache_data(ttl=1800)
def _vessel_overview(m): return q.vessel_overview(m)
@st.cache_data(ttl=1800)
def _vessels_full(m): return q.vessels_full(m)
@st.cache_data(ttl=1800)
def _tankers_full(m): return q.tankers_full(m)
@st.cache_data(ttl=1800)
def _cargo_vessels_full(m): return q.cargo_vessels_full(m)
# Tanker cargo-flow extract is heavy (~40s on first hit, single full-table
# json_extract scan). Cache long.
@st.cache_data(ttl=3600)
def _tanker_cargo_flows(m): return q.tanker_cargo_flows(m)
# Generic cargo flows — same shape as tanker_cargo_flows but excludes
# fishing/passenger; heavier scan, cache long.
@st.cache_data(ttl=3600)
def _cargo_flows(m): return q.cargo_flows(m)
# Snapshot-trend stack — depends on per-snapshot KPI compute; cache long.
@st.cache_data(ttl=3600)
def _tanker_snapshot_trend(): return q.tanker_snapshot_trend()
@st.cache_data(ttl=1800)
def _cargo_overview(m): return q.cargo_overview(m)
@st.cache_data(ttl=1800)
def _change_kpis(m): return q.change_kpis(m)
@st.cache_data(ttl=1800)
def _vessel_types(m, top): return q.vessel_types(m, top)
@st.cache_data(ttl=1800)
def _vessel_owners(m, top): return q.vessel_owners(m, top)
@st.cache_data(ttl=1800)
def _vessel_age(m): return q.vessel_age_distribution(m)
@st.cache_data(ttl=1800)
def _gt_dist(m): return q.gt_distribution(m)
@st.cache_data(ttl=1800)
def _port_traffic(m, top): return q.port_traffic(m, top)
@st.cache_data(ttl=1800)
def _monthly_traffic(m): return q.monthly_traffic(m)
@st.cache_data(ttl=1800)
def _cargo_summary(m): return q.cargo_summary(m)
@st.cache_data(ttl=1800)
def _ingestion_runs(): return q.ingestion_runs()
@st.cache_data(ttl=1800)
def _validator_summary(m): return q.validator_summary(m)
@st.cache_data(ttl=1800)
def _validator_recent(table, m, limit=200): return q.validator_recent_fixes(table, m, limit)
@st.cache_data(ttl=1800)
def _coverage_status(m): return q.coverage_status(m)
@st.cache_data(ttl=1800)
def _validator_extreme(m, threshold=1000.0, limit=200):
    return q.validator_extreme_fixes(m, threshold, limit)
@st.cache_data(ttl=1800)
def _residual_fleet_anomalies(m): return q.residual_fleet_anomalies(m)
@st.cache_data(ttl=1800)
def _vessel_utilization(m): return q.vessel_utilization(m)
@st.cache_data(ttl=1800)
def _cargo_vessel_utilization(m): return q.cargo_vessel_utilization(m)
@st.cache_data(ttl=1800)
def _korean_tankers(m): return q.korean_affiliated_tankers(m)
@st.cache_data(ttl=1800)
def _pertamina_fleet(m): return q.pertamina_fleet(m)
@st.cache_data(ttl=1800)
def _pertamina_op(m): return q.pertamina_operator_activity(m)
@st.cache_data(ttl=1800)
def _idx_listed_match(m): return q.idx_listed_tanker_match(m)
@st.cache_data(ttl=1800)
def _tbk_owners(m): return q.publicly_listed_tanker_owners(m)
@st.cache_data(ttl=600)
def _vessel_lookup(name_q, imo_q, limit=50):
    return q.vessel_lookup(name_q, imo_q, limit)
@st.cache_data(ttl=600)
def _vessel_cargo_activity(name_q, snap, limit=500):
    return q.vessel_cargo_activity(name_q, snap, limit)


# ------------------------- sidebar + URL state -------------------------
# `st.query_params` lets users bookmark / share specific views. We read the
# URL once on page load to seed the widgets, then write the current selection
# back so refreshes / copy-paste preserve state.
qp = st.query_params

st.sidebar.markdown("### :ship: Indonesia Shipping BI")
v_months = _vessel_months()
c_months = _cargo_months()
all_snaps = sorted(set(v_months) | set(c_months), reverse=True)
if not all_snaps:
    st.sidebar.error("DB가 비어있습니다. 먼저 `python -m backend.main monthly --auto` 실행")
    st.stop()

# Snapshot — defaults to URL value if present, else most recent.
url_snap = qp.get("snapshot")
snap_idx = all_snaps.index(url_snap) if url_snap in all_snaps else 0
snapshot = st.sidebar.selectbox("Snapshot month", all_snaps, index=snap_idx)

ch_months = _change_months()
ch_options = ch_months or [snapshot]
url_chm = qp.get("change_month")
chm_idx = ch_options.index(url_chm) if url_chm in ch_options else 0
change_month = st.sidebar.selectbox(
    "Change month", ch_options, index=chm_idx,
    help="변경 탐지 결과를 볼 기준 달",
)

PAGE_OPTIONS = ["📊 Overview", "🚢 Fleet", "🛢️ Tanker", "🇮🇩 Pertamina",
                "📦 Cargo", "🔄 Changes", "🔍 데이터 품질", "⚙️ Ingestion"]
url_page = qp.get("page")
page_idx = PAGE_OPTIONS.index(url_page) if url_page in PAGE_OPTIONS else 0
page = st.sidebar.radio(
    "페이지", PAGE_OPTIONS, index=page_idx, label_visibility="collapsed",
)

# Persist selection back to URL.
qp["snapshot"] = snapshot
qp["change_month"] = change_month
qp["page"] = page

st.sidebar.markdown("---")
with st.sidebar.expander("📤 공유 / Export"):
    st.caption(
        "현재 선택된 **snapshot · change month · 페이지**가 URL 쿼리에 "
        "기록됩니다. 브라우저 주소창의 URL을 그대로 복사해 공유하면 "
        "동일한 뷰가 열립니다."
    )
    st.code(
        f"?snapshot={snapshot}&change_month={change_month}&page={page}",
        language=None,
    )

st.sidebar.caption(f"DB: `data/shipping_bi.db`")
st.sidebar.caption(f"Vessel snapshots: {len(v_months)}")
st.sidebar.caption(f"Cargo snapshots: {len(c_months)}")


# ------------------------- export helpers -------------------------

def _csv_bytes(df: pd.DataFrame) -> bytes:
    """UTF-8 with BOM so Excel auto-detects encoding for Korean headers."""
    return df.to_csv(index=False).encode("utf-8-sig")


def _csv_button(df: pd.DataFrame, filename: str,
                label: str = "📥 CSV 다운로드", key: str | None = None) -> None:
    """Render a Streamlit download button for a DataFrame as UTF-8-BOM CSV."""
    if df is None or df.empty:
        return
    st.download_button(
        label, _csv_bytes(df),
        file_name=filename,
        mime="text/csv",
        key=key or f"dl_{filename}",
    )


# ------------------------- helpers -------------------------
def kpi(col, label, value, delta=None, fmt_tpl="{:,}", help=None,
        delta_color="off"):
    """Render a KPI tile.

    `delta` accepts either a signed number (then `delta_color="normal"` shows
    green/red arrows) or a descriptive string (then `delta_color="off"`
    suppresses the auto-coloring — the default, since most deltas in this
    dashboard are sub-labels, not signed metrics).

    `help` adds a Korean tooltip on the (?) icon.
    """
    if isinstance(value, (int, float)):
        v = fmt_tpl.format(value)
    else:
        v = str(value)
    col.metric(label, v, delta=delta, help=help, delta_color=delta_color)


# ------------------------- pages -------------------------

def page_overview():
    st.title("📊 Overview")
    st.caption(f"Snapshot: **{snapshot}** · Change month: **{change_month}**")

    v = _vessel_overview(snapshot)
    c = _cargo_overview(snapshot)
    k = _change_kpis(change_month)

    theme.hero_strip(
        "📦 적재 현황",
        f"{snapshot} 스냅샷 기준 — 선박 등기, 항구, LK3 물동량 적재 상태",
    )
    cols = st.columns(4)
    kpi(cols[0], "선박 등록 (전체)", v["total"],
        help="vessels_snapshot.row_count — 56개 검색코드 합산 (어선·여객선 포함)")
    kpi(cols[1], "검색 코드", f"{v['codes']}/56", help="실제로 데이터가 들어온 검색코드 수")
    kpi(cols[2], "항구", c["ports"], help="LK3에서 등장한 고유 항구 수 (origin+destination)")
    kpi(cols[3], "물동량 행", c["rows"], help="cargo_snapshot.row_count — 24mo 누적")

    # Cargo-sector scope: Fleet/Cargo tabs show the filtered subset shown here.
    cargo_fleet = _cargo_vessels_full(snapshot)
    if not cargo_fleet.empty:
        cargo_gt = pd.to_numeric(cargo_fleet["gt"], errors="coerce").fillna(0).sum()
        class_mix = cargo_fleet["vessel_class"].value_counts().to_dict()
        st.markdown("##### 화물선 (CARGO sector) 현황 — Fleet · Cargo 탭이 사용하는 범위")
        cols2 = st.columns(6)
        kpi(cols2[0], "화물선 수", fmt.fmt_int(len(cargo_fleet)),
            help=f"전체 등기 {v['total']:,}척 중 어선·여객선·예인선·정부선 제외")
        kpi(cols2[1], "총 GT", fmt.fmt_gt(float(cargo_gt)))
        kpi(cols2[2], "Tanker", fmt.fmt_int(int(class_mix.get("Tanker", 0))))
        kpi(cols2[3], "General Cargo",
            fmt.fmt_int(int(class_mix.get("General Cargo", 0))))
        kpi(cols2[4], "Container + Bulk",
            fmt.fmt_int(int(class_mix.get("Container", 0)
                            + class_mix.get("Bulk Carrier", 0))))
        kpi(cols2[5], "Other Cargo (Barge 등)",
            fmt.fmt_int(int(class_mix.get("Other Cargo", 0))))

    st.subheader(f"{change_month} 변경 탐지 KPI")
    cols = st.columns(6)
    kpi(cols[0], "선박 ADDED", k["vessel_added"])
    kpi(cols[1], "선박 REMOVED", k["vessel_removed"])
    kpi(cols[2], "선박 MODIFIED 셀", k["vessel_modified_cells"])
    kpi(cols[3], "Cargo ADDED 키", k["cargo_added"])
    kpi(cols[4], "Cargo REMOVED 키", k["cargo_removed"])
    kpi(cols[5], "Cargo REVISED 셀", k["cargo_revised_cells"])

    st.subheader("월별 LK3 데이터 행 수")
    mt = _monthly_traffic(snapshot)
    if mt.empty:
        st.info("물동량 데이터가 없습니다.")
    else:
        fig = px.bar(mt, x="period", y="rows", color="kind",
                     barmode="group",
                     labels={"period": "데이터 월", "rows": "행 수"})
        fig.update_layout(height=380, margin=dict(t=20, b=20))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Top 항구")
    pt = _port_traffic(snapshot, 20)
    if not pt.empty:
        fig = px.bar(pt, x="kode_pelabuhan", y="rows_total",
                     hover_data=["nama_pelabuhan", "rows_dn", "rows_ln", "months_covered"],
                     labels={"kode_pelabuhan": "항구 코드", "rows_total": "총 LK3 행 수"})
        fig.update_layout(height=380, margin=dict(t=20, b=20))
        st.plotly_chart(fig, width="stretch")


def _avg_pos(s: pd.Series) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[s > 0]
    return float(s.mean()) if len(s) else 0.0


# Stable color map for the cargo vessel-class facet (used by Fleet tab).
_CARGO_CLASS_PALETTE = {
    "Tanker":         "#1e40af",
    "Container":      "#0891b2",
    "Bulk Carrier":   "#92400e",
    "General Cargo":  "#16a34a",
    "Other Cargo":    "#7c3aed",
}

# Fleet-page age bucket (matches taxonomy buckets used elsewhere).
_FLEET_AGE_BUCKETS = (
    ("Newbuild (<5y)",     0,  5),
    ("Modern (5-15y)",     5, 15),
    ("Aging (15-25y)",    15, 25),
    ("Retirement (≥25y)", 25, 99),
)


def _fleet_age_bucket(age: float | None) -> str | None:
    if age is None or pd.isna(age) or age < 0:
        return None
    for label, lo, hi in _FLEET_AGE_BUCKETS:
        if lo <= age < hi:
            return label
    return _FLEET_AGE_BUCKETS[-1][0]


def page_fleet():
    st.title("🚢 화물선 선대 분석")
    st.caption(
        f"Snapshot: **{snapshot}** · 어선 / 여객선 제외 · "
        "탱커 · 컨테이너 · 벌크 · 일반화물 · 기타화물 (바지 등) 5개 클래스 중심"
    )

    df = _cargo_vessels_full(snapshot)
    if df.empty:
        st.info("화물선 데이터 없음")
        return

    total_rows = len(df)

    # ---- numeric bounds (drive slider defaults) ----
    yrs = df["tahun_num"].dropna()
    yr_min = int(yrs.min()) if not yrs.empty else 1900
    yr_max = int(yrs.max()) if not yrs.empty else 2100

    def _bounds(s: pd.Series, default_max: float):
        s = pd.to_numeric(s, errors="coerce").dropna()
        s = s[s >= 0]
        if s.empty:
            return 0.0, float(default_max)
        return 0.0, float(max(s.max(), 1.0))

    gt_lo, gt_hi = _bounds(df["gt"], 100000)
    loa_lo, loa_hi = _bounds(df["loa"], 500)

    rt = st.session_state.get("fleet_reset_token", 0)

    # ---------------- Filters ----------------
    with st.expander("🔍 필터 (필요 시 클릭으로 좁히기)", expanded=True):
        c0a, c0b = st.columns([2, 2])

        class_options = (df["vessel_class"]
                            .dropna().value_counts().index.tolist())
        with c0a:
            st.markdown("**Vessel Class**")
            sel_classes = st.multiselect(
                "Vessel Class", class_options, default=class_options,
                key=f"ft_class_{rt}", label_visibility="collapsed",
                help="화물선 5개 클래스 — 비어두면 전체",
            )
        with c0b:
            sub_options = sorted(
                [s for s in df.loc[df["vessel_class"] == "Tanker",
                                    "tanker_subclass"].dropna().unique() if s]
            )
            st.markdown("**Tanker Subclass** (Tanker 선택 시 적용)")
            sel_subs = st.multiselect(
                "Tanker Subclass", sub_options, default=sub_options,
                key=f"ft_sub_{rt}", label_visibility="collapsed",
            )

        c1, c2, c3 = st.columns(3)
        with c1:
            name_q = st.text_input("선박명 검색", key=f"ft_name_{rt}")
            owner_q = st.text_input("선주 / 회사 검색", key=f"ft_owner_{rt}")
            flags_all = sorted([f for f in df["bendera"].dropna().unique() if f])
            flag_sel = st.multiselect("국적 (Flag)", flags_all, default=[],
                                       key=f"ft_flag_{rt}",
                                       help="비어두면 모든 국적")

        with c2:
            yr_range = st.slider("건조 연도", yr_min, yr_max,
                                  (yr_min, yr_max), key=f"ft_yr_{rt}")
            age_bucket_options = [b[0] for b in _FLEET_AGE_BUCKETS]
            age_sel = st.multiselect(
                "선령 버킷", age_bucket_options, default=[],
                key=f"ft_age_{rt}",
                help="비어두면 모든 선령 · '결측' 데이터는 항상 포함",
            )

        with c3:
            gt_range = st.slider("Gross Tonnage", gt_lo, gt_hi, (gt_lo, gt_hi),
                                  key=f"ft_gt_{rt}")
            loa_range = st.slider("LOA (m)", loa_lo, loa_hi, (loa_lo, loa_hi),
                                   key=f"ft_loa_{rt}")

        if st.button("🔄 필터 초기화", key="ft_reset"):
            st.session_state["fleet_reset_token"] = rt + 1
            st.rerun()

    # ---------------- Apply filters ----------------
    df = df.assign(age_bucket=df["age"].map(_fleet_age_bucket))
    fdf = df
    if sel_classes:
        fdf = fdf[fdf["vessel_class"].isin(sel_classes)]
    # Subclass filter only narrows the Tanker rows — non-tankers pass through.
    if sel_subs and sub_options and len(sel_subs) != len(sub_options):
        mask_tanker = fdf["vessel_class"] == "Tanker"
        keep = (~mask_tanker) | (fdf["tanker_subclass"].isin(sel_subs))
        fdf = fdf[keep]

    def _between_or_na(s, lo, hi):
        s = pd.to_numeric(s, errors="coerce")
        return s.between(lo, hi) | s.isna()

    fdf = fdf[_between_or_na(fdf["tahun_num"], yr_range[0], yr_range[1])]
    fdf = fdf[_between_or_na(fdf["gt"], gt_range[0], gt_range[1])]
    fdf = fdf[_between_or_na(fdf["loa"], loa_range[0], loa_range[1])]

    if age_sel:
        fdf = fdf[fdf["age_bucket"].isin(age_sel) | fdf["age_bucket"].isna()]
    if flag_sel:
        fdf = fdf[fdf["bendera"].isin(flag_sel)]
    if name_q:
        fdf = fdf[fdf["nama_kapal"].fillna("").str.contains(
            name_q, case=False, na=False)]
    if owner_q:
        fdf = fdf[fdf["nama_pemilik"].fillna("").str.contains(
            owner_q, case=False, na=False)]

    st.caption(
        f"화물선 (CARGO sector) · **{snapshot}** · "
        f"{len(fdf):,} / {total_rows:,} 척"
    )

    # ---------------- KPI summary ----------------
    cols = st.columns(5)
    gt_total = pd.to_numeric(fdf["gt"], errors="coerce").fillna(0).sum()
    kpi(cols[0], "선박 수", fmt.fmt_int(len(fdf)))
    kpi(cols[1], "총 GT", fmt.fmt_gt(float(gt_total)))
    avg_age = fdf["age"].dropna().mean()
    kpi(cols[2], "평균 선령",
        f"{avg_age:.1f}년" if pd.notna(avg_age) else "-")
    kpi(cols[3], "고유 선주",
        fmt.fmt_int(int(fdf["nama_pemilik"].dropna().nunique())))
    kpi(cols[4], "Class 수",
        fmt.fmt_int(int(fdf["vessel_class"].nunique())))

    st.markdown("---")

    # ---------------- Sub-tabs ----------------
    sub_comp, sub_age, sub_owner, sub_util, sub_list = st.tabs(
        ["📊 구성 (Class · Subclass)",
         "📅 선령 / 연도 분포",
         "🏢 선주 · 국적",
         "🛳️ 가동률 (Class별)",
         "📋 선박 리스트"]
    )

    # ============ 1) Composition ============
    with sub_comp:
        cA, cB = st.columns(2)
        with cA:
            st.markdown("**Vessel Class 비중**")
            cls_dist = fdf["vessel_class"].value_counts().reset_index()
            cls_dist.columns = ["vessel_class", "count"]
            if cls_dist.empty:
                st.info("데이터 없음")
            else:
                fig = px.pie(cls_dist, names="vessel_class", values="count",
                              color="vessel_class",
                              color_discrete_map=_CARGO_CLASS_PALETTE,
                              hole=0.5)
                fig.update_traces(textinfo="percent+label",
                                  textposition="outside")
                fig.update_layout(height=360, margin=dict(t=10, b=10),
                                  legend=dict(font=dict(size=10)))
                theme.donut_center(fig,
                                   fmt.fmt_int(int(cls_dist["count"].sum())),
                                   "화물선")
                st.plotly_chart(fig, width="stretch")

        with cB:
            st.markdown("**Class 별 총 GT**")
            cls_gt = (fdf.assign(
                gt_num=pd.to_numeric(fdf["gt"], errors="coerce").fillna(0))
                .groupby("vessel_class")["gt_num"].sum()
                .reset_index().sort_values("gt_num", ascending=True))
            if cls_gt.empty:
                st.info("데이터 없음")
            else:
                fig = px.bar(cls_gt, x="gt_num", y="vessel_class",
                              orientation="h",
                              color="vessel_class",
                              color_discrete_map=_CARGO_CLASS_PALETTE,
                              labels={"gt_num": "총 GT",
                                      "vessel_class": ""})
                fig.update_layout(height=360, margin=dict(t=10, b=10),
                                  showlegend=False)
                st.plotly_chart(fig, width="stretch")

        st.markdown("**Tanker Subclass 세부 (척수 + 총 GT)**")
        tk = fdf[fdf["vessel_class"] == "Tanker"]
        if tk.empty:
            st.info("Tanker 데이터 없음 — 필터 확인")
        else:
            sub_agg = (tk.assign(
                gt_num=pd.to_numeric(tk["gt"], errors="coerce").fillna(0))
                .groupby("tanker_subclass")
                .agg(척수=("vessel_key", "count"),
                     총_GT=("gt_num", "sum"),
                     평균_GT=("gt_num", "mean"))
                .reset_index().sort_values("척수", ascending=False))
            sub_agg["총_GT"] = sub_agg["총_GT"].round(0)
            sub_agg["평균_GT"] = sub_agg["평균_GT"].round(0)
            theme.dataframe(sub_agg)

            fig = px.bar(sub_agg.sort_values("척수"),
                          x="척수", y="tanker_subclass",
                          orientation="h",
                          color="tanker_subclass",
                          color_discrete_map=_TANKER_PALETTE,
                          labels={"tanker_subclass": ""})
            fig.update_layout(height=300, margin=dict(t=10, b=10),
                              showlegend=False)
            st.plotly_chart(fig, width="stretch")

    # ============ 2) Age / Year ============
    with sub_age:
        cA, cB = st.columns(2)
        with cA:
            st.markdown("**선령 버킷 분포 (Class 별)**")
            ab = fdf.dropna(subset=["age_bucket"]).groupby(
                ["age_bucket", "vessel_class"]).size().reset_index(name="n")
            if ab.empty:
                st.info("선령 데이터 없음")
            else:
                order = [b[0] for b in _FLEET_AGE_BUCKETS]
                fig = px.bar(ab, x="age_bucket", y="n",
                              color="vessel_class",
                              color_discrete_map=_CARGO_CLASS_PALETTE,
                              category_orders={"age_bucket": order},
                              labels={"age_bucket": "선령 버킷",
                                      "n": "척수"})
                fig.update_layout(height=360, margin=dict(t=10, b=10),
                                  legend=dict(orientation="h", y=-0.2,
                                               font=dict(size=10)))
                st.plotly_chart(fig, width="stretch")

        with cB:
            st.markdown("**건조 연도별 추이**")
            yr_df = (fdf.dropna(subset=["tahun_num"])
                         .assign(tahun=lambda x: x["tahun_num"].astype(int))
                         .groupby(["tahun", "vessel_class"]).size()
                         .reset_index(name="count"))
            if yr_df.empty:
                st.info("연도 데이터 없음")
            else:
                fig = px.area(yr_df, x="tahun", y="count",
                               color="vessel_class",
                               color_discrete_map=_CARGO_CLASS_PALETTE,
                               labels={"tahun": "건조 연도", "count": "척수"})
                fig.update_layout(height=360, margin=dict(t=10, b=10),
                                  legend=dict(orientation="h", y=-0.2,
                                               font=dict(size=10)))
                st.plotly_chart(fig, width="stretch")

        st.markdown("**GT 분포 (log scale)**")
        gt_d = fdf[pd.to_numeric(fdf["gt"], errors="coerce") > 0]
        if gt_d.empty:
            st.info("GT 데이터 없음")
        else:
            fig = px.histogram(gt_d, x="gt", nbins=60, log_x=True,
                                color="vessel_class",
                                color_discrete_map=_CARGO_CLASS_PALETTE,
                                opacity=0.75)
            fig.update_layout(height=340, margin=dict(t=10, b=10),
                              barmode="overlay",
                              xaxis_title="GT (log)", yaxis_title="척수",
                              legend=dict(font=dict(size=10)))
            st.plotly_chart(fig, width="stretch")

    # ============ 3) Owner / Flag ============
    with sub_owner:
        cA, cB = st.columns(2)
        with cA:
            st.markdown("**Top 선주 (척수 기준)**")
            top = st.slider("Top N", 5, 50, 20, 5, key="ft_owner_top")
            ow = (fdf.dropna(subset=["nama_pemilik"])
                       .groupby("nama_pemilik")
                       .agg(척수=("vessel_key", "count"),
                            총_GT=("gt", lambda s: pd.to_numeric(s, errors="coerce")
                                                       .fillna(0).sum()))
                       .reset_index().sort_values("척수", ascending=False)
                       .head(top))
            if ow.empty:
                st.info("선주 데이터 없음")
            else:
                ow["총_GT"] = ow["총_GT"].round(0)
                fig = px.bar(ow.sort_values("척수"),
                              x="척수", y="nama_pemilik",
                              orientation="h",
                              color="총_GT",
                              color_continuous_scale=theme.SCALES["blue"],
                              hover_data=["총_GT"],
                              labels={"nama_pemilik": ""})
                fig.update_layout(height=max(360, top * 22),
                                  margin=dict(t=10, b=10),
                                  coloraxis_showscale=False)
                st.plotly_chart(fig, width="stretch")

        with cB:
            st.markdown("**국적(Flag State) Top 15**")
            fl = (fdf["bendera"].dropna()
                       .loc[lambda s: s != ""]
                       .value_counts().head(15).reset_index())
            fl.columns = ["flag", "count"]
            if fl.empty:
                st.info("국적 데이터 없음")
            else:
                fig = px.bar(fl.sort_values("count"),
                              x="count", y="flag", orientation="h",
                              color="count",
                              color_continuous_scale=theme.SCALES["amber"],
                              labels={"count": "척수", "flag": ""})
                fig.update_layout(height=480, margin=dict(t=10, b=10),
                                  coloraxis_showscale=False)
                st.plotly_chart(fig, width="stretch")

    # ============ 4) Utilization (cross-class) ============
    with sub_util:
        st.caption(
            "**가동률 정의**: LK3 (cargo_snapshot)에 등장한 24개월 중 활동 개월 수. "
            "Heavy ≥18mo · Active 12–18mo · Light 6–12mo · Idle <6mo. "
            "매칭은 등기 `nama_kapal` ↔ LK3 `KAPAL` 대문자 동일 — "
            "동명/표기차 false negative 가능."
        )
        with st.spinner("선박-cargo 매칭 중…"):
            util = _cargo_vessel_utilization(snapshot)

        if util.empty:
            st.info("가동률 데이터를 계산할 수 없습니다.")
        else:
            # Restrict to currently-filtered fleet (by vessel_key)
            keep_keys = set(fdf["vessel_key"].dropna().tolist())
            uview = util[util["vessel_key"].isin(keep_keys)] if keep_keys \
                       else util

            if uview.empty:
                st.info("현재 필터 조건에 해당하는 가동률 데이터 없음.")
            else:
                # ---- KPI row ----
                n = len(uview)
                n_idle = int((uview["status"] == "Idle (<25%)").sum())
                n_heavy = int((uview["status"] == "Heavy (≥75%)").sum())
                idle_gt = float(pd.to_numeric(
                    uview.loc[uview["status"] == "Idle (<25%)", "gt"],
                    errors="coerce").fillna(0).sum())
                cols = st.columns(5)
                kpi(cols[0], "분석 선박", fmt.fmt_int(n))
                kpi(cols[1], "Idle 선박", fmt.fmt_int(n_idle))
                kpi(cols[2], "Idle 비율", fmt.fmt_pct(n_idle / n * 100))
                kpi(cols[3], "Idle 총 GT", fmt.fmt_gt(idle_gt),
                    help="유휴 선대의 총 GT — 자본 매몰 규모")
                kpi(cols[4], "Heavy 선박", fmt.fmt_int(n_heavy),
                    help="24개월 중 ≥ 18개월 활동 — 핵심 운영 자산")

                # ---- Per-class breakdown ----
                cA, cB = st.columns([2, 3])
                with cA:
                    st.markdown("**Class별 가동률 분포 (척수)**")
                    mat = (uview.groupby(["vessel_class", "status"])
                                .size().reset_index(name="n"))
                    pivot = mat.pivot_table(index="vessel_class",
                                              columns="status",
                                              values="n", fill_value=0)
                    status_order = ["Idle (<25%)", "Light (25–50%)",
                                     "Active (50–75%)", "Heavy (≥75%)"]
                    pivot = pivot.reindex(columns=[s for s in status_order
                                                       if s in pivot.columns],
                                            fill_value=0)
                    pivot["Total"] = pivot.sum(axis=1)
                    pivot["Idle_%"] = (pivot.get("Idle (<25%)", 0)
                                          / pivot["Total"] * 100).round(1)
                    pivot["Heavy_%"] = (pivot.get("Heavy (≥75%)", 0)
                                           / pivot["Total"] * 100).round(1)
                    pivot = pivot.sort_values("Total", ascending=False)
                    theme.dataframe(pivot.reset_index())

                with cB:
                    st.markdown("**Class별 Idle 비율 (높을수록 매물·차터 후보 多)**")
                    cls_idle = (uview.groupby("vessel_class")
                                      .agg(n=("vessel_key", "count"),
                                           idle_n=("status",
                                                    lambda s: (s == "Idle (<25%)").sum()))
                                      .reset_index())
                    cls_idle["idle_pct"] = (cls_idle["idle_n"]
                                                / cls_idle["n"] * 100).round(1)
                    cls_idle = cls_idle.sort_values("idle_pct",
                                                       ascending=True)
                    fig = px.bar(cls_idle, x="idle_pct", y="vessel_class",
                                  orientation="h", color="vessel_class",
                                  color_discrete_map=_CARGO_CLASS_PALETTE,
                                  hover_data=["n", "idle_n"],
                                  labels={"idle_pct": "Idle 비율 (%)",
                                            "vessel_class": ""})
                    fig.update_layout(height=320, margin=dict(t=10, b=10),
                                       showlegend=False)
                    st.plotly_chart(fig, width="stretch")

                # ---- Status × Class stacked bar ----
                st.markdown("**상태별 척수 (Class 누적)**")
                fig = px.bar(mat, x="vessel_class", y="n",
                              color="status",
                              category_orders={"status": status_order},
                              color_discrete_map=_UTIL_PALETTE,
                              labels={"vessel_class": "", "n": "척수"})
                fig.update_layout(height=360, margin=dict(t=10, b=10),
                                   barmode="stack",
                                   legend=dict(orientation="h", y=-0.2,
                                                font=dict(size=10)))
                st.plotly_chart(fig, width="stretch")

                # ---- High-value idle list ----
                st.markdown("##### 💎 고가치 유휴 화물선 Top 30 (GT 큰 순)")
                idle_top = (uview[uview["status"] == "Idle (<25%)"]
                                .dropna(subset=["gt"])
                                .sort_values("gt", ascending=False)
                                .head(30))
                if idle_top.empty:
                    st.info("Idle 분류 선박 없음")
                else:
                    show_cols = ["nama_kapal", "vessel_class",
                                  "tanker_subclass", "nama_pemilik",
                                  "bendera", "gt", "tahun", "age",
                                  "months_active", "total_ton", "util_pct"]
                    show_cols = [c for c in show_cols
                                    if c in idle_top.columns]
                    theme.dataframe(idle_top[show_cols])
                    util_export_cols = show_cols + ["status"]
                    util_export_cols = [c for c in util_export_cols
                                            if c in uview.columns]
                    _csv_button(uview[util_export_cols],
                                 f"cargo_vessel_utilization_{snapshot}.csv",
                                 label="📥 가동률 전체 CSV",
                                 key="ft_dl_util")

    # ============ 5) Sortable list ============
    with sub_list:
        st.markdown("**선박 리스트** — 컬럼 헤더 클릭으로 정렬, 검색/CSV 다운로드 지원")
        cA, cB = st.columns([1, 1])
        with cA:
            sort_col = st.selectbox(
                "정렬 기준",
                ["gt", "age", "tahun_num", "nama_kapal", "nama_pemilik"],
                key="ft_sort_col",
            )
        with cB:
            sort_dir = st.radio(
                "정렬 방향", ["내림차순", "오름차순"], horizontal=True,
                key="ft_sort_dir",
            )

        ascending = sort_dir == "오름차순"
        if sort_col in fdf.columns:
            tbl = fdf.sort_values(sort_col, ascending=ascending,
                                    na_position="last")
        else:
            tbl = fdf

        display_cols = [
            "nama_kapal", "vessel_class", "tanker_subclass", "jenis_detail",
            "nama_pemilik", "bendera", "gt", "loa", "lebar", "dalam",
            "tahun", "age", "age_bucket", "imo", "call_sign",
            "pelabuhan_pendaftaran", "search_code", "vessel_key",
        ]
        display_cols = [c for c in display_cols if c in tbl.columns]
        tbl_show = tbl[display_cols].head(3000)
        st.caption(f"표시 {len(tbl_show):,} / 필터 {len(fdf):,} rows (최대 3,000)")
        theme.dataframe(tbl_show)
        _csv_button(fdf[display_cols], f"cargo_fleet_{snapshot}.csv",
                     label="📥 화물선 리스트 CSV (필터 전체)",
                     key="ft_csv_full")


# ------------------------- Tanker Focus page -------------------------

# Stable subclass color palette (consistent across charts).
_TANKER_PALETTE = {
    "Crude Oil":             "#0f172a",  # near-black
    "Product":               "#1e40af",  # blue
    "Chemical":              "#7c3aed",  # purple
    "LPG":                   "#f59e0b",  # amber
    "LNG":                   "#0891b2",  # cyan
    "FAME / Vegetable Oil":  "#16a34a",  # green
    "Water":                 "#0ea5e9",  # sky
    "UNKNOWN":               "#9ca3af",  # gray
}


# Fleet age buckets and approximate newbuild $/GT by tanker subclass.
# Industry rule-of-thumb numbers — accurate within ±30% but useful as a
# replacement-cost magnitude proxy. LNG/LPG carriers have specialised
# cryogenic systems → much higher $/GT. Don't use for valuation; for
# sizing the replacement opportunity.
_AGE_BUCKETS = (
    ("Newbuild (<5y)",     0,  5,  "#16a34a"),
    ("Modern (5-15y)",     5, 15,  "#0891b2"),
    ("Aging (15-25y)",    15, 25,  "#f59e0b"),
    ("Retirement (>25y)", 25, 99,  "#dc2626"),
)
_NEWBUILD_USD_PER_GT = {
    "Crude Oil":            1_800,
    "Product":              2_300,
    "Chemical":             3_000,
    "LPG":                  4_000,
    "LNG":                  5_500,
    "FAME / Vegetable Oil": 2_300,
    "Water":                1_500,
    "UNKNOWN":              2_000,
}


def _bucket_for_age(age: float | None) -> str | None:
    if age is None or pd.isna(age) or age < 0:
        return None
    for label, lo, hi, _color in _AGE_BUCKETS:
        if lo <= age < hi:
            return label
    return _AGE_BUCKETS[-1][0]  # >=25 falls into Retirement


# Approximate (lat, lon) for the top ~80 most-active Indonesian tanker ports.
# Picked manually from public geographic knowledge — accurate to ~1 km, which
# is plenty for a country-level archipelago map. Ports not in this lookup
# render as a "(좌표 미보유)" tail in the missing-coords table.
_PORT_COORDS: dict[str, tuple[float, float]] = {
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
    "IDLMA": (-1.13, 116.92),  # Lawe-Lawe Pertamina (Balikpapan area)
}


# Freeform LK3 origin/destination text → (lat, lon). Names that don't appear
# in `ports.nama_pelabuhan` (special terminals, jetties, foreign ports). Set
# to None for known foreign hubs so the lookup can mark them "international".
_PORT_NAME_ALIASES: dict[str, tuple[float, float] | None] = {
    # ---------- Foreign hubs (off-map; tagged "international") ----------
    "SINGAPORE":          None,
    "PORT KLANG":         None,
    "PASIR GUDANG":       None,
    "JOHOR":              None,
    "TANJUNG PELEPAS":    None,
    "TANJONG BIN":        None,
    "MALAYSIA":           None,
    "MELAKA":             None,
    "PENGERANG":          None,
    "MAP TA PHUT":        None,
    "SRIRACHA":           None,
    "KAOHSIUNG":          None,
    "HONG KONG":          None,
    "ZHOUSHAN":           None,
    "ZHOUSHAN PT":        None,
    "XIUYU":              None,
    "XIUYU PT":           None,
    "YEOSU":              None,
    "BUSAN":              None,
    "MUHAMMAD BIN QASIM": None,
    "CHATTOGRAM":         None,
    "CHITTAGONG":         None,
    "OFFSHORE FUJAIRAH":  None,
    "FUJAIRAH":           None,
    "RAS TANURA":         None,
    "PORT LOUIS":         None,
    "FREEPORT":           None,
    "HOUSTON":            None,
    "NEDERLAND":          None,
    "ROTTERDAM":          None,
    "BAA":                None,
    "SOYO":               None,
    "RAS LAFFAN":         None,
    "DAMPIER":            None,
    "HALDIA":             None,
    "SOHAR":              None,
    "RUWAIS":             None,
    "RUWAIS PORT":        None,
    "DAVAO":              None,
    "GIRASSOL":           None,
    "DOHA":               None,
    "JEBEL ALI":           None,
    # ---------- Indonesian terminals not in ports.nama_pelabuhan ----------
    "MARUNDA":            (-6.10, 106.96),
    "MUARA BARU":         (-6.10, 106.81),
    "TANJUNG SEKONG":     (-5.98, 106.05),
    "TANJUNG GEREM":      (-5.95, 106.05),
    "MERAK":              (-5.93, 106.00),
    "CILEGON":            (-5.98, 106.05),
    "ANYER":              (-6.06, 105.93),
    "KABIL":              (1.06, 104.10),
    "WAYAME":             (-3.62, 128.13),
    "BLANG LANCANG":      (5.18, 97.15),
    "PLAJU":              (-3.00, 104.78),
    "TUBAN":              (-6.90, 112.05),
    "TUBAN TUKS PERTAMINA": (-6.90, 112.05),
    "BALONGAN":           (-6.32, 108.39),
    "BALONGAN TERMINAL":  (-6.32, 108.39),
    "AMPENAN":            (-8.57, 116.08),
    "TUA PEJAT":          (-2.07, 99.59),
    "BOOM BARU":          (-2.99, 104.76),
    "TELUK KABUNG":       (-1.05, 100.41),
    "TELUK SEMANGKA":     (-5.85, 104.65),
    "TELUK JAKARTA":      (-6.10, 106.88),
    "BAU-BAU":            (-5.47, 122.62),
    "MALINAU":            (3.59, 116.65),
    "TANJUNG MANGGIS":    (-8.57, 115.55),
    "TELUK BAYUR":        (-1.00, 100.37),
    "TANJUNG WANGI":      (-8.21, 114.37),
    "JAKARTA":            (-6.12, 106.88),
    "TG. PRIOK":          (-6.10, 106.88),
    "PRIOK":              (-6.10, 106.88),
    "SEMARANG":           (-6.96, 110.42),
    "SURABAYA":           (-7.20, 112.74),
    "SEMAMPIR":           (-7.20, 112.74),
    "PADANG":             (-1.00, 100.37),
    "MEDAN":              (3.78, 98.69),
    "LHOKSEUMAWE":        (5.18, 97.15),
    "BANGKA":             (-2.10, 106.13),
    "PANGKAL BALAM":      (-2.10, 106.13),
    "TANJUNG REDEP":      (2.15, 117.50),
    "KAMPUNG BARU":       (-1.27, 116.83),
    "BANJARMASIN":        (-3.32, 114.59),
    "KOTABARU":           (-3.30, 116.20),
    "KALBUT":             (-7.74, 113.86),
    "KALBUT SITUBONDO":   (-7.74, 113.86),
    "TARAHAN":            (-5.55, 105.36),
    "TARJUN":             (-3.65, 116.04),
    "CINTA":              (-5.95, 106.20),  # offshore Java Sea
    "ARJUNA":             (-5.95, 107.50),  # offshore Java Sea
    "SUNGAI PAKNING":     (1.39, 102.13),
    "KENDAWANGAN":        (-2.55, 110.21),
    "MEKAR PUTIH":        (-8.59, 116.43),
    "MOROWALI":           (-2.85, 121.85),
    "LAWE-LAWE":          (-1.13, 116.92),
    "PATIMBAN":           (-6.31, 107.91),
    "TANAH GROGOT":       (-1.91, 116.20),
    "JABUNG TERMINAL":    (-1.10, 104.30),
    "JABUNG":             (-1.10, 104.30),
    "TANJUNG BARA":       (-0.42, 117.55),
    "BUKIT TUA":          (-6.27, 113.20),  # offshore East Java
    "POLEKO":             (-3.97, 122.52),  # Kendari area
    "PT. TIMAH":          (-2.10, 106.13),
    "SENIPAH":            (-0.95, 117.00),  # Senipah Oil Terminal
    "PULANG PISAU":       (-2.74, 114.07),
    "SAMPIT":             (-2.54, 112.94),
    "BATULICIN":          (-3.30, 116.20),
    "MUARA SATUI":        (-3.85, 115.50),
    "BUNGUS":             (-1.05, 100.41),
    "TANJUNG BUTON":      (1.07, 102.30),
}


# Terminal/operator keywords that, when found mid-string, signal the rest is
# a corporate suffix and should be stripped. Order matters: longest-first so
# "TUKS PT" doesn't truncate to "TUKS".
_TERMINAL_KW_TAILS = (
    "TUKS PT", "TUKS PERTAMINA", "TUKS",
    "TERSUS PT", "TERSUS PERTAMINA", "TERSUS",
    "STS PERTAMINA", "STS PT", "STS",
    "PT. PERTAMINA", "PT PERTAMINA", "PERTAMINA",
    "TERMINAL KHUSUS", "TERMINAL", "JV",
)


def _normalize_port_name(s) -> str | None:
    """Strip LK3 suffixes from freeform port name, return uppercase clean.

    Examples:
      "BALIKPAPAN/TUKS PT. PERTAMINA" → "BALIKPAPAN"
      "TANJUNG SEKONG, JV"            → "TANJUNG SEKONG"
      "MAKASSAR (BARRU)"              → "MAKASSAR"
      "TUBAN TUKS PERTAMINA"          → "TUBAN"
      "PANJANG/TUKS PERTAMINA"        → "PANJANG"
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    t = str(s).upper().strip()
    if not t:
        return None
    # Strip parenthetical / slash / comma suffixes
    t = t.split("(", 1)[0].strip()
    t = t.split("/", 1)[0].strip()
    t = t.split(",", 1)[0].strip()
    # Strip terminal-keyword tails ("TUKS ...", "PERTAMINA ...", etc.)
    for kw in _TERMINAL_KW_TAILS:
        idx = t.find(" " + kw)
        if idx > 0:
            t = t[:idx].strip()
    return t if len(t) >= 3 else None


@st.cache_data(ttl=3600)
def _port_name_to_coords() -> tuple[dict[str, tuple[float, float]], set[str]]:
    """Build a name (uppercase, stripped) → (lat, lon) lookup.

    Returns (coord_map, foreign_set). Foreign set holds normalized names of
    known foreign hubs so callers can tag international flows separately.
    """
    out: dict[str, tuple[float, float]] = {}
    foreign: set[str] = set()
    try:
        ports = q.ports()
    except Exception:
        ports = pd.DataFrame()
    for r in ports.itertuples(index=False):
        coord = _PORT_COORDS.get(getattr(r, "kode_pelabuhan", None))
        nm = getattr(r, "nama_pelabuhan", None)
        if coord and nm:
            key = _normalize_port_name(nm)
            if key:
                out[key] = coord
    for k, v in _PORT_NAME_ALIASES.items():
        if v is None:
            foreign.add(k)
        else:
            out[k] = v
    return out, foreign


def _resolve_port_coord(
    name, coord_map: dict[str, tuple[float, float]], foreign: set[str]
) -> tuple[tuple[float, float] | None, str]:
    """Return ((lat, lon) or None, status) where status ∈ {ok, foreign, unknown, empty}."""
    key = _normalize_port_name(name)
    if not key:
        return None, "empty"
    if key in coord_map:
        return coord_map[key], "ok"
    if key in foreign:
        return None, "foreign"
    return None, "unknown"


_UTIL_PALETTE = {
    "Idle (<25%)":       "#dc2626",
    "Light (25–50%)":    "#f59e0b",
    "Active (50–75%)":   "#0891b2",
    "Heavy (≥75%)":      "#16a34a",
}


def _fleet_utilization_view(sub_sel: str = "전체") -> None:
    """Per-vessel LK3 activity intensity over the 24mo window.

    Surfaces idle high-GT tankers — investment / charter targets.
    """
    st.subheader("선박별 가동률 (24개월 LK3 활동 기준)")
    with st.spinner("선박-cargo 매칭 중…"):
        u = _vessel_utilization(snapshot)
    if u.empty:
        st.info("가동률 데이터가 없습니다.")
        return

    # Filter by subclass to match the fleet view's selector
    if sub_sel != "전체" and "tanker_subclass" in u.columns:
        u = u[u["tanker_subclass"] == sub_sel]
    if u.empty:
        st.warning(f"'{sub_sel}' 분류에서 가동률 분석 가능한 선박 없음")
        return

    n = len(u)
    n_idle = int((u["status"] == "Idle (<25%)").sum())
    n_heavy = int((u["status"] == "Heavy (≥75%)").sum())
    idle_gt = float(pd.to_numeric(u.loc[u["status"] == "Idle (<25%)", "gt"],
                                    errors="coerce").fillna(0).sum())

    cols = st.columns(5)
    kpi(cols[0], "분석 선박", fmt.fmt_int(n),
        help="현재 subclass 필터에 해당하는 등기 탱커")
    kpi(cols[1], "Idle 선박", fmt.fmt_int(n_idle),
        help="24개월 중 < 6개월만 활동 — 매물/차터 후보")
    kpi(cols[2], "Idle 비율", fmt.fmt_pct(n_idle / n * 100))
    kpi(cols[3], "Idle 총 GT", fmt.fmt_gt(idle_gt),
        help="유휴 선대의 총 GT — 자본 매몰 규모")
    kpi(cols[4], "Heavy 선박", fmt.fmt_int(n_heavy),
        help="24개월 중 ≥ 18개월 활동 — 핵심 운영 자산")

    st.caption(
        "**매칭 방법**: 등기 fleet의 `nama_kapal`을 LK3의 `KAPAL` 필드와 "
        "대문자 일치로 매칭. 동명 / 표기 차이 false negative 가능. "
        "**활용**: 'Idle' = 외국 운항 중이거나 진짜 유휴 — 차터-인 / 매수 후보."
    )

    # ---- status pie + util_pct distribution ----
    cA, cB = st.columns([1, 2])
    with cA:
        status_dist = u["status"].value_counts().reset_index()
        status_dist.columns = ["status", "count"]
        fig = px.pie(status_dist, names="status", values="count",
                     color="status", color_discrete_map=_UTIL_PALETTE,
                     hole=0.5,
                     category_orders={"status": list(_UTIL_PALETTE.keys())})
        fig.update_traces(textinfo="percent+label", textposition="outside")
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          legend=dict(font=dict(size=10)))
        theme.donut_center(fig, fmt.fmt_int(int(status_dist["count"].sum())),
                           "분석 선박")
        st.plotly_chart(fig, width="stretch")
    with cB:
        fig = px.histogram(u, x="util_pct", nbins=24,
                           color="status",
                           color_discrete_map=_UTIL_PALETTE,
                           category_orders={"status": list(_UTIL_PALETTE.keys())},
                           labels={"util_pct": "가동률 (%)",
                                   "count": "선박 수"})
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          legend=dict(orientation="h", y=-0.2,
                                      font=dict(size=10)))
        st.plotly_chart(fig, width="stretch")

    # ---- High-value idle list (the goldmine) ----
    st.markdown("##### 💎 고가치 유휴 탱커 Top 30 (GT 큰 순)")
    idle = u[u["status"] == "Idle (<25%)"].copy()
    idle = idle.dropna(subset=["gt"]).sort_values("gt", ascending=False).head(30)
    if idle.empty:
        st.info("Idle 분류 선박 없음")
    else:
        cur_yr = int(snapshot[:4])
        idle["age"] = cur_yr - pd.to_numeric(idle["tahun"], errors="coerce")
        cols_show = ["nama_kapal", "tanker_subclass", "nama_pemilik",
                     "bendera", "gt", "tahun", "age",
                     "months_active", "total_ton", "util_pct"]
        cols_show = [c for c in cols_show if c in idle.columns]
        theme.dataframe(idle[cols_show])
        _csv_button(u[cols_show + ["status"]] if all(c in u.columns for c in cols_show)
                    else u, f"vessel_utilization_{snapshot}.csv",
                    label="📥 가동률 전체 CSV", key="tk_dl_util")

    # ---- subclass × status heatmap ----
    if "tanker_subclass" in u.columns:
        st.markdown("##### Subclass × 가동률 분포 (척수)")
        mat = u.groupby(["tanker_subclass", "status"]).size().reset_index(name="n")
        pivot = mat.pivot_table(index="tanker_subclass", columns="status",
                                 values="n", fill_value=0)
        pivot = pivot.reindex(columns=[s for s in _UTIL_PALETTE.keys()
                                          if s in pivot.columns])
        fig = px.imshow(pivot, text_auto=True, aspect="auto",
                        color_continuous_scale=theme.SCALES["blue"],
                        labels=dict(color="척수"))
        fig.update_layout(height=300, margin=dict(t=20, b=10))
        st.plotly_chart(fig, width="stretch")


def _age_activity_correlation_view(sub_sel: str = "전체") -> None:
    """🔬 Vessel age vs LK3 months_active scatter + regression.

    Quantifies the iter #18 thesis: do older tankers really idle more?
    Pearson r near -1 = strong "older = more idle" pattern. Near 0 = no
    relationship (suggesting idleness is owner-driven, not age-driven).
    """
    import numpy as np

    st.subheader("🔬 선령 vs 가동률 상관관계")

    u = _vessel_utilization(snapshot)
    if u.empty:
        st.info("상관관계 분석할 데이터 없음")
        return

    # Filter by subclass
    if sub_sel != "전체" and "tanker_subclass" in u.columns:
        u = u[u["tanker_subclass"] == sub_sel]
    if u.empty:
        st.warning(f"'{sub_sel}' 분류에서 분석 가능한 선박 없음")
        return

    cur_yr = int(snapshot[:4])
    yrs = pd.to_numeric(u["tahun"], errors="coerce")
    age = (cur_yr - yrs).where(cur_yr - yrs >= 0)
    df = u.assign(age=age, months_active=u["months_active"].astype(float))
    df = df.dropna(subset=["age", "months_active"])
    df = df[df["age"] <= 60]  # exclude implausibly old (data quality)

    if len(df) < 30:
        st.info(f"데이터 부족 (n={len(df)} < 30)")
        return

    # Pearson correlation
    r = float(df["age"].corr(df["months_active"]))
    n = len(df)

    # Linear regression: months_active = a × age + b
    x = df["age"].to_numpy(dtype=float)
    y = df["months_active"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)

    # Bucket means: avg months_active per age bucket
    bucket_edges = [0, 5, 10, 15, 20, 25, 30, 40, 60]
    bucket_labels = ["0-5", "5-10", "10-15", "15-20", "20-25",
                     "25-30", "30-40", "40+"]
    df["age_bucket"] = pd.cut(df["age"], bins=bucket_edges,
                                labels=bucket_labels, right=False)
    bucket_means = (df.groupby("age_bucket", observed=True)
                       .agg(n=("vessel_key", "count"),
                            avg_months=("months_active", "mean"),
                            avg_util=("util_pct", "mean"))
                       .reset_index())

    # ---- KPI ----
    cols = st.columns(4)
    kpi(cols[0], "분석 선박", fmt.fmt_int(n))
    band = ("강한 음의 상관" if r <= -0.3 else "약한 음의 상관" if r < -0.1
            else "무상관" if abs(r) <= 0.1 else "약한 양의 상관" if r < 0.3
            else "강한 양의 상관")
    kpi(cols[1], "Pearson r",
        f"{r:.3f} ({band})",
        help="age와 months_active 상관계수. -1 → '나이↑ 가동↓' 강함, 0 → 무관계")
    kpi(cols[2], "회귀 기울기",
        f"{slope:.3f} 개월/년",
        help="age 1년 늘어날 때 months_active 변화. 음수 = 노후화 → idle 추세")
    kpi(cols[3], "0년 기준 가동",
        f"{intercept:.1f} 개월",
        help="회귀선 절편 — 신조 탱커 가정 가동 (24개월 중)")

    st.caption(
        f"**투자 의미**: r={r:.2f}. "
        + (
            f"강한 음의 상관 → 노후 fleet 매수 후 신조 대체 매력 ↑ (한국 조선소 장점). "
            if r <= -0.3 else
            f"약한 상관 → 가동률은 owner 정책/operator 차터 구조의 함수, "
            "단순 노후 → idle 가정 부적절. 운영사 별 deep-dive 권장."
            if abs(r) < 0.3 else
            f"양의 상관 (예상 외) → 노후선이 오히려 더 많이 운항. "
            "확인 필요 — 노후선이 STS / 단거리 inter-island 전용 가능성."
        )
    )

    # ---- Scatter + bucket means ----
    cA, cB = st.columns([3, 2])
    with cA:
        st.markdown("##### 산점도 (Plotly OLS trendline)")
        fig = px.scatter(
            df, x="age", y="months_active",
            color="tanker_subclass",
            color_discrete_map=_TANKER_PALETTE,
            opacity=0.5,
            trendline="ols",
            trendline_scope="overall",
            hover_data=["nama_kapal", "nama_pemilik", "gt", "tahun"],
            labels={"age": "선령 (년)",
                    "months_active": "활동 개월 (24개월 중)",
                    "tanker_subclass": "Subclass"},
        )
        fig.update_layout(height=460, margin=dict(t=10, b=10),
                          legend=dict(orientation="h", y=-0.2,
                                      font=dict(size=10)))
        st.plotly_chart(fig, width="stretch")
    with cB:
        st.markdown("##### 선령 버킷별 평균 가동")
        if not bucket_means.empty:
            fig = px.bar(bucket_means, x="age_bucket", y="avg_months",
                         color="avg_months",
                         color_continuous_scale=theme.SCALES["diverging"],
                         color_continuous_midpoint=12,
                         hover_data=["n", "avg_util"],
                         labels={"age_bucket": "선령 (년)",
                                 "avg_months": "평균 활동 개월"})
            fig.update_layout(height=320, margin=dict(t=10, b=10),
                              coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")
            bucket_means["avg_util"] = bucket_means["avg_util"].round(1)
            bucket_means["avg_months"] = bucket_means["avg_months"].round(1)
            theme.dataframe(bucket_means)


def _fleet_aging_buckets_view(fdf: pd.DataFrame, cur_yr: int) -> None:
    """Render the 4-bucket aging table + $/GT replacement-cost proxy."""
    st.subheader("선령 버킷 + 대체가치 추정")
    yrs = pd.to_numeric(fdf["tahun"], errors="coerce")
    age = (cur_yr - yrs).where(cur_yr - yrs >= 0)
    bdf = fdf.assign(
        age=age,
        bucket=age.map(_bucket_for_age),
        gt_num=pd.to_numeric(fdf["gt"], errors="coerce").fillna(0),
        usd_per_gt=fdf.get("tanker_subclass",
                             pd.Series(["UNKNOWN"] * len(fdf))).map(
            lambda s: _NEWBUILD_USD_PER_GT.get(s, _NEWBUILD_USD_PER_GT["UNKNOWN"])),
    )
    bdf["replacement_usd"] = bdf["gt_num"] * bdf["usd_per_gt"]

    # Order buckets large-age last (presentation)
    order = [b[0] for b in _AGE_BUCKETS]
    grp = (bdf.dropna(subset=["bucket"])
              .groupby("bucket")
              .agg(척수=("vessel_key", "count"),
                   총_GT=("gt_num", "sum"),
                   평균_GT=("gt_num", "mean"),
                   대체가_USD=("replacement_usd", "sum"))
              .reindex(order).reset_index())
    grp["척수"] = grp["척수"].fillna(0).astype(int)
    grp["총_GT"] = grp["총_GT"].fillna(0)
    grp["평균_GT"] = grp["평균_GT"].fillna(0)
    grp["대체가_USD"] = grp["대체가_USD"].fillna(0)
    grp["GT_점유율_%"] = (grp["총_GT"] / max(grp["총_GT"].sum(), 1) * 100).round(1)

    color_map = {b[0]: b[3] for b in _AGE_BUCKETS}
    n_known = int(bdf["bucket"].notna().sum())

    # ---- KPI row: total fleet count + total replacement value ----
    total_repl = float(grp["대체가_USD"].sum())
    retirement_repl = float(grp.loc[grp["bucket"] == "Retirement (>25y)",
                                       "대체가_USD"].sum())
    aging_repl = float(grp.loc[grp["bucket"].isin(["Aging (15-25y)",
                                                       "Retirement (>25y)"]),
                                  "대체가_USD"].sum())
    cols = st.columns(4)
    kpi(cols[0], "분류된 척수", fmt.fmt_int(n_known),
        help="건조연도 결측 제외")
    kpi(cols[1], "총 대체가 추정",
        f"${total_repl/1e9:.2f}B",
        help="모든 탱커 GT × subclass별 newbuild $/GT 합. ±30% 정확도")
    kpi(cols[2], "Retirement 대체가",
        f"${retirement_repl/1e9:.2f}B",
        help="25년+ 탱커만 — 향후 5-10년 내 대체 압력")
    kpi(cols[3], "Aging+Retirement",
        f"${aging_repl/1e9:.2f}B",
        help="15년+ 누적 — 인도네시아 탱커 시장 잠재 발주 풀")

    # ---- bucket table + bar chart ----
    c1, c2 = st.columns([1, 1])
    with c1:
        fig = px.bar(grp, x="bucket", y="척수",
                     color="bucket", color_discrete_map=color_map,
                     category_orders={"bucket": order},
                     labels={"bucket": "버킷", "척수": "척수"})
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with c2:
        # USD value bar
        grp_disp = grp.assign(대체가_B=grp["대체가_USD"] / 1e9)
        fig = px.bar(grp_disp, x="bucket", y="대체가_B",
                     color="bucket", color_discrete_map=color_map,
                     category_orders={"bucket": order},
                     labels={"bucket": "버킷", "대체가_B": "대체가 (B USD)"})
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          showlegend=False)
        st.plotly_chart(fig, width="stretch")

    grp_show = grp.copy()
    grp_show["총_GT"] = grp_show["총_GT"].round(0)
    grp_show["평균_GT"] = grp_show["평균_GT"].round(0)
    grp_show["대체가_B_USD"] = (grp_show["대체가_USD"] / 1e9).round(2)
    grp_show = grp_show.drop(columns="대체가_USD")
    theme.dataframe(grp_show)
    _csv_button(grp_show, f"tanker_aging_buckets_{snapshot}.csv",
                key="tk_dl_aging")

    # ---- bucket × subclass heatmap (replacement value) ----
    st.markdown("##### 버킷 × 세부 분류 매트릭스 (대체가, B USD)")
    if "tanker_subclass" in bdf.columns:
        mat = (bdf.dropna(subset=["bucket"])
                  .groupby(["bucket", "tanker_subclass"])["replacement_usd"]
                  .sum().reset_index())
        pivot = mat.pivot(index="tanker_subclass",
                          columns="bucket",
                          values="replacement_usd").fillna(0) / 1e9
        pivot = pivot.reindex(columns=[b for b in order if b in pivot.columns])
        if not pivot.empty:
            fig = px.imshow(pivot.round(2), text_auto=".2f",
                            aspect="auto",
                            color_continuous_scale=theme.SCALES["red"],
                            labels=dict(color="B USD"))
            fig.update_layout(height=340, margin=dict(t=20, b=10))
            st.plotly_chart(fig, width="stretch")
        st.caption(
            "$/GT 단가는 subclass별 newbuild 시세 추정치 "
            "(Crude $1.8k / Product $2.3k / Chemical $3.0k / LPG $4.0k / "
            "LNG $5.5k / FAME $2.3k). 발주처·연도·환율 변동 시 ±30% 차이. "
            "투자 사이즈 잡기용 magnitude 지표 — 정확한 valuation은 별도."
        )


def _hhi(shares: pd.Series) -> float:
    """Herfindahl-Hirschman Index in [0, 10000].

    `shares` is a Series of *percent* shares (0-100). HHI < 1500 = low
    concentration, 1500–2500 = moderate, > 2500 = high.
    """
    s = pd.to_numeric(shares, errors="coerce").dropna()
    return float((s ** 2).sum())


def page_tanker():
    st.title("🛢️ Tanker Focus")
    st.caption(
        f"Snapshot: **{snapshot}** · 인도네시아 탱커 선대 + 화물 흐름 분석"
    )

    # Brief export (top-right — generates a one-page Markdown summary)
    cBrief1, cBrief2 = st.columns([3, 1])
    with cBrief2:
        if st.button("📄 Brief 생성", help="모든 sub-tab 핵심 시그널을 1-페이지 MD로 다운로드",
                      key="tk_brief_btn", width="stretch"):
            with st.spinner("Brief 작성 중…"):
                md = _build_tanker_brief_md()
            st.session_state["tk_brief_md"] = md
        if "tk_brief_md" in st.session_state:
            st.download_button(
                "📥 Tanker Sector Brief (.md)",
                st.session_state["tk_brief_md"].encode("utf-8"),
                file_name=f"tanker_sector_brief_{snapshot}.md",
                mime="text/markdown",
                key="tk_brief_dl", width="stretch",
            )

    _tanker_thesis_card()

    tab_fleet, tab_flow, tab_port, tab_op, tab_inv, tab_trend, tab_search = st.tabs(
        ["🛳️ 선대 분석", "🌊 화물 흐름", "🏗️ 항구 경쟁력",
         "🏢 운영사 / 소유주", "💰 투자 시그널", "📈 트렌드", "🔎 선박 검색"])
    with tab_fleet:
        _tanker_fleet_view()
    with tab_flow:
        _tanker_flow_view()
    with tab_port:
        _tanker_port_view()
    with tab_op:
        _tanker_operator_view()
    with tab_inv:
        _tanker_investment_view()
    with tab_trend:
        _tanker_trend_view()
    with tab_search:
        _tanker_search_view()


def _build_tanker_brief_md() -> str:
    """Generate a Markdown 'Tanker Sector Brief' consolidating sub-tab signals.

    Pulls from the cached extracts (no extra DB cost beyond what's already
    been computed by the Streamlit cache layer this session).
    """
    from datetime import datetime as _dt
    fleet = _tankers_full(snapshot)
    flows = _tanker_cargo_flows(snapshot)

    if fleet.empty and flows.empty:
        return f"# Tanker Sector Brief — {snapshot}\n\n_데이터 없음_\n"

    lines: list[str] = []
    push = lines.append
    push(f"# 🛢️ Tanker Sector Brief — {snapshot}")
    push("")
    push(f"_Generated: {_dt.now().strftime('%Y-%m-%d %H:%M')} KST_  ")
    push("_Source: kapal.dephub.go.id (fleet) + monitoring-inaportnet.dephub.go.id (LK3)_")
    push("")
    push("---")
    push("")

    # ===================== Executive Summary =====================
    push("## 🎯 Executive Summary (auto-derived)")
    push("")
    flows_sig = flows.assign(
        op_norm=flows["operator"].map(_norm_company),
        ton_total=(pd.to_numeric(flows["bongkar_ton"], errors="coerce").fillna(0)
                    + pd.to_numeric(flows["muat_ton"], errors="coerce").fillna(0)),
    )
    op_ton = (flows_sig.dropna(subset=["op_norm"])
                       .groupby("op_norm")["ton_total"].sum()
                       .sort_values(ascending=False))
    op_total = float(op_ton.sum()) if not op_ton.empty else 0
    if not op_ton.empty:
        push(f"1. **시장 지배 운영사**: `{op_ton.index[0]}` — "
             f"점유율 **{op_ton.iloc[0]/op_total*100:.1f}%** "
             f"({fmt.fmt_compact(op_ton.iloc[0])} 톤)")

    # Fastest YoY OD pair
    periods = sorted(flows_sig["period"].dropna().unique())
    half = min(12, len(periods) // 2)
    if len(periods) >= 4 and half >= 2:
        latest = set(periods[-half:])
        prior = set(periods[-2 * half:-half])
        od = flows_sig[(flows_sig["origin"] != flows_sig["destination"])
                         & flows_sig["origin"].notna()
                         & flows_sig["destination"].notna()].copy()
        od["side"] = od["period"].map(
            lambda p: "latest" if p in latest else ("prior" if p in prior else None))
        agg = (od.dropna(subset=["side"])
                  .groupby(["origin", "destination", "side"])["ton_total"].sum()
                  .unstack(fill_value=0).reset_index())
        if "latest" not in agg.columns: agg["latest"] = 0
        if "prior" not in agg.columns: agg["prior"] = 0
        agg = agg[(agg["prior"] >= 50_000) & (agg["latest"] > 0)]
        agg["delta"] = agg["latest"] - agg["prior"]
        if not agg.empty:
            top_g = agg.sort_values("delta", ascending=False).iloc[0]
            growth_pct = (top_g["latest"] / top_g["prior"] - 1) * 100
            push(f"2. **최대 성장 항로 (YoY)**: `{top_g['origin']}` → "
                 f"`{top_g['destination']}` "
                 f"`+{fmt.fmt_compact(top_g['delta'])}` 톤 "
                 f"(**{growth_pct:+.0f}%**)")

    # Aged-25 retirement count
    cur_yr = int(snapshot[:4])
    yrs = pd.to_numeric(fleet["tahun"], errors="coerce")
    age = cur_yr - yrs
    aged25 = (age >= 25)
    aged_count = int(aged25.sum())
    aged_gt = float(pd.to_numeric(fleet.loc[aged25, "gt"], errors="coerce")
                      .fillna(0).sum())
    aged_pct = aged_count / max(len(fleet), 1) * 100
    push(f"3. **25년+ 노후 선대**: {aged_count:,}척 "
         f"({fmt.fmt_gt(aged_gt)} · 전체 {aged_pct:.1f}%) — 대체 압력")

    # Top charter-out
    fleet_owner = (fleet.dropna(subset=["nama_pemilik"])
                          .assign(owner_norm=fleet["nama_pemilik"].map(_norm_company))
                          .groupby("owner_norm")
                          .agg(fleet_count=("vessel_key", "count"),
                               fleet_gt=("gt", lambda s: pd.to_numeric(s, errors="coerce")
                                                            .fillna(0).sum()))
                          .reset_index())
    op_active = op_ton.rename("op_ton").reset_index()
    cross = fleet_owner.merge(op_active, left_on="owner_norm",
                                right_on="op_norm", how="left").fillna(0)
    cross = cross[cross["fleet_count"] >= 3]
    if not cross.empty:
        top_chartered = cross.sort_values("fleet_gt", ascending=False).head(20)
        chartered = top_chartered.sort_values("op_ton").iloc[0]
        push(f"4. **차터아웃 시그널**: `{chartered['owner_norm']}` — "
             f"보유 {int(chartered['fleet_count'])}척 / {fmt.fmt_gt(chartered['fleet_gt'])}, "
             f"운영자로는 {fmt.fmt_compact(chartered['op_ton'])} 톤")

    push("")
    push("---")
    push("")

    # ===================== Fleet Snapshot =====================
    push("## 🛳️ 선대 분석")
    push("")
    sum_gt = float(pd.to_numeric(fleet["gt"], errors="coerce").fillna(0).sum())
    avg_age_v = float(age.where(age >= 0).mean()) if age.notna().any() else None
    push(f"- 탱커 척수: **{len(fleet):,}** | 총 GT: **{fmt.fmt_gt(sum_gt)}** | "
         f"평균 선령: **{avg_age_v:.1f} 년**" if avg_age_v else
         f"- 탱커 척수: **{len(fleet):,}** | 총 GT: **{fmt.fmt_gt(sum_gt)}**")

    push("")
    push("### 세부 분류 mix (척수)")
    push("")
    sub_dist = fleet["tanker_subclass"].value_counts()
    push("| Subclass | 척수 | 비중 |")
    push("|---|---:|---:|")
    for sub, cnt in sub_dist.items():
        push(f"| {sub} | {cnt:,} | {cnt/len(fleet)*100:.1f}% |")
    push("")

    # Aging buckets + replacement value
    age_known = age.where(age >= 0)
    bdf = fleet.assign(
        bucket=age_known.map(_bucket_for_age),
        gt_num=pd.to_numeric(fleet["gt"], errors="coerce").fillna(0),
        usd_per_gt=fleet["tanker_subclass"].map(
            lambda s: _NEWBUILD_USD_PER_GT.get(s, _NEWBUILD_USD_PER_GT["UNKNOWN"])),
    )
    bdf["replacement_usd"] = bdf["gt_num"] * bdf["usd_per_gt"]
    order = [b[0] for b in _AGE_BUCKETS]
    grp = (bdf.dropna(subset=["bucket"])
              .groupby("bucket").agg(
                  척수=("vessel_key", "count"),
                  총_GT=("gt_num", "sum"),
                  대체가_USD=("replacement_usd", "sum"))
              .reindex(order).fillna(0).reset_index())
    push("### 선령 버킷 + 대체가치")
    push("")
    push("| 버킷 | 척수 | 총 GT | 대체가 (B USD) |")
    push("|---|---:|---:|---:|")
    for r in grp.itertuples(index=False):
        push(f"| {r.bucket} | {int(r.척수):,} | {r.총_GT:,.0f} | "
             f"${r.대체가_USD/1e9:.2f}B |")
    total_repl = float(grp["대체가_USD"].sum()) / 1e9
    aging_repl = float(
        grp.loc[grp["bucket"].isin(["Aging (15-25y)", "Retirement (>25y)"]),
                  "대체가_USD"].sum()
    ) / 1e9
    push("")
    push(f"_총 대체가 추정: **${total_repl:.2f}B** · "
         f"Aging+Retirement (10-yr 대체 풀): **${aging_repl:.2f}B**_")
    push("")
    push("---")
    push("")

    # ===================== Cargo Flow =====================
    push("## 🌊 화물 흐름 (24개월)")
    push("")
    bton = pd.to_numeric(flows["bongkar_ton"], errors="coerce").fillna(0)
    mton = pd.to_numeric(flows["muat_ton"], errors="coerce").fillna(0)
    push(f"- LK3 행수: **{len(flows):,}** | "
         f"BONGKAR: **{fmt.fmt_ton(bton.sum())}** | "
         f"MUAT: **{fmt.fmt_ton(mton.sum())}**")
    push("")

    # Top 10 commodities (combined BONGKAR+MUAT)
    b_kom = flows[["bongkar_kom", "bongkar_ton"]].rename(
        columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
    m_kom = flows[["muat_kom", "muat_ton"]].rename(
        columns={"muat_kom": "kom", "muat_ton": "ton"})
    long = pd.concat([b_kom, m_kom], ignore_index=True).dropna(subset=["kom"])
    long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
    top_kom = (long.groupby("kom")["ton"].sum()
                   .sort_values(ascending=False).head(10))
    push("### Top 10 화물 (BONGKAR + MUAT)")
    push("")
    push("| 화물 | 톤 |")
    push("|---|---:|")
    for k, v in top_kom.items():
        push(f"| {k} | {fmt.fmt_compact(v, 1)} |")
    push("")

    # Top 10 OD pairs (excluding self-loops)
    od_self = (flows[(flows["origin"] != flows["destination"])
                       & flows["origin"].notna()
                       & flows["destination"].notna()]
                  .assign(ton=lambda d: pd.to_numeric(d["bongkar_ton"], errors="coerce").fillna(0)
                                          + pd.to_numeric(d["muat_ton"], errors="coerce").fillna(0))
                  .groupby(["origin", "destination"])["ton"].sum()
                  .sort_values(ascending=False).head(10))
    push("### Top 10 항로 (Origin → Destination)")
    push("")
    push("| 출발 | 도착 | 톤 |")
    push("|---|---|---:|")
    for (o, d), v in od_self.items():
        push(f"| {o} | {d} | {fmt.fmt_compact(v, 1)} |")
    push("")
    push("---")
    push("")

    # ===================== Port Competitiveness =====================
    push("## 🏗️ 항구 경쟁력")
    push("")
    flows_p = flows.assign(
        ton_total=bton + mton, loa=pd.to_numeric(flows["loa"], errors="coerce"),
        draft_max=pd.to_numeric(flows["draft_max"], errors="coerce"),
    )
    pgrp = (flows_p.groupby("kode_pelabuhan")
                   .agg(기항=("kapal", "size"),
                        고유_탱커=("kapal", "nunique"),
                        총_톤=("ton_total", "sum"),
                        Max_LOA=("loa", "max"),
                        Max_DRAFT=("draft_max", "max"))
                   .reset_index().sort_values("기항", ascending=False))
    push("### Top 10 항구 (기항수 기준)")
    push("")
    push("| 항구 | 기항 | 고유 탱커 | 총 톤 | Max LOA | Max DRAFT |")
    push("|---|---:|---:|---:|---:|---:|")
    for r in pgrp.head(10).itertuples(index=False):
        push(f"| {r.kode_pelabuhan} | {int(r.기항):,} | {int(r.고유_탱커):,} | "
             f"{fmt.fmt_compact(r.총_톤, 1)} | "
             f"{r.Max_LOA:.1f}m | {r.Max_DRAFT:.1f}m |")
    push("")
    # VLCC-capable port count
    vlcc_n = int((pgrp["Max_LOA"].fillna(0) >= 320).sum())
    push(f"_VLCC급 (≥ 320m LOA) 수용 항구: **{vlcc_n}** 개_")
    push("")
    push("---")
    push("")

    # ===================== Operator =====================
    push("## 🏢 운영사 / 소유주")
    push("")
    if not op_ton.empty:
        op_total_p = float(op_ton.sum())
        cr5 = float(op_ton.head(5).sum() / op_total_p * 100)
        cr10 = float(op_ton.head(10).sum() / op_total_p * 100)
        push(f"- 고유 운영사: **{len(op_ton):,}** | "
             f"CR5: **{cr5:.1f}%** | CR10: **{cr10:.1f}%**")
        push("")
        push("### Top 10 운영사 (총 톤)")
        push("")
        push("| 운영사 | 톤 | 점유율 |")
        push("|---|---:|---:|")
        for op_name, ton in op_ton.head(10).items():
            push(f"| {op_name} | {fmt.fmt_compact(ton, 1)} | "
                 f"{ton/op_total_p*100:.2f}% |")
        push("")
    push("---")
    push("")

    # ===================== Investment Signals =====================
    push("## 💰 투자 시그널")
    push("")
    flows_p["c_sub"] = flows_p["bongkar_kom"].where(
        flows_p["bongkar_ton"].fillna(0) > 0,
        flows_p["muat_kom"]).map(_kom_to_subclass)
    if half >= 2:
        sub_ton = (flows_p[flows_p["period"].isin(latest)]
                       .groupby("c_sub")["ton_total"].sum()
                       .rename("annual") * (12.0 / half))
    else:
        sub_ton = flows_p.groupby("c_sub")["ton_total"].sum().rename("annual")
    fleet_count = (fleet.groupby("tanker_subclass").size()
                          .rename("n").reset_index()
                          .rename(columns={"tanker_subclass": "c_sub"}))
    sp = sub_ton.reset_index().merge(fleet_count, on="c_sub", how="inner")
    sp = sp[sp["n"] > 0]
    sp["ton_per_vessel"] = sp["annual"] / sp["n"]
    sp = sp.sort_values("ton_per_vessel", ascending=False)
    push("### Subclass별 공급 압력")
    push("")
    push("| Subclass | Fleet (척) | 연 cargo (톤) | 톤/선/년 |")
    push("|---|---:|---:|---:|")
    for r in sp.itertuples(index=False):
        push(f"| {r.c_sub} | {int(r.n):,} | "
             f"{fmt.fmt_compact(r.annual, 1)} | "
             f"{fmt.fmt_compact(r.ton_per_vessel, 1)} |")
    push("")

    push("---")
    push("")
    push("_본 brief는 자동 생성된 magnitude 지표 모음입니다. "
         "실제 투자 결정은 해당 KAPAL/owner 별 due-diligence 필수._")
    push("")

    return "\n".join(lines)


def _tanker_thesis_card():
    """Auto-derived executive summary at the top of the Tanker page.

    Five scannable numeric signals an investor cares about for the snapshot.
    Computed live from the two cached extracts (no extra DB hits beyond the
    Streamlit cache layer).
    """
    fleet = _tankers_full(snapshot)
    flows = _tanker_cargo_flows(snapshot)
    if fleet.empty or flows.empty:
        return

    # ---- 1) Dominant operator + ton share ----
    flows_sig = flows.assign(
        op_norm=flows["operator"].map(_norm_company),
        ton_total=(pd.to_numeric(flows["bongkar_ton"], errors="coerce").fillna(0)
                   + pd.to_numeric(flows["muat_ton"], errors="coerce").fillna(0)),
    )
    op_ton = (flows_sig.dropna(subset=["op_norm"])
                       .groupby("op_norm")["ton_total"].sum()
                       .sort_values(ascending=False))
    if op_ton.empty:
        return
    op_total = float(op_ton.sum())
    top_op_name = op_ton.index[0]
    top_op_share = float(op_ton.iloc[0] / op_total * 100) if op_total else 0
    top_op_ton = float(op_ton.iloc[0])

    # ---- 2) Fastest-growing OD pair (YoY) ----
    periods = sorted(flows_sig["period"].dropna().unique())
    half = min(12, len(periods) // 2)
    growth_label = "-"
    growth_sub = "데이터 부족"
    if len(periods) >= 4 and half >= 2:
        latest = set(periods[-half:])
        prior = set(periods[-2 * half:-half])
        od = flows_sig[(flows_sig["origin"] != flows_sig["destination"])
                         & flows_sig["origin"].notna()
                         & flows_sig["destination"].notna()].copy()
        od["side"] = od["period"].map(
            lambda p: "latest" if p in latest else ("prior" if p in prior else None))
        agg = (od.dropna(subset=["side"])
                  .groupby(["origin", "destination", "side"])["ton_total"].sum()
                  .unstack(fill_value=0).reset_index())
        if "latest" not in agg.columns: agg["latest"] = 0
        if "prior" not in agg.columns: agg["prior"] = 0
        # Filter out single-shipment noise; require both sides with min volume.
        agg = agg[(agg["prior"] >= 50_000) & (agg["latest"] > 0)]
        agg["delta"] = agg["latest"] - agg["prior"]
        if not agg.empty:
            top_g = agg.sort_values("delta", ascending=False).iloc[0]
            growth_pct = (top_g["latest"] / top_g["prior"] - 1) * 100
            growth_label = f"{top_g['origin'][:14]} → {top_g['destination'][:14]}"
            growth_sub = (f"+{fmt.fmt_compact(top_g['delta'], 1)}t "
                          f"({fmt.fmt_pct(growth_pct, 0, signed=True)})")

    # ---- 3) Most supply-constrained subclass (highest cargo TON per fleet vessel) ----
    flows_sig["c_sub"] = flows_sig["bongkar_kom"].where(
        flows_sig["bongkar_ton"].fillna(0) > 0,
        flows_sig["muat_kom"]).map(_kom_to_subclass)
    if half >= 2:
        sub_ton = (flows_sig[flows_sig["period"].isin(latest)]
                     .groupby("c_sub")["ton_total"].sum()
                     .rename("annual_ton") * (12.0 / half))
    else:
        sub_ton = flows_sig.groupby("c_sub")["ton_total"].sum().rename("annual_ton")
    fleet_count = (fleet.groupby("tanker_subclass").size()
                          .rename("n").reset_index()
                          .rename(columns={"tanker_subclass": "c_sub"}))
    sub_pressure = (sub_ton.reset_index()
                          .merge(fleet_count, on="c_sub", how="inner"))
    sub_pressure = sub_pressure[sub_pressure["n"] > 0]
    sub_pressure["ton_per_vessel"] = sub_pressure["annual_ton"] / sub_pressure["n"]
    sub_label = "-"
    sub_sub = "데이터 부족"
    if not sub_pressure.empty:
        worst = sub_pressure.sort_values("ton_per_vessel", ascending=False).iloc[0]
        sub_label = worst["c_sub"]
        sub_sub = (f"{fmt.fmt_compact(worst['ton_per_vessel'], 1)}t/선/년 "
                   f"(fleet {int(worst['n'])}척)")

    # ---- 4) Retirement-bucket size (>25 yrs) ----
    yrs = pd.to_numeric(fleet["tahun"], errors="coerce")
    cur_yr = int(snapshot[:4])
    age = cur_yr - yrs
    aged25 = (age >= 25)
    aged_count = int(aged25.sum())
    aged_gt = float(pd.to_numeric(fleet.loc[aged25, "gt"], errors="coerce")
                      .fillna(0).sum())
    aged_pct = aged_count / len(fleet) * 100 if len(fleet) else 0
    aged_label = f"{aged_count:,}척"
    aged_sub = f"{fmt.fmt_gt(aged_gt)} · 전체 {fmt.fmt_pct(aged_pct)}"

    # ---- 5) Top charter-out owner (largest fleet with ≪ operator activity) ----
    fleet_owner = (fleet.dropna(subset=["nama_pemilik"])
                          .assign(owner_norm=fleet["nama_pemilik"].map(_norm_company))
                          .groupby("owner_norm")
                          .agg(fleet_count=("vessel_key", "count"),
                               fleet_gt=("gt", lambda s: pd.to_numeric(s, errors="coerce")
                                                            .fillna(0).sum()))
                          .reset_index())
    op_active = op_ton.rename("op_ton").reset_index()
    cross = fleet_owner.merge(op_active, left_on="owner_norm",
                               right_on="op_norm", how="left").fillna(0)
    # Charter-out signal: large fleet but ton activity / fleet GT very low
    cross["charter_out_signal"] = cross["fleet_gt"] / (cross["op_ton"] + 1)
    cross = cross[cross["fleet_count"] >= 3]  # ignore micro owners
    charter_label = "-"
    charter_sub = "데이터 부족"
    if not cross.empty:
        # Rank by fleet_gt; pick top with lowest op_ton/fleet_gt ratio
        top_chartered = cross.sort_values(
            ["fleet_gt", "charter_out_signal"], ascending=[False, False]
        ).head(20)
        # Among top-fleet owners, the one with lowest op_ton (most pure charter-out)
        chartered = top_chartered.sort_values("op_ton").iloc[0]
        charter_label = (chartered["owner_norm"][:24] + "…") \
            if len(str(chartered["owner_norm"])) > 24 else str(chartered["owner_norm"])
        charter_sub = (f"보유 {int(chartered['fleet_count'])}척 · "
                       f"{fmt.fmt_gt(chartered['fleet_gt'])} · "
                       f"운영자로는 {fmt.fmt_compact(chartered['op_ton'])}t")

    # ---- render the card ----
    theme.hero_strip(
        "🎯 투자 요지 (Auto-summary)",
        "5개 시그널 — 매 스냅샷에서 자동 산출. 세부 로직은 각 KPI의 ❓ 툴팁",
    )
    cols = st.columns(5)
    kpi(cols[0], "🏢 시장 지배 운영사",
        (top_op_name[:18] + "…") if len(top_op_name) > 18 else top_op_name,
        delta=f"{fmt.fmt_pct(top_op_share)} ({fmt.fmt_compact(top_op_ton)}t)",
        help="LK3 PERUSAHAAN 정규화 기준. 점유율 = 본사 운송 톤 / 전체 탱커 톤")
    kpi(cols[1], "🚀 최대 성장 항로 (YoY)",
        growth_label, delta=growth_sub,
        help="Latest 12mo vs Prior 12mo. prior 윈도우 ≥ 50k톤 필터")
    kpi(cols[2], "⚠️ 공급 압력 큰 클래스",
        sub_label, delta=sub_sub,
        help="해당 subclass의 연간 cargo 톤 ÷ 인도네시아 등기 fleet 척수. "
             "수치 클수록 외국선 의존도↑ → 신규 진입 기회")
    kpi(cols[3], "🛠️ 25년+ 노후 선대",
        aged_label, delta=aged_sub,
        help="조선업계 통상 대체 신호 기준선. 신조 발주/매각 후보")
    kpi(cols[4], "📤 차터아웃 시그널",
        charter_label, delta=charter_sub,
        help="등기 선대는 큰데 LK3에서 PERUSAHAAN으로 거의 등장 안 하는 owner. "
             "차터 아웃 모델 가능성 → 직접 인수 또는 협업 후보")
    st.caption("원본 데이터는 아래 탭에서 drilling.")
    st.markdown("---")


def _tanker_fleet_view():
    df = _tankers_full(snapshot)
    if df.empty:
        st.info("이 스냅샷에는 탱커 데이터가 없습니다.")
        return

    # Subclass selector — applies to every chart below
    subclasses = ["전체"] + sorted(df["tanker_subclass"].dropna().unique().tolist())
    sub_sel = st.selectbox("탱커 세부 분류", subclasses, index=0,
                           help="Crude / Product / Chemical / LPG / LNG / FAME / Water / UNKNOWN",
                           key="tk_fleet_sub")
    fdf = df if sub_sel == "전체" else df[df["tanker_subclass"] == sub_sel]
    if fdf.empty:
        st.warning(f"'{sub_sel}' 분류 데이터 없음")
        return

    # ---- KPI hero ----
    total = len(fdf)
    avg_gt = _avg_pos(fdf["gt"])
    sum_gt = pd.to_numeric(fdf["gt"], errors="coerce").fillna(0).sum()
    yrs = pd.to_numeric(fdf["tahun"], errors="coerce").dropna()
    cur_yr = int(snapshot[:4])
    age_series = (cur_yr - yrs).where(cur_yr - yrs >= 0)
    avg_age_v = float(age_series.mean()) if not age_series.empty else None
    aged_25 = int((age_series >= 25).sum()) if not age_series.empty else 0

    cols = st.columns(5)
    kpi(cols[0], "탱커 척수", fmt.fmt_n(total),
        help="현 스냅샷에서 Tanker 분류된 인도네시아 등기 선박 수")
    kpi(cols[1], "총 GT", fmt.fmt_gt(sum_gt),
        help="필터 결과 선박들의 총 Gross Tonnage 합계")
    kpi(cols[2], "평균 GT", fmt.fmt_gt(avg_gt),
        help="GT > 0 선박만 평균. 0/누락 제외")
    kpi(cols[3], "평균 선령",
        f"{avg_age_v:.1f} 년" if avg_age_v else "-",
        help="현재 연도(snapshot 기준) - 건조연도. tahun 결측 제외")
    kpi(cols[4], "25년 이상", fmt.fmt_n(aged_25),
        help="조선업계 통상 대체 신호 기준선. 신조 발주/매각 후보군")

    st.markdown("---")

    # ---- subclass mix (always shown, ignores subclass filter) ----
    st.subheader("세부 분류 구성")
    sub_dist = (df.groupby("tanker_subclass")
                  .agg(척수=("vessel_key", "count"),
                       총_GT=("gt", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
                       평균_GT=("gt", _avg_pos))
                  .reset_index()
                  .sort_values("척수", ascending=False))
    sub_dist["GT_share_%"] = (sub_dist["총_GT"] / sub_dist["총_GT"].sum() * 100).round(1)
    c1, c2 = st.columns([1, 1])
    with c1:
        fig = px.bar(sub_dist, x="tanker_subclass", y="척수",
                     color="tanker_subclass", color_discrete_map=_TANKER_PALETTE,
                     labels={"tanker_subclass": "세부 분류", "척수": "척수"})
        fig.update_layout(height=320, margin=dict(t=10, b=10), showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with c2:
        fig = px.pie(sub_dist, names="tanker_subclass", values="총_GT",
                     color="tanker_subclass", color_discrete_map=_TANKER_PALETTE,
                     hole=0.5)
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          legend=dict(font=dict(size=10)))
        fig.update_traces(textinfo="percent+label", textposition="outside")
        theme.donut_center(fig, fmt.fmt_gt(sub_dist["총_GT"].sum()),
                           "탱커 총 GT")
        st.plotly_chart(fig, width="stretch")
    theme.dataframe(sub_dist)
    _csv_button(sub_dist, f"tanker_subclass_mix_{snapshot}.csv",
                key="tk_dl_subclass")

    st.markdown("---")

    # ---- fleet aging ----
    st.subheader("선령 분포")
    cur_yr = int(snapshot[:4])
    age_df = pd.DataFrame({
        "subclass": fdf["tanker_subclass"],
        "age": cur_yr - pd.to_numeric(fdf["tahun"], errors="coerce"),
    }).dropna()
    age_df = age_df[(age_df["age"] >= 0) & (age_df["age"] <= 80)]
    if age_df.empty:
        st.info("건조연도 데이터 없음")
    else:
        fig = px.histogram(
            age_df, x="age", color="subclass", nbins=40,
            color_discrete_map=_TANKER_PALETTE,
            labels={"age": "선령 (년)", "count": "척수"},
        )
        # vertical reference line at 25y (industry retirement signal)
        fig.add_vline(x=25, line_dash="dash", line_color="#dc2626",
                      annotation_text="25년 (대체 신호)", annotation_position="top right")
        fig.update_layout(height=360, margin=dict(t=10, b=10), barmode="stack")
        st.plotly_chart(fig, width="stretch")

    # ---- aged-fleet alert (>= 25) ----
    if not age_df.empty and aged_25 > 0:
        with st.expander(f"⚠️ 25년 이상 탱커 ({aged_25}척) — 대체/투자 신호", expanded=False):
            old = fdf.assign(age=cur_yr - pd.to_numeric(fdf["tahun"], errors="coerce"))
            old = old[old["age"] >= 25].sort_values("age", ascending=False)
            cols_old = ["nama_kapal", "tanker_subclass", "nama_pemilik",
                        "bendera", "gt", "tahun", "age"]
            cols_old = [c for c in cols_old if c in old.columns]
            st.dataframe(old[cols_old].head(500),
                         width="stretch", hide_index=True)

    st.markdown("---")

    # ---- fleet aging buckets + $/GT replacement-value proxy (iter #13) ----
    _fleet_aging_buckets_view(fdf, cur_yr)

    st.markdown("---")

    # ---- vessel utilization timeseries (iter #18) ----
    _fleet_utilization_view(sub_sel)

    st.markdown("---")

    # ---- age vs activity correlation (iter #29) ----
    _age_activity_correlation_view(sub_sel)

    st.markdown("---")

    # ---- top tankers by USD revenue (iter #31) ----
    _top_vessels_by_usd_view(sub_sel)


def _top_vessels_by_usd_view(sub_sel: str = "전체") -> None:
    """💎 Top tankers ranked by 24mo USD cargo revenue proxy.

    Joins vessel-level LK3 USD revenue (TON × commodity price) with the
    fleet record + utilization. Identifies the highest-revenue tankers in
    the snapshot, plus a sub-list of high-revenue idle tankers — the most
    actionable M&A / charter-in candidates.
    """
    st.subheader("💎 USD 매출 상위 탱커")

    flows = _tanker_cargo_flows(snapshot)
    util = _vessel_utilization(snapshot)
    if flows.empty or util.empty:
        st.info("USD 랭킹 데이터 부족")
        return

    # Subclass filter
    if sub_sel != "전체" and "tanker_subclass" in util.columns:
        util = util[util["tanker_subclass"] == sub_sel]

    # Stack BONGKAR + MUAT into single (kapal, kom, ton)
    b = flows[["kapal", "bongkar_kom", "bongkar_ton"]].rename(
        columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
    m = flows[["kapal", "muat_kom", "muat_ton"]].rename(
        columns={"muat_kom": "kom", "muat_ton": "ton"})
    long = pd.concat([b, m], ignore_index=True).dropna(subset=["kom"])
    long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
    long = long[long["ton"] > 0].copy()
    long["bucket"] = long["kom"].map(_classify_kom_for_palette)
    long["price_usd"] = long["bucket"].map(
        lambda b: _COMMODITY_USD_PER_TON.get(b, 500.0))
    long["usd_revenue"] = long["ton"] * long["price_usd"]
    long["kapal_norm"] = long["kapal"].fillna("").str.upper().str.strip()

    # Per-vessel USD aggregation
    vessel_usd = (long.groupby("kapal_norm")
                       .agg(USD_M=("usd_revenue", lambda s: s.sum() / 1e6),
                            ton_M=("ton", lambda s: s.sum() / 1e6),
                            n_rows=("usd_revenue", "size"))
                       .reset_index())
    if vessel_usd.empty:
        st.info("USD 매출 계산 가능한 vessel 없음")
        return

    # Join with fleet utilization
    util_keep = ["kapal_norm", "nama_kapal", "tanker_subclass",
                 "nama_pemilik", "bendera", "gt", "tahun", "imo",
                 "months_active", "util_pct", "status"]
    util_keep = [c for c in util_keep if c in util.columns]
    merged = vessel_usd.merge(util[util_keep], on="kapal_norm", how="left")
    merged = merged.sort_values("USD_M", ascending=False)

    # KPI
    n_total = len(merged)
    top1_usd = float(merged.iloc[0]["USD_M"]) if not merged.empty else 0
    top1_name = merged.iloc[0].get("nama_kapal") or merged.iloc[0]["kapal_norm"]
    top10_usd = float(merged.head(10)["USD_M"].sum())
    cols = st.columns(4)
    kpi(cols[0], "분석 vessel 수", fmt.fmt_int(n_total),
        help="LK3 USD 매출 발생 vessel (필터 적용 후)")
    kpi(cols[1], "Top1 매출",
        f"${top1_usd:,.0f}M",
        help=f"{top1_name}")
    kpi(cols[2], "Top10 누적",
        f"${top10_usd:,.0f}M")
    kpi(cols[3], "Top10 점유율",
        fmt.fmt_pct(top10_usd / merged["USD_M"].sum() * 100)
        if merged["USD_M"].sum() > 0 else "-",
        help="상위 10척이 전체 USD 매출에서 차지하는 비율")

    # Top N selectable
    top_n = st.slider("Top N vessels", 10, 100, 30, key="tk_top_usd_n")
    top = merged.head(top_n).copy()

    # Display columns
    show = top.copy()
    show["USD_M"] = show["USD_M"].round(0)
    show["ton_M"] = show["ton_M"].round(2)
    show["util_pct"] = show["util_pct"].round(1) if "util_pct" in show.columns else None
    cur_yr = int(snapshot[:4])
    show["age"] = (cur_yr - pd.to_numeric(show["tahun"], errors="coerce")).astype("Int64")

    cols_show = ["nama_kapal", "tanker_subclass", "nama_pemilik", "bendera",
                 "gt", "age", "USD_M", "ton_M", "n_rows",
                 "months_active", "util_pct", "status", "imo"]
    cols_show = [c for c in cols_show if c in show.columns]
    theme.dataframe(show[cols_show])
    _csv_button(merged[cols_show + ["kapal_norm"]] if "kapal_norm" in merged.columns
                else merged, f"top_vessels_usd_{snapshot}.csv",
                key="tk_dl_top_usd")

    # ---- High-revenue idle sub-table (M&A goldmine) ----
    st.markdown("##### 💰 고매출 + Idle = M&A 우선 후보 Top 20")
    if "status" not in merged.columns:
        st.info("utilization 데이터 부족 — Idle 표시 불가")
    else:
        idle_high = merged[
            merged["status"].fillna("").str.startswith("Idle")
        ].sort_values("USD_M", ascending=False).head(20)
        if idle_high.empty:
            st.info("Idle 분류 vessel 없음")
        else:
            disp = idle_high.copy()
            disp["USD_M"] = disp["USD_M"].round(0)
            disp["ton_M"] = disp["ton_M"].round(2)
            disp["util_pct"] = disp["util_pct"].round(1)
            disp["age"] = (cur_yr - pd.to_numeric(disp["tahun"], errors="coerce")).astype("Int64")
            cols_idle = ["nama_kapal", "tanker_subclass", "nama_pemilik",
                         "gt", "age", "USD_M", "months_active", "util_pct"]
            cols_idle = [c for c in cols_idle if c in disp.columns]
            theme.dataframe(disp[cols_idle])
            _csv_button(idle_high, f"high_revenue_idle_{snapshot}.csv",
                        key="tk_dl_idle_usd")
            st.caption(
                "**해석**: 24개월 USD 매출 ↑ AND utilization < 25% (Idle) → "
                "이 탱커는 idle 기간 동안에도 (활동 시) 큰 cargo를 처리. "
                "→ **소유자 매도/차터-아웃 의향 매우 높음** 후보. 한국 매수 또는 차터-인 협상 우선 타깃."
            )

    # ---- USD per call efficiency (high-USD-per-row vessels) ----
    if "n_rows" in merged.columns:
        st.markdown("##### 🚀 호출 1회당 USD 매출 효율 (high-value vessels)")
        merged["USD_per_call_M"] = (merged["USD_M"] /
                                     merged["n_rows"].replace(0, pd.NA))
        eff = (merged[merged["n_rows"] >= 10]
                  .sort_values("USD_per_call_M", ascending=False).head(20))
        if not eff.empty:
            disp = eff.copy()
            disp["USD_per_call_M"] = disp["USD_per_call_M"].round(2)
            disp["USD_M"] = disp["USD_M"].round(0)
            disp["age"] = (cur_yr - pd.to_numeric(disp["tahun"], errors="coerce")).astype("Int64")
            cols_eff = ["nama_kapal", "tanker_subclass", "nama_pemilik",
                        "gt", "age", "USD_per_call_M", "n_rows", "USD_M"]
            cols_eff = [c for c in cols_eff if c in disp.columns]
            theme.dataframe(disp[cols_eff])
            st.caption(
                "n_rows ≥ 10 필터 적용. **USD/call 높음 = 대형 cargo 운송선** — "
                "일반적으로 VLCC / 대형 LNG carrier. 한국 신조 발주 직접 비교 대상."
            )

    st.markdown("---")

    # ---- owner concentration / HHI ----
    st.subheader("소유주 집중도")
    own = (fdf.dropna(subset=["nama_pemilik"])
              .assign(gt_num=lambda x: pd.to_numeric(x["gt"], errors="coerce").fillna(0))
              .groupby("nama_pemilik")
              .agg(척수=("vessel_key", "count"),
                   총_GT=("gt_num", "sum"))
              .reset_index()
              .sort_values("총_GT", ascending=False))
    if not own.empty:
        own["GT_점유율_%"] = (own["총_GT"] / own["총_GT"].sum() * 100).round(2)
        own["척수_점유율_%"] = (own["척수"] / own["척수"].sum() * 100).round(2)
        hhi_gt = _hhi(own["GT_점유율_%"])
        hhi_count = _hhi(own["척수_점유율_%"])
        cr5_gt = own["GT_점유율_%"].head(5).sum()
        cr10_gt = own["GT_점유율_%"].head(10).sum()
        c1, c2, c3, c4 = st.columns(4)
        kpi(c1, "고유 소유주 수", len(own))
        # HHI band — Indonesian regulator KPPU uses similar thresholds
        band = ("낮음" if hhi_gt < 1500 else
                "중간" if hhi_gt < 2500 else "높음")
        kpi(c2, "HHI (GT 기준)", f"{hhi_gt:,.0f} ({band})")
        kpi(c3, "Top5 점유율 (GT)", f"{cr5_gt:.1f}%")
        kpi(c4, "Top10 점유율 (GT)", f"{cr10_gt:.1f}%")

        top_n = st.slider("표시할 소유주 수", 5, 30, 15, key="tk_own_n")
        own_top = own.head(top_n).sort_values("총_GT")
        fig = px.bar(own_top, x="총_GT", y="nama_pemilik", orientation="h",
                     hover_data=["척수", "GT_점유율_%"],
                     color="총_GT", color_continuous_scale=theme.SCALES["blue"])
        fig.update_layout(height=max(360, top_n * 22),
                          margin=dict(t=10, b=10),
                          yaxis_title="", xaxis_title="총 GT",
                          coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")
        theme.dataframe(own.head(top_n))
        _csv_button(own, f"tanker_owners_{snapshot}.csv",
                    label="📥 전체 소유주 CSV", key="tk_dl_owners")

    st.markdown("---")

    # ---- flag mix ----
    st.subheader("국적(Flag State) 분포")
    fl = (fdf.dropna(subset=["bendera"])
             .assign(gt_num=lambda x: pd.to_numeric(x["gt"], errors="coerce").fillna(0))
             .groupby("bendera")
             .agg(척수=("vessel_key", "count"), 총_GT=("gt_num", "sum"))
             .reset_index()
             .sort_values("총_GT", ascending=False)
             .head(15))
    if not fl.empty:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(fl.sort_values("척수"), x="척수", y="bendera",
                         orientation="h", color="척수",
                         color_continuous_scale=theme.SCALES["amber"])
            fig.update_layout(height=380, margin=dict(t=10, b=10),
                              yaxis_title="", xaxis_title="척수",
                              coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")
        with c2:
            fig = px.bar(fl.sort_values("총_GT"), x="총_GT", y="bendera",
                         orientation="h", color="총_GT",
                         color_continuous_scale=theme.SCALES["blue"])
            fig.update_layout(height=380, margin=dict(t=10, b=10),
                              yaxis_title="", xaxis_title="총 GT",
                              coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # ---- raw list ----
    st.subheader("탱커 선박 목록")
    cols_show = [
        "nama_kapal", "tanker_subclass", "jenis_detail", "nama_pemilik",
        "bendera", "gt", "loa", "lebar", "dalam", "imo", "tahun",
        "pelabuhan_pendaftaran", "vessel_key",
    ]
    cols_show = [c for c in cols_show if c in fdf.columns]
    st.dataframe(
        fdf[cols_show].sort_values("gt", ascending=False, na_position="last").head(2000),
        width="stretch", hide_index=True,
    )
    st.caption(f"표시 {min(len(fdf), 2000):,} / 전체 {len(fdf):,} 척 (최대 2,000)")


# ------------- Tanker Cargo Flow view (iteration #2) -------------

def _classify_kom_for_palette(label: str | None) -> str:
    """Bucket a freeform komoditi text into a stable color category for charts."""
    if not label:
        return "기타"
    s = str(label).upper()
    if "CRUDE" in s or "MENTAH" in s:                 return "Crude"
    if "CPO" in s or "PALM OIL" in s or "MINYAK SAWIT" in s: return "CPO/팜오일"
    if "LNG" in s or "NATURAL GAS" in s or "GAS ALAM" in s: return "LNG"
    if any(k in s for k in ("LPG", "ELPIJI", "PROPANE", "BUTANE")): return "LPG"
    if any(k in s for k in ("PERTALITE", "PERTAMAX", "GASOLINE", "BENZIN", "MOGAS")): return "BBM-가솔린"
    if any(k in s for k in ("SOLAR", "DIESEL", "BIOSOLAR", "GASOIL", "GAS OIL")): return "BBM-디젤"
    if "AVTUR" in s or "JET" in s or "AVGAS" in s:    return "BBM-항공유"
    if "BBM" in s:                                    return "BBM-기타"
    if "CHEMICAL" in s or "KIMIA" in s:               return "Chemical"
    if any(k in s for k in ("FAME", "BIODIESEL", "METHYL ESTER", "METIL ESTER")): return "FAME"
    if "ASPHALT" in s or "ASPAL" in s:                return "아스팔트"
    if any(k in s for k in ("RBD", "OLEIN", "STEARIN", "PKO", "CPKO", "PKS")): return "팜 파생"
    if "MINYAK" in s or "VEGETABLE OIL" in s:         return "기타 식용유"
    if "FUEL OIL" in s or "BUNKER" in s:              return "벙커유"
    if "NAPHTHA" in s or "NAFTA" in s:                return "Naphtha"
    if "KEROSEN" in s:                                return "Kerosene"
    return "기타"


_KOM_BUCKET_PALETTE = {
    "Crude":         "#0f172a",
    "BBM-가솔린":     "#b91c1c",
    "BBM-디젤":       "#92400e",
    "BBM-항공유":     "#0e7490",
    "BBM-기타":       "#6b7280",
    "벙커유":          "#3f3f46",
    "CPO/팜오일":     "#16a34a",
    "팜 파생":        "#84cc16",
    "기타 식용유":    "#65a30d",
    "FAME":          "#a3e635",
    "LNG":           "#0891b2",
    "LPG":           "#f59e0b",
    "Chemical":      "#7c3aed",
    "Naphtha":       "#1e40af",
    "Kerosene":      "#3b82f6",
    "아스팔트":       "#27272a",
    "기타":          "#9ca3af",
}


def _od_usd_lanes(df: pd.DataFrame, od_agg: pd.DataFrame) -> None:
    """💲 Top USD trade lanes — ranks OD pairs by commodity-priced USD revenue.

    Distinct from the ton-based OD ranking: high-$/ton commodities (Crude,
    Chemical, FAME) re-rank lanes upward; bulk LPG/LNG that's high in tons
    can drop in USD ranking. The ranking-shift table makes the price effect
    visible.
    """
    st.markdown("##### 💲 Top USD 항로")
    if df.empty:
        return

    # USD per OD pair
    pairs = df.dropna(subset=["origin", "destination"]).copy()
    pairs = pairs[pairs["origin"] != pairs["destination"]]
    if pairs.empty:
        st.info("USD 항로 분석 가능한 데이터 없음")
        return

    # BONGKAR + MUAT stacked, classify bucket → price
    b = pairs[["origin", "destination", "bongkar_kom", "bongkar_ton"]].rename(
        columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
    m = pairs[["origin", "destination", "muat_kom", "muat_ton"]].rename(
        columns={"muat_kom": "kom", "muat_ton": "ton"})
    long = pd.concat([b, m], ignore_index=True).dropna(subset=["kom"])
    long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
    long = long[long["ton"] > 0].copy()
    long["bucket"] = long["kom"].map(_classify_kom_for_palette)
    long["price"] = long["bucket"].map(
        lambda b: _COMMODITY_USD_PER_TON.get(b, 500.0))
    long["usd"] = long["ton"] * long["price"]

    usd_pairs = (long.groupby(["origin", "destination"])
                       .agg(USD_M=("usd", lambda s: s.sum() / 1e6),
                            ton_M=("ton", lambda s: s.sum() / 1e6),
                            n_rows=("usd", "size"))
                       .reset_index().sort_values("USD_M", ascending=False))
    usd_pairs["USD_M"] = usd_pairs["USD_M"].round(0)
    usd_pairs["ton_M"] = usd_pairs["ton_M"].round(2)

    if usd_pairs.empty:
        st.info("USD 매출 항로 데이터 없음")
        return

    # Top N
    top_n = st.slider("Top N USD 항로", 10, 40, 20, key="tk_od_usd_n")
    top = usd_pairs.head(top_n).copy()
    top["pair"] = top["origin"].astype(str) + " → " + top["destination"].astype(str)

    # KPI
    total_usd = float(usd_pairs["USD_M"].sum())
    top10_usd = float(usd_pairs.head(10)["USD_M"].sum())
    top1 = usd_pairs.iloc[0]
    cols = st.columns(4)
    kpi(cols[0], "전체 OD pair", fmt.fmt_int(len(usd_pairs)),
        help="origin ≠ destination, ton > 0 항로")
    kpi(cols[1], "Top1 항로",
        f"{top1['origin'][:14]} → {top1['destination'][:14]}",
        delta=f"${top1['USD_M']:,.0f}M")
    kpi(cols[2], "Top10 누적", f"${top10_usd:,.0f}M",
        help=f"{top10_usd/total_usd*100:.1f}% of all USD lanes")
    kpi(cols[3], "전체 USD", f"${total_usd:,.0f}M")

    # Bar chart
    fig = px.bar(top.sort_values("USD_M"), x="USD_M", y="pair",
                 orientation="h",
                 color="USD_M", color_continuous_scale=theme.SCALES["blue"],
                 hover_data=["ton_M", "n_rows"],
                 labels={"USD_M": "USD (M)", "pair": ""})
    fig.update_layout(height=max(400, top_n * 22),
                      margin=dict(t=10, b=10),
                      coloraxis_showscale=False)
    st.plotly_chart(fig, width="stretch")

    # ---- Ranking-shift table: ton-rank vs USD-rank ----
    st.markdown("##### 🔄 톤 vs USD 순위 차이 (Top 30)")
    # Ton ranking from od_agg (already passed in)
    ton_rank = od_agg.copy()
    ton_rank["ton_rank"] = range(1, len(ton_rank) + 1)
    usd_rank = usd_pairs.copy()
    usd_rank["usd_rank"] = range(1, len(usd_rank) + 1)
    merged = usd_rank.merge(
        ton_rank[["origin", "destination", "ton_rank", "총_톤"]],
        on=["origin", "destination"], how="left",
    )
    merged["rank_shift"] = merged["ton_rank"] - merged["usd_rank"]
    merged = merged.head(30).copy()
    merged["pair"] = merged["origin"] + " → " + merged["destination"]
    show = merged[["pair", "USD_M", "ton_M", "n_rows",
                   "usd_rank", "ton_rank", "rank_shift"]]
    show = show.rename(columns={
        "USD_M": "USD (M)", "ton_M": "톤 (M)",
        "usd_rank": "USD 순위", "ton_rank": "톤 순위",
        "rank_shift": "순위 변동",
    })
    theme.dataframe(show)
    st.caption(
        "**해석**: 순위 변동 > 0 = 톤 기준보다 USD 기준이 더 높음 → "
        "**고가 commodity 우세 항로** (Crude/Chemical/FAME). "
        "변동 < 0 = 톤보다 USD가 낮음 → 저가 commodity (LNG·LPG bulk). "
        "한국 투자자는 USD-우위 항로 진입 시 **마진 압박 ↓**."
    )

    # CSV
    _csv_button(usd_pairs.head(200), f"od_usd_lanes_{snapshot}.csv",
                key="tk_dl_od_usd")


def _render_sankey(od_top: pd.DataFrame, ton_col: str = "총_톤") -> None:
    """Render a Plotly Sankey chart of OD-pair tonnage flows.

    `od_top` must have columns: origin, destination, plus the value column
    in ``ton_col``. Origin and destination namespaces are kept distinct
    (e.g. "JAKARTA · 출발" vs "JAKARTA · 도착") so the same port name on
    both sides doesn't collapse the graph into a self-loop.
    """
    if od_top is None or od_top.empty:
        st.info("Sankey 표시할 데이터가 없습니다.")
        return
    sources, targets, values, link_labels = [], [], [], []
    nodes: list[str] = []
    idx: dict[str, int] = {}

    def _node(label: str) -> int:
        if label not in idx:
            idx[label] = len(nodes)
            nodes.append(label)
        return idx[label]

    for r in od_top.itertuples(index=False):
        o = str(getattr(r, "origin"))[:30]
        d = str(getattr(r, "destination"))[:30]
        v = float(getattr(r, ton_col))
        if v <= 0:
            continue
        si = _node(f"{o} · 출발")
        ti = _node(f"{d} · 도착")
        sources.append(si)
        targets.append(ti)
        values.append(v)
        link_labels.append(f"{o} → {d}: {fmt.fmt_compact(v, 1)}t")

    if not values:
        st.info("Sankey 표시할 데이터가 없습니다.")
        return

    # Color nodes by side (origin teal, destination amber) for legibility.
    node_colors = [
        "#0d9488" if lbl.endswith("출발") else "#f59e0b" for lbl in nodes
    ]
    fig = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=14, thickness=18,
            label=nodes, color=node_colors,
            line=dict(color="black", width=0.3),
        ),
        link=dict(
            source=sources, target=targets, value=values,
            label=link_labels,
            color="rgba(30, 64, 175, 0.35)",
        ),
    )])
    fig.update_layout(
        height=max(480, 22 * len(nodes)),
        margin=dict(t=10, b=10, l=10, r=10),
        font=dict(size=11),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "왼쪽 = 출발 항구, 오른쪽 = 도착 항구. 화살 두께 ∝ 총 톤. "
        "동일 항구가 양쪽에 등장하는 경우 (예: SINGAPORE 출발 ↔ SINGAPORE 도착) "
        "도시 안 이동(intra-city) / 해상 STS 트랜스퍼 신호."
    )


def _tanker_cargo_flow_map(df: pd.DataFrame) -> None:
    """🗺️ Indonesia map of tanker cargo flows.

    Origin → destination pairs are aggregated from the LK3 ``BERANGKAT.KE``
    and ``TIBA.DARI`` fields, mapped to coordinates, then drawn as great-arc
    flow lines coloured by commodity bucket. Port bubbles size by total ton
    routed through the port.

    Vessel list panel below the map surfaces the actual ships that loaded /
    unloaded the selected commodity bucket — ranked by 24mo total ton.
    """
    st.subheader("🗺️ 탱커 화물 흐름 지도 (Origin → Destination)")
    st.caption(
        "벤치마크: jang1117.github.io/shipping_volume — "
        "버블 크기 = 항구별 24mo 총 톤, 선 두께 ∝ 항로 톤, 색상 = 화물 카테고리. "
        "외국 항구 (SINGAPORE 등)는 지도 밖 — 별도 KPI에 합산."
    )

    coord_map, foreign_set = _port_name_to_coords()

    # ---- Build long-form (origin, destination, kom, ton) stream ----
    b = df[["origin", "destination", "kapal", "operator", "jenis_kapal",
            "bongkar_kom", "bongkar_ton", "gt", "dwt"]].rename(
        columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
    b["direction"] = "BONGKAR"
    m = df[["origin", "destination", "kapal", "operator", "jenis_kapal",
            "muat_kom", "muat_ton", "gt", "dwt"]].rename(
        columns={"muat_kom": "kom", "muat_ton": "ton"})
    m["direction"] = "MUAT"
    long = pd.concat([b, m], ignore_index=True)
    long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
    long = long[long["ton"] > 0].copy()
    long["bucket"] = long["kom"].map(_classify_kom_for_palette)

    # ---- Filter controls ----
    fc1, fc2, fc3 = st.columns([2, 2, 1])
    with fc1:
        all_buckets = (long.groupby("bucket")["ton"].sum()
                            .sort_values(ascending=False).index.tolist())
        # default: top 6 buckets so user immediately sees something dense
        default_buckets = all_buckets[:6]
        sel_buckets = st.multiselect(
            "화물 카테고리", all_buckets, default=default_buckets,
            help="선택한 카테고리만 흐름선으로 표시. 비워두면 모든 카테고리 표시.",
            key="tk_map_buckets",
        )
        if not sel_buckets:
            sel_buckets = all_buckets
    with fc2:
        dir_pick = st.radio(
            "방향",
            ["전체", "BONGKAR (양하)", "MUAT (적재)"],
            horizontal=True, key="tk_map_dir",
        )
    with fc3:
        top_n_lanes = st.slider(
            "Top N 항로", 10, 200, 60, step=10, key="tk_map_topn",
            help="가독성을 위해 상위 N개 항로만 표시 (시각적 노이즈 컷)",
        )

    f = long[long["bucket"].isin(sel_buckets)].copy()
    if dir_pick.startswith("BONGKAR"):
        f = f[f["direction"] == "BONGKAR"]
    elif dir_pick.startswith("MUAT"):
        f = f[f["direction"] == "MUAT"]
    if f.empty:
        st.info("필터 조건에 해당하는 화물 흐름이 없습니다.")
        return

    # ---- Resolve coordinates ----
    f["o_norm"] = f["origin"].map(_normalize_port_name)
    f["d_norm"] = f["destination"].map(_normalize_port_name)
    f["o_coord"] = f["o_norm"].map(lambda k: coord_map.get(k))
    f["d_coord"] = f["d_norm"].map(lambda k: coord_map.get(k))
    f["o_foreign"] = f["o_norm"].isin(foreign_set)
    f["d_foreign"] = f["d_norm"].isin(foreign_set)

    # Total ton broken into mappable / international / unknown
    total_ton = float(f["ton"].sum())
    intl_ton = float(f.loc[f["o_foreign"] | f["d_foreign"], "ton"].sum())
    plottable = f.dropna(subset=["o_coord", "d_coord"]).copy()
    plottable = plottable[~(plottable["o_foreign"] | plottable["d_foreign"])]
    plot_ton = float(plottable["ton"].sum())
    unknown_ton = total_ton - intl_ton - plot_ton

    cN = st.columns(4)
    kpi(cN[0], "필터 톤 합", fmt.fmt_ton(total_ton),
        help="현재 필터 (카테고리 + 방향) 하 전체 톤 합")
    kpi(cN[1], "지도 표시 톤", fmt.fmt_ton(plot_ton),
        help="origin/destination 양쪽 좌표 매핑된 항로의 톤 합")
    kpi(cN[2], "국제 항해 톤",
        fmt.fmt_ton(intl_ton),
        help="origin 또는 destination이 외국 (SINGAPORE 등)인 항해 — 지도 밖")
    kpi(cN[3], "미매핑 톤",
        fmt.fmt_ton(unknown_ton),
        help="origin/destination 텍스트가 좌표 사전에 없음 (소규모 항구·터미널)")

    if plottable.empty:
        st.info("좌표 매핑 가능한 항로가 없습니다.")
        return

    # ---- Aggregate OD pairs by bucket ----
    plottable["lat_o"] = plottable["o_coord"].map(lambda c: c[0])
    plottable["lon_o"] = plottable["o_coord"].map(lambda c: c[1])
    plottable["lat_d"] = plottable["d_coord"].map(lambda c: c[0])
    plottable["lon_d"] = plottable["d_coord"].map(lambda c: c[1])

    od_bucket = (plottable.groupby(
                    ["o_norm", "d_norm", "lat_o", "lon_o", "lat_d", "lon_d", "bucket"])
                          .agg(ton=("ton", "sum"), n_calls=("ton", "size"),
                               n_vessels=("kapal", "nunique"))
                          .reset_index())
    od_bucket = od_bucket[od_bucket["o_norm"] != od_bucket["d_norm"]]  # exclude self-loops on map
    if od_bucket.empty:
        st.info("Origin ≠ Destination 항로가 없습니다 (모두 self-loop).")
        return
    od_bucket = od_bucket.sort_values("ton", ascending=False).head(top_n_lanes)

    # Per-port aggregate (bubble sizing)
    port_ton = pd.concat([
        plottable[["o_norm", "lat_o", "lon_o", "ton"]].rename(
            columns={"o_norm": "port", "lat_o": "lat", "lon_o": "lon"}),
        plottable[["d_norm", "lat_d", "lon_d", "ton"]].rename(
            columns={"d_norm": "port", "lat_d": "lat", "lon_d": "lon"}),
    ], ignore_index=True)
    port_agg = (port_ton.groupby(["port", "lat", "lon"])["ton"].sum()
                          .reset_index().sort_values("ton", ascending=False))

    # ---- Build figure ----
    max_ton = float(od_bucket["ton"].max())
    fig = go.Figure()

    # 1) Flow lines per bucket trace (so legend toggles work cleanly)
    for bucket, sub in od_bucket.groupby("bucket"):
        color = _KOM_BUCKET_PALETTE.get(bucket, "#64748b")
        # One trace per OD lane so we can vary line width by ton
        # Plotly can't vary width along one trace, so issue per-lane sub-traces
        # but group by bucket via legendgroup to keep legend tidy.
        first = True
        for r in sub.itertuples(index=False):
            width = 1.0 + 8.0 * (r.ton / max_ton) ** 0.5
            fig.add_trace(go.Scattergeo(
                lon=[r.lon_o, r.lon_d],
                lat=[r.lat_o, r.lat_d],
                mode="lines",
                line=dict(width=width, color=color),
                opacity=0.75,
                hoverinfo="text",
                text=(f"<b>{bucket}</b><br>{r.o_norm} → {r.d_norm}<br>"
                      f"{fmt.fmt_compact(r.ton, 1)}t · {r.n_vessels}척 · "
                      f"{int(r.n_calls)}회"),
                name=bucket,
                legendgroup=bucket,
                showlegend=first,
            ))
            first = False

    # 2) Port bubbles on top
    fig.add_trace(go.Scattergeo(
        lon=port_agg["lon"], lat=port_agg["lat"],
        mode="markers",
        marker=dict(
            size=(port_agg["ton"] / port_agg["ton"].max() * 26 + 4),
            color="#0f172a", opacity=0.85,
            line=dict(width=0.5, color="#ffffff"),
        ),
        text=port_agg.apply(
            lambda r: f"<b>{r['port']}</b><br>{fmt.fmt_compact(r['ton'], 1)}t",
            axis=1),
        hoverinfo="text",
        name="항구 (총 톤)",
        showlegend=True,
    ))

    fig.update_layout(
        height=620, margin=dict(t=10, b=10, l=10, r=10),
        legend=dict(
            orientation="h", y=-0.05, x=0,
            bgcolor="rgba(255,255,255,0.85)", bordercolor="#e2e8f0",
            borderwidth=1, font=dict(size=11),
        ),
        geo=dict(
            scope="asia",
            projection_type="natural earth",
            showcountries=True, showcoastlines=True, showland=True,
            showocean=True, oceancolor="#f1f5f9",
            landcolor="#fefefe", countrycolor="#cbd5e1",
            coastlinecolor="#94a3b8",
            lataxis=dict(range=[-12, 8]),
            lonaxis=dict(range=[94, 142]),
        ),
    )
    st.plotly_chart(fig, width="stretch")

    # ---- Lane table (the actual numbers behind the map) ----
    with st.expander(f"📋 항로 테이블 — Top {len(od_bucket)} (현재 필터)"):
        lane_show = (od_bucket[["o_norm", "d_norm", "bucket",
                                 "ton", "n_calls", "n_vessels"]]
                       .rename(columns={"o_norm": "출발", "d_norm": "도착",
                                        "bucket": "카테고리", "ton": "총_톤",
                                        "n_calls": "항해수", "n_vessels": "선박수"}))
        theme.dataframe(lane_show)
        _csv_button(lane_show,
                    f"tanker_flow_map_lanes_{snapshot}.csv",
                    label="📥 항로 CSV", key="tk_map_lanes_dl")

    # ============================================================
    # Vessel list panel — ships that loaded the selected cargo
    # ============================================================
    st.markdown("---")
    st.subheader("🛳️ 해당 화물을 실은 선박 리스트")
    st.caption(
        "현재 카테고리/방향 필터에 해당하는 LK3 화물 행을 선박 단위로 집계. "
        "총 톤·항해 수·주요 항로(가장 빈번한 OD)가 표시됩니다."
    )

    # Use full filtered set (not just top-N OD) so vessel ranking reflects total activity.
    vsel = f.copy()
    vsel = vsel.dropna(subset=["kapal"])
    if vsel.empty:
        st.info("선택한 카테고리에 해당하는 선박이 없습니다.")
        return

    # Per-vessel aggregate
    def _top_route(s: pd.Series) -> str:
        if s.empty:
            return "-"
        top = s.value_counts().head(1)
        if top.empty:
            return "-"
        return f"{top.index[0]} ({int(top.iloc[0])}회)"

    vsel["route_label"] = (vsel["origin"].fillna("?").astype(str)
                           + " → "
                           + vsel["destination"].fillna("?").astype(str))
    v_agg = (vsel.groupby("kapal")
                  .agg(총_톤=("ton", "sum"),
                       항해수=("ton", "size"),
                       운영사=("operator",
                              lambda s: s.dropna().mode().iloc[0]
                              if not s.dropna().empty else "-"),
                       jenis_kapal=("jenis_kapal",
                              lambda s: s.dropna().mode().iloc[0]
                              if not s.dropna().empty else "-"),
                       gt=("gt",
                              lambda s: pd.to_numeric(s, errors="coerce").max()),
                       dwt=("dwt",
                              lambda s: pd.to_numeric(s, errors="coerce").max()),
                       카테고리=("bucket",
                              lambda s: s.value_counts().index[0]
                              if not s.empty else "-"),
                       주요_항로=("route_label", _top_route))
                  .reset_index()
                  .sort_values("총_톤", ascending=False))
    v_agg["총_톤"] = v_agg["총_톤"].round(0)
    v_agg["gt"] = pd.to_numeric(v_agg["gt"], errors="coerce").round(0)
    v_agg["dwt"] = pd.to_numeric(v_agg["dwt"], errors="coerce").round(0)

    cV = st.columns(4)
    kpi(cV[0], "선박 수", fmt.fmt_int(len(v_agg)),
        help="현재 필터 하의 고유 KAPAL 수")
    kpi(cV[1], "Top 1 톤", fmt.fmt_ton(float(v_agg.iloc[0]["총_톤"])),
        help=f"최다 운송 선박: {v_agg.iloc[0]['kapal']}")
    kpi(cV[2], "운영사 수", fmt.fmt_int(int(v_agg["운영사"].nunique())),
        help="이 카테고리에 진입한 운영사 수")
    kpi(cV[3], "평균 항해/척",
        f"{v_agg['항해수'].mean():.1f}",
        help="선박당 평균 항해 (LK3 행) 수")

    show_top_n = st.slider(
        "선박 Top N", 10, min(200, len(v_agg)),
        min(50, len(v_agg)), step=10, key="tk_map_vessel_topn",
    )
    cols_show = ["kapal", "운영사", "jenis_kapal", "카테고리",
                 "gt", "dwt", "총_톤", "항해수", "주요_항로"]
    cols_show = [c for c in cols_show if c in v_agg.columns]
    theme.dataframe(v_agg[cols_show].head(show_top_n))
    _csv_button(v_agg[cols_show],
                f"tanker_flow_map_vessels_{snapshot}.csv",
                label="📥 선박 리스트 CSV", key="tk_map_vessels_dl")


def _tanker_flow_view():
    with st.spinner("탱커 화물 흐름 데이터 불러오는 중 (최초 1회 수십 초 소요)…"):
        df = _tanker_cargo_flows(snapshot)
    if df.empty:
        st.info("이 스냅샷에는 탱커 화물 데이터가 없습니다.")
        return

    # ---- KPI hero ----
    n_calls = len(df)
    bton = pd.to_numeric(df["bongkar_ton"], errors="coerce").fillna(0)
    mton = pd.to_numeric(df["muat_ton"], errors="coerce").fillna(0)
    sum_b, sum_m = float(bton.sum()), float(mton.sum())
    n_ports = df["kode_pelabuhan"].nunique()
    n_kapal = df["kapal"].nunique()
    n_op = df["operator"].nunique()
    cols = st.columns(6)
    kpi(cols[0], "탱커 행 수", fmt.fmt_int(n_calls),
        help="LK3 양식의 탱커 분류 행 수. 1행 = 1 항해의 양하 또는 적재 항목")
    kpi(cols[1], "고유 탱커명", fmt.fmt_int(n_kapal),
        help="중복 제거한 KAPAL 필드 값. 등기 외 외국선 포함 가능")
    kpi(cols[2], "고유 운영사", fmt.fmt_int(n_op),
        help="LK3의 PERUSAHAAN 필드 (운영사/대리점). 정규화 전 원본 기준")
    kpi(cols[3], "기항 항구", fmt.fmt_int(n_ports),
        help="이 윈도우에서 탱커가 1회 이상 기항한 항구 수")
    kpi(cols[4], "BONGKAR 합", fmt.fmt_ton(sum_b),
        help="양하(下船) 톤 합계. 24개월 누적치")
    kpi(cols[5], "MUAT 합", fmt.fmt_ton(sum_m),
        help="적재(船積) 톤 합계. 24개월 누적치")
    st.caption(
        "BONGKAR = 양하(unload), MUAT = 적재(load). "
        "동일 항해는 한쪽 또는 양쪽에 톤이 기록될 수 있음."
    )

    st.markdown("---")

    # ---- Cargo flow map (top of view, replaces text-only Sankey as the
    #      first visual the user sees) ----
    _tanker_cargo_flow_map(df)

    st.markdown("---")

    # ---- direction filter applies to commodity / OD / monthly views ----
    direction = st.radio(
        "방향", ["BONGKAR (양하)", "MUAT (적재)", "BONGKAR + MUAT 합산"],
        horizontal=True, key="tk_flow_dir",
    )
    if direction.startswith("BONGKAR (양하)"):
        kom_col, ton_col = "bongkar_kom", "bongkar_ton"
    elif direction.startswith("MUAT"):
        kom_col, ton_col = "muat_kom", "muat_ton"
    else:
        kom_col, ton_col = None, None  # combined branch

    # ---------- Top commodities ----------
    st.subheader("Top 화물 종류 (톤 기준)")
    if kom_col:
        agg = (df.dropna(subset=[kom_col])
                 .assign(ton=pd.to_numeric(df[ton_col], errors="coerce").fillna(0))
                 .groupby(kom_col)
                 .agg(총_톤=("ton", "sum"), 행수=(kom_col, "count"))
                 .reset_index().rename(columns={kom_col: "komoditi"}))
    else:
        # Combined: stack BONGKAR + MUAT, treat as single (komoditi, ton) stream
        b = df[["bongkar_kom", "bongkar_ton"]].rename(
            columns={"bongkar_kom": "komoditi", "bongkar_ton": "ton"})
        m = df[["muat_kom", "muat_ton"]].rename(
            columns={"muat_kom": "komoditi", "muat_ton": "ton"})
        both = pd.concat([b, m], ignore_index=True)
        both["ton"] = pd.to_numeric(both["ton"], errors="coerce").fillna(0)
        both = both.dropna(subset=["komoditi"])
        agg = (both.groupby("komoditi")
                   .agg(총_톤=("ton", "sum"), 행수=("ton", "count"))
                   .reset_index())

    agg = agg[agg["총_톤"] > 0].sort_values("총_톤", ascending=False)
    if agg.empty:
        st.info("화물 데이터 없음")
    else:
        agg["bucket"] = agg["komoditi"].map(_classify_kom_for_palette)
        agg["톤_점유율_%"] = (agg["총_톤"] / agg["총_톤"].sum() * 100).round(2)
        top_n = st.slider("Top N 화물", 5, 30, 15, key="tk_flow_topn")
        top = agg.head(top_n).sort_values("총_톤")
        fig = px.bar(top, x="총_톤", y="komoditi", orientation="h",
                     color="bucket", color_discrete_map=_KOM_BUCKET_PALETTE,
                     hover_data=["행수", "톤_점유율_%"])
        fig.update_layout(height=max(360, top_n * 24),
                          margin=dict(t=10, b=10),
                          yaxis_title="", xaxis_title="총 톤")
        st.plotly_chart(fig, width="stretch")

        # bucket pie (group small commodities into named buckets)
        bucket_agg = (agg.groupby("bucket")["총_톤"].sum()
                      .reset_index().sort_values("총_톤", ascending=False))
        fig2 = px.pie(bucket_agg, names="bucket", values="총_톤", hole=0.5,
                      color="bucket", color_discrete_map=_KOM_BUCKET_PALETTE,
                      title="카테고리별 톤 점유율")
        fig2.update_layout(height=360, margin=dict(t=40, b=10))
        fig2.update_traces(textinfo="percent+label")
        st.plotly_chart(fig2, width="stretch")
        theme.dataframe(agg.head(50))
        _csv_button(agg, f"tanker_top_commodities_{snapshot}.csv",
                    label="📥 화물 종류 전체 CSV", key="tk_dl_kom")

    st.markdown("---")

    # ---------- OD pairs ----------
    st.subheader("Top 항로 (Origin → Destination, 톤 기준)")
    od_df = df.dropna(subset=["origin", "destination"]).copy()
    od_df["bton"] = pd.to_numeric(od_df["bongkar_ton"], errors="coerce").fillna(0)
    od_df["mton"] = pd.to_numeric(od_df["muat_ton"], errors="coerce").fillna(0)
    od_df["ton"] = od_df["bton"] + od_df["mton"]
    exclude_self = st.checkbox(
        "동일 항구 (origin = destination) 제외", value=True, key="tk_flow_self",
        help="LK3 데이터에는 일부 행이 동일 항구로 기록되어 있어 의미 있는 항로 분석에는 제외 권장.",
    )
    od_use = od_df[od_df["origin"] != od_df["destination"]] if exclude_self else od_df
    od_agg = (od_use.groupby(["origin", "destination"])
                    .agg(총_톤=("ton", "sum"), 행수=("ton", "count"))
                    .reset_index().sort_values("총_톤", ascending=False))
    if od_agg.empty:
        st.info("항로 데이터 없음")
    else:
        top_od = st.slider("Top N 항로", 10, 50, 20, key="tk_od_topn")
        theme.dataframe(od_agg.head(top_od))
        _csv_button(od_agg, f"tanker_routes_{snapshot}.csv",
                    label="📥 항로 전체 CSV", key="tk_dl_routes")
        # bar chart: top OD pairs
        topd = od_agg.head(top_od).copy()
        topd["pair"] = topd["origin"].astype(str) + " → " + topd["destination"].astype(str)
        topd = topd.sort_values("총_톤")
        fig = px.bar(topd, x="총_톤", y="pair", orientation="h",
                     color="총_톤", color_continuous_scale=theme.SCALES["blue"],
                     hover_data=["행수"])
        fig.update_layout(height=max(360, top_od * 22),
                          margin=dict(t=10, b=10),
                          yaxis_title="", xaxis_title="총 톤",
                          coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")

        # ---- Sankey diagram (flow direction) ----
        st.markdown("##### 🌐 항로 흐름 (Sankey)")
        sk_n = st.slider(
            "Sankey Top N 항로", 10, 50, 25,
            help="너무 많으면 시각적 노이즈; 25~30이 가독성 sweet spot",
            key="tk_sankey_topn",
        )
        _render_sankey(od_agg.head(sk_n))

        # ---- USD lane ranking (iter #32) ----
        st.markdown("---")
        _od_usd_lanes(df, od_agg)

    st.markdown("---")

    # ---------- Monthly seasonality ----------
    st.subheader("월별 계절성")
    seas = (df.assign(
                bton=pd.to_numeric(df["bongkar_ton"], errors="coerce").fillna(0),
                mton=pd.to_numeric(df["muat_ton"], errors="coerce").fillna(0))
              .groupby("period")
              .agg(BONGKAR_톤=("bton", "sum"),
                   MUAT_톤=("mton", "sum"),
                   행수=("period", "count"))
              .reset_index().sort_values("period"))
    if seas.empty:
        st.info("월별 데이터 없음")
    else:
        long = seas.melt(id_vars=["period"], value_vars=["BONGKAR_톤", "MUAT_톤"],
                         var_name="방향", value_name="톤")
        fig = px.bar(long, x="period", y="톤", color="방향", barmode="group",
                     color_discrete_map={"BONGKAR_톤": "#1e40af", "MUAT_톤": "#16a34a"})
        fig.update_layout(height=380, margin=dict(t=10, b=10),
                          xaxis_title="기간", yaxis_title="톤")
        st.plotly_chart(fig, width="stretch")

        # Year-over-year delta — by calendar month
        seas["year"] = seas["period"].str[:4]
        seas["month"] = seas["period"].str[5:7]
        if seas["year"].nunique() >= 2:
            piv = seas.pivot_table(index="month", columns="year",
                                   values=["BONGKAR_톤", "MUAT_톤"],
                                   aggfunc="sum").fillna(0)
            st.markdown("##### 연간 비교 (월별)")
            st.dataframe(piv.round(0), width="stretch")
        st.dataframe(seas.drop(columns=["year", "month"], errors="ignore"),
                     width="stretch", hide_index=True)

    # ---------- BBM monthly demand trend (iter #23) ----------
    st.markdown("---")
    _bbm_demand_trend(df)

    # ---------- Subclass tonnage trend (iter #24) ----------
    st.markdown("---")
    _subclass_tonnage_trend(df)

    # ---------- Cargo USD revenue proxy (iter #27) ----------
    st.markdown("---")
    _cargo_usd_revenue_proxy(df)


# Approximate USD/ton prices for major Indonesian tanker commodities (2025-26
# market-averaged). Rough magnitude — actual contracts vary by ±25%. Used as a
# dollar-magnitude proxy on top of ton-based metrics, NOT for valuation.
_COMMODITY_USD_PER_TON: dict[str, float] = {
    # Bucket label -> approximate USD per metric ton
    "Crude":           580.0,    # WTI/Brent $80/bbl × 7.25 bbl/ton
    "BBM-가솔린":      650.0,    # Pertalite/Pertamax retail-equivalent
    "BBM-디젤":        700.0,    # Solar/Biosolar including subsidy spread
    "BBM-항공유":      820.0,    # Jet A-1 (Avtur)
    "BBM-기타":        680.0,
    "벙커유":           540.0,    # Bunker fuel oil
    "CPO/팜오일":      850.0,    # CPO Malaysia/Indonesia FOB
    "팜 파생":         920.0,    # RBD Olein, Stearin, PKO etc.
    "기타 식용유":     900.0,
    "FAME":            1100.0,   # Biodiesel premium over diesel
    "LNG":             420.0,    # ~$10/MMBtu × ~52 MMBtu/ton (varies hugely)
    "LPG":             550.0,    # Propane/Butane mixed
    "Chemical":        1200.0,   # Generic chemical avg (heterogeneous)
    "Naphtha":         700.0,
    "Kerosene":        780.0,
    "아스팔트":         480.0,
    "기타":             500.0,    # generic fallback
}


def _cargo_usd_revenue_proxy(df: pd.DataFrame) -> None:
    """💵 Cargo USD revenue proxy = TON × commodity-price.

    Maps each cargo's commodity bucket to an approximate $/ton, computes
    proxy revenue, and surfaces by subclass + by operator + by month.
    Magnitude proxy only — for sizing, not for valuation.
    """
    st.subheader("💵 Cargo USD 매출 추정 (TON × commodity 단가)")

    if df.empty:
        st.info("USD 매출 추정 데이터 없음")
        return

    # Stack BONGKAR + MUAT into a single (period, operator, kom, ton) stream
    b = df[["period", "operator", "bongkar_kom", "bongkar_ton"]].rename(
        columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
    m = df[["period", "operator", "muat_kom", "muat_ton"]].rename(
        columns={"muat_kom": "kom", "muat_ton": "ton"})
    long = pd.concat([b, m], ignore_index=True).dropna(subset=["kom"])
    long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
    long = long[long["ton"] > 0].copy()
    long["bucket"] = long["kom"].map(_classify_kom_for_palette)
    long["price_usd"] = long["bucket"].map(
        lambda b: _COMMODITY_USD_PER_TON.get(b, 500.0))
    long["usd_revenue"] = long["ton"] * long["price_usd"]

    total_usd = float(long["usd_revenue"].sum())
    total_ton = float(long["ton"].sum())
    avg_price = total_usd / total_ton if total_ton > 0 else 0
    n_periods = long["period"].nunique()
    annual_usd = total_usd * (12.0 / max(n_periods, 1))

    cols = st.columns(4)
    kpi(cols[0], "USD 매출 합 (24mo)",
        f"${total_usd/1e9:.2f}B",
        help="TON × commodity 단가 합. ±25% 정확도, magnitude 지표")
    kpi(cols[1], "연간 환산",
        f"${annual_usd/1e9:.2f}B/yr",
        help="(24mo 합 / 24) × 12. 인도네시아 탱커 cargo 시장 연 USD 규모")
    kpi(cols[2], "평균 단가",
        f"${avg_price:,.0f}/t",
        help="총 USD / 총 톤")
    kpi(cols[3], "Top 카테고리",
        long.groupby("bucket")["usd_revenue"].sum()
            .sort_values(ascending=False).index[0]
        if not long.empty else "-")

    st.caption(
        "⚠️ **추정치 매뉴얼 단가**: Crude $580/t (Brent $80/bbl), "
        "Pertalite $650/t, Solar $700/t, Avtur $820/t, CPO $850/t, "
        "FAME $1,100/t, LNG $420/t, LPG $550/t, Chemical $1,200/t. "
        "실제 거래는 ±25% 변동 — magnitude 비교 용도 (절대 valuation 아님)."
    )

    # ---- USD by category ----
    st.markdown("##### 카테고리별 USD 매출 추정 (24mo)")
    bucket_agg = (long.groupby("bucket")
                       .agg(USD_M=("usd_revenue", lambda s: s.sum() / 1e6),
                            ton_M=("ton", lambda s: s.sum() / 1e6),
                            avg_USD_per_ton=("price_usd", "first"))
                       .reset_index().sort_values("USD_M", ascending=False))
    bucket_agg["USD_share_%"] = (bucket_agg["USD_M"] /
                                  bucket_agg["USD_M"].sum() * 100).round(1)
    bucket_agg["USD_M"] = bucket_agg["USD_M"].round(0)
    bucket_agg["ton_M"] = bucket_agg["ton_M"].round(2)

    cA, cB = st.columns([3, 2])
    with cA:
        plot = bucket_agg.head(15).copy().sort_values("USD_M")
        fig = px.bar(plot, x="USD_M", y="bucket", orientation="h",
                     color="bucket",
                     color_discrete_map=_KOM_BUCKET_PALETTE,
                     hover_data=["ton_M", "avg_USD_per_ton", "USD_share_%"])
        fig.update_layout(height=420, margin=dict(t=10, b=10),
                          xaxis_title="USD (M$)", yaxis_title="",
                          showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with cB:
        # Side-by-side: ton vs USD top 5 (shows whether high-volume = high-value)
        top5 = bucket_agg.head(5)
        compare = pd.DataFrame({
            "category": list(top5["bucket"]) * 2,
            "metric": ["톤 (M)"] * 5 + ["USD (M)"] * 5,
            "value": list(top5["ton_M"]) + list(top5["USD_M"]),
        })
        fig = px.bar(compare, x="category", y="value", color="metric",
                     barmode="group",
                     color_discrete_map={
                         "톤 (M)": "#0d9488", "USD (M)": "#1e40af"})
        fig.update_layout(height=420, margin=dict(t=10, b=10),
                          xaxis_tickangle=-30,
                          legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig, width="stretch")

    theme.dataframe(bucket_agg)
    _csv_button(bucket_agg, f"cargo_usd_buckets_{snapshot}.csv",
                key="tk_dl_usd_buckets")

    # ---- Top operators by USD revenue ----
    st.markdown("##### Top 운영사 USD 매출 추정")
    op_agg = (long.dropna(subset=["operator"])
                   .groupby("operator")
                   .agg(USD_M=("usd_revenue", lambda s: s.sum() / 1e6),
                        ton_M=("ton", lambda s: s.sum() / 1e6))
                   .reset_index().sort_values("USD_M", ascending=False).head(20))
    op_agg["USD_share_%"] = (op_agg["USD_M"] /
                              op_agg["USD_M"].sum() * 100).round(2)
    op_agg["USD_M"] = op_agg["USD_M"].round(0)
    op_agg["ton_M"] = op_agg["ton_M"].round(2)
    theme.dataframe(op_agg)
    _csv_button(op_agg, f"cargo_usd_operators_{snapshot}.csv",
                key="tk_dl_usd_op")

    # ---- Monthly USD trend ----
    st.markdown("##### 월별 USD 매출 추정 추이")
    monthly = (long.groupby(["period", "bucket"])["usd_revenue"]
                    .sum().reset_index())
    monthly["usd_M"] = monthly["usd_revenue"] / 1e6
    fig = px.area(monthly, x="period", y="usd_M", color="bucket",
                  color_discrete_map=_KOM_BUCKET_PALETTE,
                  labels={"period": "기간", "usd_M": "USD (M$)",
                          "bucket": "카테고리"})
    fig.update_layout(height=380, margin=dict(t=10, b=10),
                      legend=dict(orientation="h", y=-0.2,
                                  font=dict(size=10)))
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "**투자 의미**: ton 기준 vs USD 기준 시장 점유율 차이가 큰 카테고리 = "
        "프리미엄 commodity. 예: Chemical은 톤 점유율 작아도 USD 점유율 큼 → "
        "매출 비중 높지만 fleet 적은 → premium charter rate / margin ↑."
    )


# Stable color palette for tanker subclass timeseries (matches earlier views).
_SUBCLASS_PALETTE = {
    "Crude Oil":            "#0f172a",
    "Product":              "#1e40af",
    "Chemical":             "#7c3aed",
    "LPG":                  "#f59e0b",
    "LNG":                  "#0891b2",
    "FAME / Vegetable Oil": "#16a34a",
    "Water":                "#0ea5e9",
}


def _subclass_tonnage_trend(df: pd.DataFrame) -> None:
    """Per-subclass monthly tonnage trend over the 24mo window.

    Generalizes ``_bbm_demand_trend`` to every tanker commodity bucket:
    Crude Oil / Product / Chemical / LPG / LNG / FAME / Water. Uses the same
    snapshot-month partial filter for YoY computation.
    """
    st.subheader("📈 세부 분류 별 월간 톤 추이")

    if df.empty:
        st.info("subclass trend 데이터 없음")
        return

    # Stack BONGKAR + MUAT into one (period, kom, ton) stream
    b = df[["period", "bongkar_kom", "bongkar_ton"]].rename(
        columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
    m = df[["period", "muat_kom", "muat_ton"]].rename(
        columns={"muat_kom": "kom", "muat_ton": "ton"})
    long = pd.concat([b, m], ignore_index=True).dropna(subset=["kom"])
    long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
    long["subclass"] = long["kom"].map(_kom_to_subclass)

    g = (long.groupby(["period", "subclass"])["ton"].sum()
              .reset_index().sort_values("period"))
    if g.empty:
        st.info("월별 subclass 톤 데이터 없음")
        return

    # ---- KPI: latest period totals + 24mo accumulated ----
    latest_period = g["period"].max()
    by_sub_total = g.groupby("subclass")["ton"].sum().sort_values(ascending=False)
    by_sub_latest = g[g["period"] == latest_period].groupby("subclass")["ton"].sum()

    cols = st.columns(4)
    kpi(cols[0], "분석 subclass", fmt.fmt_int(g["subclass"].nunique()))
    kpi(cols[1], "전체 24mo 톤", fmt.fmt_ton(float(by_sub_total.sum())))
    kpi(cols[2], "Top subclass",
        f"{by_sub_total.index[0]} ({fmt.fmt_compact(float(by_sub_total.iloc[0]))})"
        if not by_sub_total.empty else "-")
    kpi(cols[3], f"Latest ({latest_period})",
        fmt.fmt_ton(float(by_sub_latest.sum()) if not by_sub_latest.empty else 0))

    # ---- Stacked area: full 24mo by subclass ----
    fig = px.area(
        g, x="period", y="ton", color="subclass",
        color_discrete_map=_SUBCLASS_PALETTE,
        labels={"period": "기간", "ton": "톤", "subclass": "세부 분류"},
    )
    fig.update_layout(height=400, margin=dict(t=10, b=10),
                      legend=dict(orientation="h", y=-0.2,
                                  font=dict(size=10)))
    st.plotly_chart(fig, width="stretch")

    # ---- Per-subclass YoY (snapshot-month partial filter applied) ----
    st.markdown("##### 세부 분류 별 평균 YoY (snapshot 월 partial 제외)")
    yoy_rows: list[dict] = []
    g["year"] = g["period"].str[:4]
    g["month"] = g["period"].str[5:7]
    snap_year, snap_mo = snapshot[:4], snapshot[5:7]

    # Min base filter: subclass must have ≥1M ton over 24mo to produce a
    # meaningful YoY (suppresses tiny-base outliers like 200,000% spikes).
    MIN_24MO_TON = 1_000_000
    for sub in by_sub_total.index:
        if float(by_sub_total[sub]) < MIN_24MO_TON:
            continue
        sub_g = g[g["subclass"] == sub]
        piv = sub_g.pivot_table(index="month", columns="year",
                                  values="ton", aggfunc="sum").fillna(0)
        if piv.empty or piv.shape[1] < 2:
            continue
        sorted_years = sorted(piv.columns)
        deltas = []
        for mo in piv.index:
            for i in range(len(sorted_years) - 1, 0, -1):
                ly, py = sorted_years[i], sorted_years[i - 1]
                if str(ly) == snap_year and mo == snap_mo:
                    continue
                if piv.at[mo, ly] > 0 and piv.at[mo, py] > 0:
                    deltas.append((piv.at[mo, ly] / piv.at[mo, py] - 1) * 100)
                    break
        if not deltas:
            continue
        avg = sum(deltas) / len(deltas)
        yoy_rows.append({
            "subclass": sub,
            "24mo_ton": float(by_sub_total[sub]),
            "share_%": float(by_sub_total[sub] / by_sub_total.sum() * 100),
            "valid_pairs": len(deltas),
            "YoY_avg_%": round(avg, 1),
        })

    if not yoy_rows:
        st.info("YoY 계산 가능한 subclass 없음 (다음 스냅샷부터 활성화)")
    else:
        ydf = pd.DataFrame(yoy_rows).sort_values("24mo_ton", ascending=False)
        ydf["share_%"] = ydf["share_%"].round(1)

        # YoY chart — green for growth, red for decline
        fig = px.bar(ydf.sort_values("YoY_avg_%"),
                     x="YoY_avg_%", y="subclass", orientation="h",
                     color="YoY_avg_%", color_continuous_scale=theme.SCALES["diverging"],
                     color_continuous_midpoint=0,
                     hover_data=["24mo_ton", "share_%", "valid_pairs"],
                     labels={"YoY_avg_%": "평균 YoY 변화 (%)",
                             "subclass": "세부 분류"})
        fig.add_vline(x=0, line_dash="dash", line_color="#475569",
                      line_width=1)
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")
        theme.dataframe(ydf)
        _csv_button(ydf, f"subclass_yoy_{snapshot}.csv",
                    key="tk_dl_subclass_yoy")
        st.caption(
            "**해석**: YoY > 0 = 해당 commodity 수요 성장 → tanker fleet 가동률 ↑ → "
            "신규 진입/매수 매력적. YoY < 0 = 수요 위축 → 차터 가격 압박. "
            "valid_pairs는 partial 월 제외 후 비교 가능했던 월 수 (보통 11)."
        )

    # ---- Raw monthly table (showable on demand) ----
    with st.expander("월별 raw 톤 표"):
        piv = g.pivot_table(index="period", columns="subclass",
                              values="ton", aggfunc="sum").fillna(0)
        st.dataframe(piv.round(0), width="stretch")
        _csv_button(piv.reset_index(), f"subclass_monthly_{snapshot}.csv",
                    key="tk_dl_subclass_monthly")


def _bbm_demand_trend(df: pd.DataFrame) -> None:
    """⛽ BBM (Indonesian fuel) monthly tonnage trend over the 24mo window.

    Pertamina BBM demand is the dominant cycle for ID tanker market — captures
    macro-economic activity (Pertalite = mass-market gasoline, Solar = diesel
    for industry/transport, Avtur = airline activity).
    """
    st.subheader("⛽ BBM (Pertamina 연료) 월별 수요 추이")

    if df.empty:
        st.info("BBM trend 계산할 데이터 없음")
        return

    # Stack BONGKAR + MUAT into single (period, kom, ton) stream
    b = df[["period", "bongkar_kom", "bongkar_ton"]].rename(
        columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
    m = df[["period", "muat_kom", "muat_ton"]].rename(
        columns={"muat_kom": "kom", "muat_ton": "ton"})
    long = pd.concat([b, m], ignore_index=True).dropna(subset=["kom"])
    long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
    long["bucket"] = long["kom"].map(_classify_kom_for_palette)

    # Filter to BBM (fuel) categories only
    BBM_BUCKETS = ("BBM-가솔린", "BBM-디젤", "BBM-항공유", "BBM-기타")
    bbm = long[long["bucket"].isin(BBM_BUCKETS)].copy()
    if bbm.empty:
        st.info("이 스냅샷에 BBM 카테고리 cargo 없음")
        return

    # Group by period × bucket
    g = (bbm.groupby(["period", "bucket"])["ton"].sum()
              .reset_index().sort_values("period"))

    # KPI
    total_bbm = float(g["ton"].sum())
    monthly_avg = total_bbm / max(g["period"].nunique(), 1)
    latest_period = g["period"].max()
    latest_total = float(g[g["period"] == latest_period]["ton"].sum())
    by_bucket = g.groupby("bucket")["ton"].sum().sort_values(ascending=False)
    top_bucket = by_bucket.index[0] if not by_bucket.empty else "-"

    cols = st.columns(4)
    kpi(cols[0], "BBM 총 톤 (24mo)", fmt.fmt_ton(total_bbm),
        help="Pertalite / Solar / Avtur / 기타 BBM의 24개월 누적")
    kpi(cols[1], "월 평균",
        fmt.fmt_ton(monthly_avg))
    kpi(cols[2], "최근 월 합", fmt.fmt_ton(latest_total),
        help=f"{latest_period} BBM cargo 톤")
    kpi(cols[3], "Top 카테고리", top_bucket,
        help=f"24개월 누적 {fmt.fmt_ton(float(by_bucket.iloc[0])) if not by_bucket.empty else '-'}")

    # Stacked area chart
    fig = px.area(
        g, x="period", y="ton", color="bucket",
        color_discrete_map=_KOM_BUCKET_PALETTE,
        category_orders={"bucket": list(BBM_BUCKETS)},
        labels={"period": "기간", "ton": "톤", "bucket": "BBM 카테고리"},
    )
    fig.update_layout(height=380, margin=dict(t=10, b=10),
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")

    # Side-by-side: monthly total + YoY comparison
    cA, cB = st.columns(2)
    with cA:
        st.markdown("##### 월별 BBM 총합 (line)")
        total_per_period = g.groupby("period")["ton"].sum().reset_index()
        fig = px.line(total_per_period, x="period", y="ton", markers=True,
                      labels={"period": "기간", "ton": "톤"})
        fig.update_traces(line_color="#dc2626", line_width=3)
        fig.update_layout(height=300, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")
    with cB:
        st.markdown("##### 카테고리별 누적 mix")
        bucket_totals = (by_bucket.reset_index()
                         .rename(columns={"bucket": "category", "ton": "총_톤"}))
        fig = px.pie(bucket_totals, names="category", values="총_톤",
                     color="category", color_discrete_map=_KOM_BUCKET_PALETTE,
                     hole=0.5)
        fig.update_traces(textinfo="percent+label", textposition="outside")
        fig.update_layout(height=300, margin=dict(t=10, b=10),
                          legend=dict(font=dict(size=10)))
        theme.donut_center(fig, fmt.fmt_ton(float(bucket_totals["총_톤"].sum())),
                           "BBM 누적")
        st.plotly_chart(fig, width="stretch")

    # YoY pivot if multi-year coverage
    g["year"] = g["period"].str[:4]
    g["month"] = g["period"].str[5:7]
    if g["year"].nunique() >= 2:
        st.markdown("##### 연간 비교 (월별 합산, 톤)")
        yoy = (g.groupby(["year", "month"])["ton"].sum()
                  .reset_index().pivot_table(
                      index="month", columns="year",
                      values="ton", aggfunc="sum").fillna(0))
        st.dataframe(yoy.round(0), width="stretch")
        # Compute YoY % using only month-pairs where BOTH years have full data
        # (avoids partial-month / missing-year skew). Use the highest year-pair
        # available per month, scanning newest → oldest. Skip the snapshot's
        # own (year, month) — it's the partial scrape month.
        if len(yoy.columns) >= 2:
            sorted_years = sorted(yoy.columns)
            snap_year, snap_mo = snapshot[:4], snapshot[5:7]
            yoy_rows = []
            for mo in yoy.index:
                pair = None
                for i in range(len(sorted_years) - 1, 0, -1):
                    ly, py = sorted_years[i], sorted_years[i - 1]
                    if str(ly) == snap_year and mo == snap_mo:
                        continue  # skip partial snapshot month
                    if yoy.at[mo, ly] > 0 and yoy.at[mo, py] > 0:
                        pair = (mo, py, ly,
                                (yoy.at[mo, ly] / yoy.at[mo, py] - 1) * 100)
                        break
                if pair is not None:
                    yoy_rows.append(pair)
            if yoy_rows:
                avg_yoy = sum(r[3] for r in yoy_rows) / len(yoy_rows)
                st.caption(
                    f"**평균 YoY 변화** (양년 동월 모두 데이터 있는 {len(yoy_rows)}개 월 평균): "
                    f"**{avg_yoy:+.1f}%** "
                    f"({'성장' if avg_yoy > 0 else '감소'} 추세). "
                    "비교 쌍은 월별로 가장 최근 가용 연도 쌍 사용 — "
                    "partial 월 / missing 연도 자동 제외."
                )

    st.dataframe(g.drop(columns=["year", "month"], errors="ignore"),
                 width="stretch", hide_index=True)
    _csv_button(g, f"bbm_monthly_demand_{snapshot}.csv",
                key="tk_dl_bbm")
    st.caption(
        "**해석 가이드**: BBM 수요 = Indonesian 거시경제 활동 프록시. "
        "**Pertalite ↑** = 소비자/소상공 활동 / **Solar ↑** = 산업·물류 활동 / "
        "**Avtur ↑** = 항공 운항 회복 / **YoY ↑** = 인도네시아 경제 성장 시그널 → "
        "Pertamina 차터 수요 증가 → 탱커 fleet 가동률 ↑ → 신규 진입 기회."
    )


# ------------- Tanker Port Competitiveness view (iteration #3) -------------

# Tanker class buckets keyed by max LOA (m) observed. Approximate industry
# cutoffs — useful as "what size class can this port accept?".
_TANKER_LOA_CLASS = (
    (320.0, "VLCC급 (≥320m)"),
    (250.0, "Suezmax/Aframax급 (250–320m)"),
    (200.0, "LR1/Panamax급 (200–250m)"),
    (160.0, "MR2/Handysize급 (160–200m)"),
    (110.0, "MR1/Coastal급 (110–160m)"),
    (0.0,   "Small/Barge (<110m)"),
)

def _classify_loa_bucket(loa: float | None) -> str:
    if loa is None or pd.isna(loa) or loa <= 0:
        return "Unknown"
    for cut, label in _TANKER_LOA_CLASS:
        if loa >= cut:
            return label
    return "Small/Barge (<110m)"


def _tanker_port_view():
    with st.spinner("탱커 화물 흐름 데이터 불러오는 중 (캐시 적중 시 즉시)…"):
        df = _tanker_cargo_flows(snapshot)
    if df.empty:
        st.info("이 스냅샷에는 탱커 화물 데이터가 없습니다.")
        return

    # Parse arrival/departure timestamps and compute dwell hours.
    tiba = pd.to_datetime(df["tiba_tanggal"],
                          format="%d-%m-%Y %H:%M:%S", errors="coerce")
    dep = pd.to_datetime(df["berangkat_tanggal"],
                         format="%d-%m-%Y %H:%M:%S", errors="coerce")
    dwell_h = (dep - tiba).dt.total_seconds() / 3600.0
    # Cap implausible values: < 0 (parse mistakes) or > 720h (30 days).
    dwell_h = dwell_h.where((dwell_h >= 0) & (dwell_h <= 720))

    df = df.assign(
        dwell_h=dwell_h,
        ton_total=(pd.to_numeric(df["bongkar_ton"], errors="coerce").fillna(0)
                   + pd.to_numeric(df["muat_ton"], errors="coerce").fillna(0)),
    )

    # ---- KPI hero ----
    n_ports = df["kode_pelabuhan"].nunique()
    med_dwell = float(df["dwell_h"].median()) if df["dwell_h"].notna().any() else None
    total_ton = float(df["ton_total"].sum())
    mean_dwell = float(df["dwell_h"].mean()) if df["dwell_h"].notna().any() else None
    cols = st.columns(5)
    kpi(cols[0], "탱커 기항 항구", fmt.fmt_int(n_ports),
        help="이 윈도우에서 탱커가 1회 이상 기항한 인도네시아 항구 수")
    kpi(cols[1], "전체 행 수", fmt.fmt_int(len(df)),
        help="LK3 양식의 탱커 행 (1행 ≈ 1 항해의 단일 화물 항목)")
    kpi(cols[2], "총 거래량", fmt.fmt_ton(total_ton),
        help="BONGKAR + MUAT 합계. 24개월 누적")
    kpi(cols[3], "Dwell 중앙값",
        fmt.fmt_dwell(med_dwell),
        help="TIBA → BERANGKAT 시각 차의 50 percentile. 항만 효율 프록시")
    kpi(cols[4], "Dwell 평균",
        fmt.fmt_dwell(mean_dwell),
        help="평균 체류 시간. 중앙값과 차이가 크면 long-tail 정체 구간 존재")
    st.caption(
        "Dwell time = TIBA(도착) → BERANGKAT(출항) 시각 차이. "
        "운영 효율 / 항만 혼잡도 프록시 지표."
    )

    st.markdown("---")

    # ---- per-port aggregation ----
    ports = _ports()
    name_lookup = dict(zip(ports["kode_pelabuhan"], ports["nama_pelabuhan"]))

    g = (df.groupby("kode_pelabuhan")
           .agg(기항수=("kapal", "size"),
                고유_탱커=("kapal", "nunique"),
                고유_운영사=("operator", "nunique"),
                BONGKAR_톤=("bongkar_ton", "sum"),
                MUAT_톤=("muat_ton", "sum"),
                Max_LOA=("loa", "max"),
                Mean_LOA=("loa", "mean"),
                Max_DRAFT=("draft_max", "max"),
                Median_DRAFT=("draft_max", "median"),
                Median_Dwell_h=("dwell_h", "median"),
                Mean_Dwell_h=("dwell_h", "mean"),
                Total_TON=("ton_total", "sum"))
           .reset_index())
    g["nama_pelabuhan"] = g["kode_pelabuhan"].map(name_lookup)
    g["TON_per_call"] = (g["Total_TON"] / g["기항수"]).round(0)
    g["Class_capacity"] = g["Max_LOA"].map(_classify_loa_bucket)

    # ---- top ports by metric ----
    st.subheader("Top 항구")
    metric_label = st.radio(
        "정렬 기준",
        ["기항수", "총 거래량 (톤)", "고유 탱커 수", "Dwell 중앙값"],
        horizontal=True, key="tk_port_metric",
    )
    metric_col = {
        "기항수": "기항수", "총 거래량 (톤)": "Total_TON",
        "고유 탱커 수": "고유_탱커", "Dwell 중앙값": "Median_Dwell_h",
    }[metric_label]
    asc = (metric_col == "Median_Dwell_h")  # shorter dwell = better
    top_n_p = st.slider("Top N 항구", 10, 50, 20, key="tk_port_topn")
    g_top = g.sort_values(metric_col, ascending=asc).head(top_n_p)

    fig = px.bar(g_top.sort_values(metric_col, ascending=not asc),
                 x=metric_col, y="kode_pelabuhan", orientation="h",
                 color="Class_capacity",
                 hover_data=["nama_pelabuhan", "고유_탱커", "Total_TON",
                             "Max_LOA", "Max_DRAFT", "Median_Dwell_h"])
    fig.update_layout(height=max(400, top_n_p * 22),
                      margin=dict(t=10, b=10),
                      yaxis_title="", xaxis_title=metric_label)
    st.plotly_chart(fig, width="stretch")

    show_cols = ["kode_pelabuhan", "nama_pelabuhan", "기항수", "고유_탱커",
                 "고유_운영사", "Total_TON", "TON_per_call",
                 "Max_LOA", "Max_DRAFT", "Class_capacity",
                 "Median_Dwell_h", "Mean_Dwell_h"]
    show_cols = [c for c in show_cols if c in g_top.columns]
    st.dataframe(g_top[show_cols].round(2),
                 width="stretch", hide_index=True)
    _csv_button(g[show_cols].round(2),
                f"tanker_ports_{snapshot}.csv",
                label="📥 항구 전체 CSV", key="tk_dl_ports")

    st.markdown("---")

    # ---- port capacity matrix: max LOA / max draft → class ----
    st.subheader("항구별 수용 가능 탱커 클래스 (관측된 최대 LOA 기준)")
    cls_dist = (g.groupby("Class_capacity")
                  .agg(항구수=("kode_pelabuhan", "nunique"),
                       총_기항=("기항수", "sum"))
                  .reset_index())
    # Order classes large → small for readability
    order = [lbl for _, lbl in _TANKER_LOA_CLASS]
    cls_dist["__order"] = cls_dist["Class_capacity"].map(
        {lbl: i for i, lbl in enumerate(order)})
    cls_dist = cls_dist.sort_values("__order").drop(columns="__order")
    c1, c2 = st.columns([1, 1])
    with c1:
        fig = px.bar(cls_dist, x="Class_capacity", y="항구수",
                     color="Class_capacity",
                     labels={"Class_capacity": "클래스", "항구수": "항구 수"})
        fig.update_layout(height=320, margin=dict(t=10, b=10), showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with c2:
        theme.dataframe(cls_dist)
    st.caption(
        "예: 'VLCC급'으로 분류된 항구 = 24개월 LK3에서 LOA ≥ 320m 탱커가 "
        "실제 입항한 적이 있는 항구. 자체 시설 한계가 아닌 _관측 기반_ 추정치."
    )

    st.markdown("---")

    # ---- dwell time distribution (Top-N ports) ----
    st.subheader("Dwell time 분포 (Top 20 항구)")
    top20_codes = g.sort_values("기항수", ascending=False).head(20)["kode_pelabuhan"]
    sub = df[df["kode_pelabuhan"].isin(top20_codes)
             & df["dwell_h"].notna()].copy()
    if not sub.empty:
        # Order ports by median dwell (low → high) so chart reads left-to-right
        port_order = (sub.groupby("kode_pelabuhan")["dwell_h"].median()
                         .sort_values().index.tolist())
        fig = px.box(sub, x="kode_pelabuhan", y="dwell_h",
                     category_orders={"kode_pelabuhan": port_order},
                     points=False)
        fig.update_layout(height=380, margin=dict(t=10, b=10),
                          xaxis_title="항구 코드", yaxis_title="체류 시간 (h)",
                          yaxis=dict(range=[0, 240]))  # hide 240h+ outliers
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "박스: 25–75 percentile, 중앙선 = 중앙값. 240h 이상은 시각화 범위 밖. "
            "낮을수록 항만 회전율↑."
        )

    st.markdown("---")

    # ---- volume per call ----
    st.subheader("기항 1회당 평균 거래량")
    vol = g[g["기항수"] >= 30].copy()  # filter low-frequency ports
    vol = vol.sort_values("TON_per_call", ascending=False).head(20)
    if not vol.empty:
        fig = px.bar(vol.sort_values("TON_per_call"), y="kode_pelabuhan",
                     x="TON_per_call", orientation="h",
                     color="TON_per_call", color_continuous_scale=theme.SCALES["blue"],
                     hover_data=["nama_pelabuhan", "기항수", "Class_capacity"])
        fig.update_layout(height=460, margin=dict(t=10, b=10),
                          yaxis_title="", xaxis_title="평균 톤/기항",
                          coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "기항수 ≥ 30 항구만 표시 (단발성 대형 양하 왜곡 방지). "
            "수치가 클수록 대형 탱커 위주 / 단위 거래량 큰 시장."
        )

    # ---- Geographic map (iteration #20) ----
    st.markdown("---")
    _port_geo_map(g)

    # ---- STS transfer hubs (iteration #26) ----
    st.markdown("---")
    _port_sts_pattern(df)

    # ---- Port mass-balance (iteration #28) ----
    st.markdown("---")
    _port_mass_balance(df)

    # ---- Operator HHI per port (iteration #30) ----
    st.markdown("---")
    _port_operator_hhi(df)


def _port_operator_hhi(df: pd.DataFrame) -> None:
    """🚧 Operator-share HHI per port — entry-barrier mapping.

    For each port, compute HHI of operator ton-shares. High HHI =
    monopolized port (single operator dominates). Low HHI = competitive
    port. Investor decision: target competitive ports for entry, target
    monopolized port operators for partnership/acquisition.
    """
    st.subheader("🚧 항구별 운영사 집중도 (Entry-barrier 매핑)")

    if df.empty or "operator" not in df.columns:
        st.info("운영사 HHI 분석할 데이터 없음")
        return

    sub = df.dropna(subset=["operator", "kode_pelabuhan"]).copy()
    sub["op_norm"] = sub["operator"].map(_norm_company)
    sub["ton_total"] = (pd.to_numeric(sub["bongkar_ton"], errors="coerce").fillna(0)
                        + pd.to_numeric(sub["muat_ton"], errors="coerce").fillna(0))
    sub = sub[sub["ton_total"] > 0]
    if sub.empty:
        st.info("ton > 0 데이터 없음")
        return

    # Per-port × operator ton totals
    g = (sub.groupby(["kode_pelabuhan", "op_norm"])["ton_total"]
             .sum().reset_index())

    # HHI per port
    rows = []
    for port, port_g in g.groupby("kode_pelabuhan"):
        total = float(port_g["ton_total"].sum())
        if total <= 0:
            continue
        shares = port_g["ton_total"] / total * 100
        hhi = float((shares ** 2).sum())
        top1 = float(shares.max())
        top1_name = port_g.loc[port_g["ton_total"].idxmax(), "op_norm"]
        n_op = len(port_g)
        rows.append({
            "kode_pelabuhan": port, "HHI": round(hhi, 0),
            "Top1_share_%": round(top1, 1),
            "Top1_op": top1_name,
            "n_operators": int(n_op),
            "total_ton": total,
        })
    if not rows:
        st.info("HHI 계산 가능한 port 없음")
        return

    pdf = pd.DataFrame(rows)

    # Classify
    def _band(h: float) -> str:
        if h >= 5000:
            return "Monopolized (≥5000)"
        if h >= 2500:
            return "Oligopoly (2500-5000)"
        if h >= 1500:
            return "Moderate (1500-2500)"
        return "Competitive (<1500)"

    pdf["band"] = pdf["HHI"].map(_band)
    ports_meta = _ports()
    pdf = pdf.merge(ports_meta, on="kode_pelabuhan", how="left")

    # Filter to ports with meaningful traffic
    min_ton = st.slider(
        "최소 거래량 필터 (톤)",
        0, 5_000_000, 100_000, 100_000,
        key="tk_phhi_min",
        help="작은 항구의 1-operator artifact 제거",
    )
    pdf_f = pdf[pdf["total_ton"] >= min_ton].copy()
    if pdf_f.empty:
        st.info("필터 조건 통과 항구 없음")
        return

    # KPI
    n_mono = int(pdf_f["band"].str.startswith("Monop").sum())
    n_olig = int(pdf_f["band"].str.startswith("Olig").sum())
    n_comp = int(pdf_f["band"].str.startswith("Compet").sum())
    n_mod = int(pdf_f["band"].str.startswith("Moder").sum())
    median_hhi = float(pdf_f["HHI"].median())
    cols = st.columns(4)
    kpi(cols[0], "분석 항구", fmt.fmt_int(len(pdf_f)),
        help=f"≥ {min_ton:,} 톤 항구")
    kpi(cols[1], "Monopolized", fmt.fmt_int(n_mono),
        help="HHI ≥ 5000 — 사실상 단일 운영사 지배")
    kpi(cols[2], "Competitive", fmt.fmt_int(n_comp),
        help="HHI < 1500 — 신규 진입 매력도 ↑")
    kpi(cols[3], "Median HHI",
        f"{median_hhi:,.0f}",
        help="중앙값. 인도네시아 항구 평균 entry-barrier 수준")

    # Distribution histogram
    fig = px.histogram(pdf_f, x="HHI", nbins=30, color="band",
                       color_discrete_map={
                           "Monopolized (≥5000)": "#dc2626",
                           "Oligopoly (2500-5000)": "#f59e0b",
                           "Moderate (1500-2500)": "#eab308",
                           "Competitive (<1500)": "#16a34a",
                       },
                       category_orders={"band": [
                           "Competitive (<1500)", "Moderate (1500-2500)",
                           "Oligopoly (2500-5000)", "Monopolized (≥5000)",
                       ]},
                       labels={"HHI": "운영사 HHI", "count": "항구 수"})
    fig.update_layout(height=320, margin=dict(t=10, b=10),
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")

    # Top tables
    cA, cB = st.columns(2)
    show_cols = ["kode_pelabuhan", "nama_pelabuhan", "HHI", "band",
                 "Top1_op", "Top1_share_%", "n_operators", "total_ton"]
    show_cols = [c for c in show_cols if c in pdf_f.columns]
    with cA:
        st.markdown("##### 🚧 Top 15 Monopolized (진입 어려운 항구)")
        mono = pdf_f[pdf_f["band"].str.startswith("Monop")] \
            .sort_values("total_ton", ascending=False).head(15)
        if not mono.empty:
            disp = mono[show_cols].copy()
            disp["total_ton"] = disp["total_ton"].round(0)
            theme.dataframe(disp)
    with cB:
        st.markdown("##### 🟢 Top 15 Competitive (진입 매력 ↑)")
        comp = pdf_f[pdf_f["band"].str.startswith("Compet")] \
            .sort_values("total_ton", ascending=False).head(15)
        if not comp.empty:
            disp = comp[show_cols].copy()
            disp["total_ton"] = disp["total_ton"].round(0)
            theme.dataframe(disp)

    # Full table + CSV
    with st.expander("전체 port HHI 표"):
        full = pdf_f[show_cols].copy().sort_values("HHI", ascending=False)
        full["total_ton"] = full["total_ton"].round(0)
        theme.dataframe(full)
        _csv_button(full, f"port_operator_hhi_{snapshot}.csv",
                    key="tk_dl_phhi")
    st.caption(
        "**투자 의미**: Monopolized 항구 → Top1 운영사와 charter agreement / "
        "M&A 협상이 사실상 진입 유일 통로. Competitive 항구 → 한국선이 직접 cargo "
        "계약 영업 가능. Oligopoly = Top 2-3 운영자 인수 후 통합 가능성."
    )


def _port_mass_balance(df: pd.DataFrame) -> None:
    """⚖️ Port mass-balance: BONGKAR(양하) vs MUAT(적재) per port.

    Net positive ton = import-dominant (refineries, distribution hubs).
    Net negative ton = export-dominant (production terminals).
    Near zero = transshipment / STS hubs.
    """
    st.subheader("⚖️ 항구별 BONGKAR vs MUAT 균형")

    if df.empty:
        st.info("Mass-balance 분석할 데이터 없음")
        return

    bton = pd.to_numeric(df["bongkar_ton"], errors="coerce").fillna(0)
    mton = pd.to_numeric(df["muat_ton"], errors="coerce").fillna(0)

    g = (df.assign(bton=bton, mton=mton)
            .groupby("kode_pelabuhan")
            .agg(BONGKAR=("bton", "sum"),
                 MUAT=("mton", "sum"),
                 행수=("kapal", "size"),
                 고유_탱커=("kapal", "nunique"))
            .reset_index())
    g["NET"] = g["BONGKAR"] - g["MUAT"]
    g["TOTAL"] = g["BONGKAR"] + g["MUAT"]
    # Avoid div-by-zero for tiny ports — keep result as plain float so .round works
    safe_total = g["TOTAL"].where(g["TOTAL"] > 0)
    g["balance_pct"] = (g["NET"] / safe_total * 100).astype(float).round(1)

    # Classify
    def _label(pct: float | None) -> str:
        if pct is None or pd.isna(pct):
            return "Unknown"
        if pct >= 60:
            return "Import-dominant (양하 ≥ 60%)"
        if pct <= -60:
            return "Export-dominant (적재 ≥ 60%)"
        if -20 <= pct <= 20:
            return "Balanced / Transshipment"
        return "Mixed"

    g["dominance"] = g["balance_pct"].map(_label)
    ports = _ports()
    g = g.merge(ports, on="kode_pelabuhan", how="left")

    # Filter to ports with meaningful traffic
    min_total = st.slider(
        "최소 거래량 필터 (BONGKAR + MUAT, 톤)",
        0, 5_000_000, 100_000, 100_000,
        help="작은 anchorage의 small-base 노이즈 차단",
        key="tk_balance_min",
    )
    sub = g[g["TOTAL"] >= min_total].copy()
    if sub.empty:
        st.info("필터 조건 통과 항구 없음")
        return

    # KPI
    n_imp = int((sub["dominance"].str.startswith("Import")).sum())
    n_exp = int((sub["dominance"].str.startswith("Export")).sum())
    n_bal = int((sub["dominance"].str.startswith("Balanced")).sum())
    cols = st.columns(4)
    kpi(cols[0], "분석 항구", fmt.fmt_int(len(sub)),
        help=f"BONGKAR+MUAT ≥ {min_total:,} 톤 항구만 분석")
    kpi(cols[1], "Import-dominant", fmt.fmt_int(n_imp),
        help="양하 ≥ 60% — 정유소·소비시장")
    kpi(cols[2], "Export-dominant", fmt.fmt_int(n_exp),
        help="적재 ≥ 60% — 생산·수출 터미널")
    kpi(cols[3], "Balanced/Transshipment", fmt.fmt_int(n_bal),
        help="±20% 이내 — STS hub / transshipment")

    # ---- Bidirectional bar chart (top 25 by total) ----
    top_p = sub.sort_values("TOTAL", ascending=False).head(25).copy()
    top_p["BONGKAR_neg"] = -top_p["BONGKAR"]  # plot import as negative for visual symmetry
    top_p["MUAT_pos"] = top_p["MUAT"]
    long_p = pd.concat([
        top_p[["kode_pelabuhan", "BONGKAR_neg"]].assign(direction="BONGKAR (양하)")
                                                    .rename(columns={"BONGKAR_neg": "ton"}),
        top_p[["kode_pelabuhan", "MUAT_pos"]].assign(direction="MUAT (적재)")
                                                .rename(columns={"MUAT_pos": "ton"}),
    ], ignore_index=True)
    fig = px.bar(long_p, x="ton", y="kode_pelabuhan",
                 color="direction", orientation="h",
                 color_discrete_map={"BONGKAR (양하)": "#dc2626",
                                       "MUAT (적재)": "#16a34a"},
                 category_orders={"kode_pelabuhan":
                                    top_p.sort_values("TOTAL")["kode_pelabuhan"].tolist()})
    fig.update_layout(height=560, margin=dict(t=10, b=10),
                      xaxis_title="톤 (좌 음수 = 양하 / 우 양수 = 적재)",
                      yaxis_title="",
                      legend=dict(orientation="h", y=-0.1))
    fig.add_vline(x=0, line_color="#475569", line_width=1)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "**좌측 빨강 = BONGKAR**(양하·import) / **우측 녹색 = MUAT**(적재·export). "
        "막대 길이 비대칭 = 그 항구가 import-skewed 또는 export-skewed."
    )

    # ---- Tables: top import + top export + most balanced ----
    show_cols = ["kode_pelabuhan", "nama_pelabuhan", "BONGKAR", "MUAT",
                 "NET", "balance_pct", "TOTAL", "dominance"]
    show_cols = [c for c in show_cols if c in sub.columns]
    cA, cB = st.columns(2)
    with cA:
        st.markdown("##### 🔻 Top 10 Import-dominant (수입항)")
        imp = sub[sub["dominance"].str.startswith("Import")].sort_values(
            "BONGKAR", ascending=False).head(10)
        if not imp.empty:
            disp = imp[show_cols].copy()
            for col in ("BONGKAR", "MUAT", "NET", "TOTAL"):
                if col in disp.columns:
                    disp[col] = disp[col].round(0)
            theme.dataframe(disp)
    with cB:
        st.markdown("##### 🔺 Top 10 Export-dominant (수출항)")
        exp = sub[sub["dominance"].str.startswith("Export")].sort_values(
            "MUAT", ascending=False).head(10)
        if not exp.empty:
            disp = exp[show_cols].copy()
            for col in ("BONGKAR", "MUAT", "NET", "TOTAL"):
                if col in disp.columns:
                    disp[col] = disp[col].round(0)
            theme.dataframe(disp)

    # Full table + CSV
    with st.expander("전체 항구 mass-balance 표"):
        full = sub[show_cols].copy()
        for col in ("BONGKAR", "MUAT", "NET", "TOTAL"):
            if col in full.columns:
                full[col] = full[col].round(0)
        full = full.sort_values("TOTAL", ascending=False)
        theme.dataframe(full)
        _csv_button(full, f"port_mass_balance_{snapshot}.csv",
                    key="tk_dl_balance")
    st.caption(
        "**투자 의미**: 수입항(BBM/Crude 양하) = Pertamina 정유망 거점, "
        "차터-인 contract 협상 후보. 수출항(CPO·LNG·LPG 적재) = 외국선 의존도 큰 곳, "
        "한국선 진입 가장 직접적 타깃. Balanced 항구는 STS hub — "
        "차터 operator 매수 시 첫 번째 target."
    )

    # ---- Commodity diversity per port (iteration #14) ----
    st.markdown("---")
    _port_commodity_diversity(df)


def _port_sts_pattern(df: pd.DataFrame) -> None:
    """🔄 Ship-to-ship (STS) transfer pattern analysis.

    LK3 rows with origin == destination + ton > 0 indicate STS transfers
    (vessel arrived at port X, departed back to X with cargo). Indonesia
    relies heavily on STS for fuel distribution + palm-oil export.
    """
    st.subheader("🔄 STS (Ship-to-Ship) 트랜스퍼 패턴")
    if df.empty:
        st.info("STS 분석할 데이터 없음")
        return

    sts = df[(df["origin"].notna()) & (df["destination"].notna())
              & (df["origin"] == df["destination"])
              & (df["ton_total"] > 0)].copy()
    if sts.empty:
        st.info("STS 패턴 행 없음")
        return

    sts_rows = len(sts)
    sts_share = sts_rows / len(df) * 100
    sts_ton = float(sts["ton_total"].sum())
    sts_ton_share = sts_ton / float(df["ton_total"].sum()) * 100 \
        if df["ton_total"].sum() > 0 else 0
    cols = st.columns(4)
    kpi(cols[0], "STS 행수", fmt.fmt_int(sts_rows),
        help="origin = destination 이고 ton > 0인 LK3 행")
    kpi(cols[1], "STS 행 점유율",
        fmt.fmt_pct(sts_share),
        help="전체 탱커 행 중 STS 패턴 비율")
    kpi(cols[2], "STS 총 톤",
        fmt.fmt_ton(sts_ton))
    kpi(cols[3], "STS 톤 점유율",
        fmt.fmt_pct(sts_ton_share),
        help="전체 탱커 cargo ton 중 STS가 차지하는 비율")

    st.caption(
        "**STS = Ship-to-Ship transfer**: 같은 항구에서 두 선박 간 cargo 이송. "
        "인도네시아는 정유소 외 anchorage / STS hub에서 광범위하게 활용. "
        "한국 STS 전문 operator (예: 광양만 STS / 울산항 STS) 진출 후보 hub."
    )

    # ---- Top STS hubs ----
    ports_meta = _ports()
    hubs = (sts.groupby("kode_pelabuhan")
                .agg(STS_rows=("kapal", "size"),
                     STS_ton=("ton_total", "sum"),
                     unique_kapal=("kapal", "nunique"),
                     unique_ops=("operator", "nunique"))
                .reset_index()
                .sort_values("STS_ton", ascending=False)
                .merge(ports_meta, on="kode_pelabuhan", how="left"))
    top_n = st.slider("STS Top N hubs", 10, 30, 15, key="tk_sts_topn")
    top_h = hubs.head(top_n).copy()
    top_h["STS_ton"] = top_h["STS_ton"].round(0)
    cols_show = ["kode_pelabuhan", "nama_pelabuhan", "STS_rows",
                 "unique_kapal", "unique_ops", "STS_ton"]
    cols_show = [c for c in cols_show if c in top_h.columns]
    theme.dataframe(top_h[cols_show])

    # ---- Side-by-side: top hubs bar + STS commodity mix ----
    cA, cB = st.columns([3, 2])
    with cA:
        plot_h = top_h.head(15).copy().sort_values("STS_ton")
        fig = px.bar(plot_h, x="STS_ton", y="kode_pelabuhan",
                     orientation="h", color="STS_ton",
                     color_continuous_scale=theme.SCALES["blue"],
                     hover_data=["nama_pelabuhan", "unique_kapal", "unique_ops"])
        fig.update_layout(height=460, margin=dict(t=10, b=10),
                          coloraxis_showscale=False, yaxis_title="",
                          xaxis_title="STS 톤")
        st.plotly_chart(fig, width="stretch")
    with cB:
        # STS commodity mix
        b = sts[["bongkar_kom", "bongkar_ton"]].rename(
            columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
        m = sts[["muat_kom", "muat_ton"]].rename(
            columns={"muat_kom": "kom", "muat_ton": "ton"})
        long = pd.concat([b, m], ignore_index=True).dropna(subset=["kom"])
        long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
        long["bucket"] = long["kom"].map(_classify_kom_for_palette)
        mix = (long.groupby("bucket")["ton"].sum()
                   .reset_index().sort_values("ton", ascending=False))
        mix = mix[mix["ton"] > 0]
        if not mix.empty:
            fig = px.pie(mix, names="bucket", values="ton",
                         color="bucket",
                         color_discrete_map=_KOM_BUCKET_PALETTE, hole=0.5,
                         title="STS 화물 카테고리 mix")
            fig.update_traces(textinfo="percent+label")
            fig.update_layout(height=460, margin=dict(t=40, b=10),
                              legend=dict(font=dict(size=9)))
            st.plotly_chart(fig, width="stretch")

    # ---- Top STS operators ----
    st.markdown("##### Top STS 운영사")
    op_sts = (sts.dropna(subset=["operator"])
                  .groupby("operator")
                  .agg(STS_rows=("kapal", "size"),
                       STS_ton=("ton_total", "sum"),
                       unique_hubs=("kode_pelabuhan", "nunique"))
                  .reset_index().sort_values("STS_ton", ascending=False).head(15))
    op_sts["STS_ton"] = op_sts["STS_ton"].round(0)
    op_sts["STS_share_%"] = (op_sts["STS_ton"] /
                              max(op_sts["STS_ton"].sum(), 1) * 100).round(2)
    theme.dataframe(op_sts)
    _csv_button(op_sts, f"sts_operators_{snapshot}.csv",
                key="tk_dl_sts_op")
    st.caption(
        "STS는 인도네시아 fuel/palm-oil 분배 핵심 메커니즘. "
        "Pertamina Trans Kontinental이 STS도 지배적이지만 (50%+), "
        "Energy Marine Indonesia / Seroja Jaya 등 specialty STS operator도 존재 — "
        "한국 STS specialty 회사의 partnership / 인수 후보군."
    )


def _port_geo_map(g: pd.DataFrame) -> None:
    """Indonesia archipelago bubble map of port tanker activity.

    `g` must have columns: kode_pelabuhan, nama_pelabuhan, 기항수, Total_TON,
    Max_LOA (the per-port aggregate produced by `_tanker_port_view`).
    Bubble size = total ton; color = max LOA (port draft capacity proxy).
    """
    st.subheader("🗺️ 인도네시아 항구 지도")

    # Attach coordinates
    rows = []
    missing = []
    for r in g.itertuples(index=False):
        coord = _PORT_COORDS.get(r.kode_pelabuhan)
        if coord is None:
            missing.append({
                "code": r.kode_pelabuhan,
                "nama": getattr(r, "nama_pelabuhan", None),
                "기항수": int(r.기항수),
                "총_톤": float(r.Total_TON),
            })
            continue
        rows.append({
            "kode_pelabuhan": r.kode_pelabuhan,
            "nama_pelabuhan": getattr(r, "nama_pelabuhan", None) or "-",
            "기항수": int(r.기항수),
            "총_톤": float(r.Total_TON),
            "Max_LOA": float(r.Max_LOA) if pd.notna(r.Max_LOA) else None,
            "Class_capacity": getattr(r, "Class_capacity", "-"),
            "lat": coord[0], "lon": coord[1],
        })
    if not rows:
        st.info("좌표 매핑 가능한 항구가 없습니다.")
        return
    plot_df = pd.DataFrame(rows)

    # Total mapped vs unmapped
    total_ton_mapped = plot_df["총_톤"].sum()
    total_ton_missing = sum(m["총_톤"] for m in missing)
    cov = total_ton_mapped / max(total_ton_mapped + total_ton_missing, 1) * 100
    cN = st.columns(3)
    kpi(cN[0], "지도 표시 항구", fmt.fmt_int(len(plot_df)),
        help=f"총 {len(plot_df) + len(missing)}개 항구 중")
    kpi(cN[1], "톤 커버리지", fmt.fmt_pct(cov),
        help="지도에 표시된 항구의 톤 합 / 전체 톤 합")
    kpi(cN[2], "좌표 미보유", fmt.fmt_int(len(missing)),
        help="lat/lon 매핑 없음 — 보통 작은 항구")

    fig = px.scatter_geo(
        plot_df, lat="lat", lon="lon",
        size="총_톤", color="Max_LOA",
        hover_name="kode_pelabuhan",
        hover_data={
            "nama_pelabuhan": True, "기항수": ":,", "총_톤": ":,.0f",
            "Max_LOA": ":.0f", "Class_capacity": True,
            "lat": False, "lon": False,
        },
        color_continuous_scale=theme.SCALES["teal"],
        size_max=40,
    )
    # Manually focus on Indonesia (lon ~94-141, lat ~-11 to 6)
    fig.update_layout(
        height=520, margin=dict(t=10, b=10, l=10, r=10),
        geo=dict(
            scope="asia",
            projection_type="natural earth",
            showcountries=True, showcoastlines=True, showland=True,
            landcolor="#f8fafc",
            countrycolor="#cbd5e1",
            coastlinecolor="#94a3b8",
            lataxis=dict(range=[-12, 8]),
            lonaxis=dict(range=[94, 142]),
        ),
        coloraxis_colorbar=dict(title="Max LOA (m)"),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "버블 크기 = 24개월 BONGKAR+MUAT 톤 합. 색상 = 관측된 최대 LOA "
        "(항만 capacity 프록시). 🇰🇷 Korean-flag 탱커는 별도 표시 안 됨 — "
        "🏢 운영사 탭의 한국계 노출 섹션 참조."
    )

    if missing:
        with st.expander(f"좌표 미보유 항구 {len(missing)}개"):
            mdf = pd.DataFrame(missing).sort_values("총_톤", ascending=False)
            theme.dataframe(mdf)
            st.caption(
                "이 항구들은 dashboard/app.py::_PORT_COORDS 사전에 lat/lon 추가 시 자동으로 지도에 표시됩니다."
            )


def _port_commodity_diversity(df: pd.DataFrame) -> None:
    """Per-port commodity diversity via Shannon entropy.

    Effective number of commodity buckets ``= exp(H)`` where ``H`` is the
    Shannon entropy of ton-share across the bucket categories at the port.
    Investors care about this because a port serving a single commodity
    (e.g., crude only) has a very different risk profile from a diversified
    hub.
    """
    import numpy as np
    st.subheader("항구별 화물 다양성 (Shannon entropy)")

    # Each row contributes its bongkar bucket and muat bucket separately
    # because a row can record both a discharge and a load — both are
    # "commodity activity" signals at this port.
    b = df[["kode_pelabuhan", "bongkar_kom", "bton"]].rename(
        columns={"bongkar_kom": "kom", "bton": "ton"})
    m = df[["kode_pelabuhan", "muat_kom", "mton"]].rename(
        columns={"muat_kom": "kom", "mton": "ton"})
    long = pd.concat([b, m], ignore_index=True).dropna(subset=["kom"])
    long = long[long["ton"] > 0].copy()
    if long.empty:
        st.info("화물 종류 데이터가 비어있어 다양성 계산 불가")
        return
    long["bucket"] = long["kom"].map(_classify_kom_for_palette)
    pb = (long.groupby(["kode_pelabuhan", "bucket"])["ton"]
              .sum().reset_index())
    pivot = pb.pivot_table(index="kode_pelabuhan", columns="bucket",
                           values="ton", fill_value=0)
    if pivot.empty:
        st.info("다양성 계산할 데이터 없음")
        return

    totals = pivot.sum(axis=1)
    shares = pivot.div(totals.replace(0, pd.NA), axis=0).fillna(0)
    # Shannon entropy in nats; clip log of zero
    log_shares = shares.where(shares > 0).map(np.log).fillna(0)
    H = -(shares * log_shares).sum(axis=1)
    eff_n = np.exp(H)  # effective number of equally-weighted commodities

    div = pd.DataFrame({
        "kode_pelabuhan": shares.index,
        "총_톤": totals.values,
        "고유_화물수": (shares > 0).sum(axis=1).values,
        "Shannon_H": H.values.round(3),
        "유효_화물수": eff_n.values.round(2),
    })
    # Dominant bucket per port
    dom_bucket = shares.idxmax(axis=1)
    dom_share = shares.max(axis=1) * 100
    div["주력_화물"] = dom_bucket.values
    div["주력_점유율_%"] = dom_share.values.round(1)
    div["단일_화물_(>80%)"] = (dom_share >= 80.0).map(lambda b: "✓" if b else "")

    # Filter to ports with ≥ 30 calls so single-shipment ports don't pollute
    call_counts = df.groupby("kode_pelabuhan").size().rename("기항수")
    div = div.merge(call_counts.reset_index(), on="kode_pelabuhan", how="left")
    min_calls = st.slider(
        "최소 기항수 필터", 0, 200, 30, 5,
        help="단발성 양하 항구를 제외해 다양성 metric의 노이즈를 줄임",
        key="tk_div_minc",
    )
    sub = div[div["기항수"].fillna(0) >= min_calls].copy()

    if sub.empty:
        st.info("필터 조건에 맞는 항구가 없습니다")
        return

    # ---- KPI row ----
    n_ports = len(sub)
    n_single = int((sub["주력_점유율_%"] >= 80).sum())
    avg_eff = float(sub["유효_화물수"].mean())
    cols = st.columns(4)
    kpi(cols[0], "분석 항구", fmt.fmt_int(n_ports),
        help=f"기항 ≥ {min_calls}회 항구만 포함")
    kpi(cols[1], "단일 화물 항구", fmt.fmt_int(n_single),
        help="주력 화물 ≥ 80% 점유. 단일 commodity 의존도 ↑ → 가격 사이클 리스크")
    kpi(cols[2], "평균 유효 화물 수", f"{avg_eff:.2f}",
        help="exp(H). 1에 가까우면 단일 화물, 8 정도면 모든 카테고리 균등")
    kpi(cols[3], "최다 다양성", f"{sub['유효_화물수'].max():.2f}",
        help="exp(H) 최대값")

    # ---- top single-commodity ports ----
    cA, cB = st.columns(2)
    with cA:
        st.markdown("##### 🎯 단일 화물 항구 Top 15 (주력 점유율 ≥ 80%)")
        single = (sub[sub["주력_점유율_%"] >= 80]
                    .sort_values("총_톤", ascending=False).head(15))
        if single.empty:
            st.info("단일 화물 항구 없음")
        else:
            fig = px.bar(single.sort_values("총_톤"),
                         x="총_톤", y="kode_pelabuhan", orientation="h",
                         color="주력_화물", color_discrete_map=_KOM_BUCKET_PALETTE,
                         hover_data=["주력_점유율_%", "기항수", "유효_화물수"])
            fig.update_layout(height=460, margin=dict(t=10, b=10),
                              yaxis_title="", xaxis_title="총 톤")
            st.plotly_chart(fig, width="stretch")

    with cB:
        st.markdown("##### 🌐 다양화된 항구 Top 15 (유효 화물 수 ↑)")
        diverse = sub.sort_values("유효_화물수", ascending=False).head(15)
        if diverse.empty:
            st.info("다양화된 항구 없음")
        else:
            fig = px.bar(diverse.sort_values("유효_화물수"),
                         x="유효_화물수", y="kode_pelabuhan", orientation="h",
                         color="유효_화물수", color_continuous_scale=theme.SCALES["teal"],
                         hover_data=["주력_화물", "주력_점유율_%",
                                       "고유_화물수", "총_톤"])
            fig.update_layout(height=460, margin=dict(t=10, b=10),
                              yaxis_title="", xaxis_title="유효 화물 수 (exp H)",
                              coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")

    # ---- distribution histogram ----
    st.markdown("##### 다양성 분포 (분석 항구 전체)")
    fig = px.histogram(sub, x="유효_화물수", nbins=30,
                       color_discrete_sequence=["#0d9488"],
                       labels={"유효_화물수": "유효 화물 수 (exp H)",
                               "count": "항구 수"})
    fig.add_vline(x=2.0, line_dash="dash", line_color="#dc2626",
                  annotation_text="2 = 사실상 단일+보조",
                  annotation_position="top right")
    fig.update_layout(height=300, margin=dict(t=10, b=10), showlegend=False)
    st.plotly_chart(fig, width="stretch")

    show_cols = ["kode_pelabuhan", "기항수", "총_톤", "고유_화물수",
                 "유효_화물수", "Shannon_H", "주력_화물",
                 "주력_점유율_%", "단일_화물_(>80%)"]
    show_cols = [c for c in show_cols if c in sub.columns]
    st.dataframe(sub[show_cols].sort_values("총_톤", ascending=False),
                 width="stretch", hide_index=True)
    _csv_button(sub[show_cols], f"port_commodity_diversity_{snapshot}.csv",
                key="tk_dl_div")
    st.caption(
        "**Shannon H** (nats) = -Σ p × ln(p), p = 화물 카테고리 톤 점유율. "
        "**유효 화물 수** = exp(H) — 동일 가중 화물이 몇 개인지 직관적 해석. "
        "1 = 단일 화물 / 1.5–2.5 = 1개 주력 + 1–2 보조 / 3+ = 진정한 hub. "
        "단일 화물 항구는 commodity 가격 사이클에 취약, 다양화 항구는 안정성 ↑."
    )


# ------------- Tanker Operator / Owner view (iteration #4) -------------

# Indonesian company name prefixes — strip for cross-matching owner ↔ operator.
_COMPANY_PREFIXES = ("PT.", "PT", "P.T.", "P.T", "CV.", "CV", "PERSERO,",
                     "PERSERO", "(PERSERO)", "TBK.", "TBK")


def _norm_company(s: str | None) -> str | None:
    """Normalize Indonesian company name for cross-source matching."""
    if not isinstance(s, str):
        return None
    out = s.strip().upper()
    # Strip leading prefixes (run twice for "PT. (PERSERO)" style chains)
    for _ in range(3):
        for p in _COMPANY_PREFIXES:
            if out.startswith(p + " "):
                out = out[len(p) + 1:].strip()
                break
        else:
            break
    return out or None


def _tanker_operator_view():
    with st.spinner("탱커 운영사 데이터 불러오는 중…"):
        flows = _tanker_cargo_flows(snapshot)
        fleet = _tankers_full(snapshot)
    if flows.empty:
        st.info("이 스냅샷에는 운영사 데이터가 없습니다.")
        return

    flows = flows.assign(
        op_norm=flows["operator"].map(_norm_company),
        bton=pd.to_numeric(flows["bongkar_ton"], errors="coerce").fillna(0),
        mton=pd.to_numeric(flows["muat_ton"], errors="coerce").fillna(0),
    )
    flows["ton_total"] = flows["bton"] + flows["mton"]

    # Per-operator aggregation
    op = (flows.dropna(subset=["op_norm"])
                .groupby("op_norm")
                .agg(행수=("kapal", "size"),
                     고유_탱커=("kapal", "nunique"),
                     고유_항구=("kode_pelabuhan", "nunique"),
                     BONGKAR_톤=("bton", "sum"),
                     MUAT_톤=("mton", "sum"),
                     총_톤=("ton_total", "sum"))
                .reset_index())
    # Route diversity: unique (origin, destination) pairs per operator
    od = (flows.dropna(subset=["op_norm", "origin", "destination"])
                .groupby("op_norm")
                .apply(lambda d: d.drop_duplicates(["origin", "destination"]).shape[0],
                       include_groups=False)
                .rename("고유_항로")
                .reset_index())
    op = op.merge(od, on="op_norm", how="left")
    op["고유_항로"] = op["고유_항로"].fillna(0).astype(int)

    # Operator share of total tons
    grand_ton = float(op["총_톤"].sum())
    op["톤_점유율_%"] = (op["총_톤"] / grand_ton * 100).round(2) if grand_ton > 0 else 0
    op_sorted = op.sort_values("총_톤", ascending=False)

    # ---- KPI hero ----
    n_op = len(op_sorted)
    top_op = op_sorted.iloc[0] if not op_sorted.empty else None
    cr5_share = float(op_sorted.head(5)["톤_점유율_%"].sum())
    cr10_share = float(op_sorted.head(10)["톤_점유율_%"].sum())
    hhi_op = _hhi(op_sorted["톤_점유율_%"])

    cols = st.columns(5)
    kpi(cols[0], "고유 운영사", fmt.fmt_int(n_op),
        help="회사명 정규화(PT./CV. 등 접두 제거) 후 distinct 운영사 수")
    kpi(cols[1], "Top1 운영사",
        (top_op["op_norm"][:18] + "…") if top_op is not None and len(top_op["op_norm"]) > 18
        else (top_op["op_norm"] if top_op is not None else "-"),
        help="총 거래 톤 1위 운영사")
    kpi(cols[2], "Top1 톤 점유율",
        fmt.fmt_pct(top_op['톤_점유율_%']) if top_op is not None else "-",
        help="1위 운영사의 BONGKAR+MUAT 톤 점유율")
    kpi(cols[3], "Top5 / Top10",
        f"{fmt.fmt_pct(cr5_share)} / {fmt.fmt_pct(cr10_share)}",
        help="Top5/Top10 운영사 합산 점유율 (시장 집중도 직관적 척도)")
    band = ("낮음" if hhi_op < 1500 else "중간" if hhi_op < 2500 else "높음")
    kpi(cols[4], "HHI (톤 기준)",
        f"{hhi_op:,.0f} ({band})",
        help="Herfindahl-Hirschman Index. <1500 낮음 · 1500-2500 중간 · >2500 높음 (KPPU·DOJ 기준)")

    st.caption(
        "운영사 = LK3의 ('PERUSAHAAN', 'PERUSAHAAN') 필드 (실제 항해 운영자/대리점). "
        "선박 등기상 소유주(`nama_pemilik`)와 다를 수 있음 — 차터/풀 운영 구조 파악에 활용."
    )

    st.markdown("---")

    # ---- Top operators ----
    st.subheader("Top 운영사")
    metric_label = st.radio(
        "정렬 기준",
        ["총 톤", "행수", "고유 탱커 수", "고유 항로 수", "고유 항구 수"],
        horizontal=True, key="tk_op_metric",
    )
    metric_col = {
        "총 톤": "총_톤", "행수": "행수", "고유 탱커 수": "고유_탱커",
        "고유 항로 수": "고유_항로", "고유 항구 수": "고유_항구",
    }[metric_label]
    top_n = st.slider("Top N 운영사", 10, 50, 20, key="tk_op_topn")
    top = op_sorted.sort_values(metric_col, ascending=False).head(top_n)

    fig = px.bar(top.sort_values(metric_col),
                 x=metric_col, y="op_norm", orientation="h",
                 color="고유_탱커", color_continuous_scale=theme.SCALES["blue"],
                 hover_data=["행수", "고유_항구", "고유_항로",
                             "BONGKAR_톤", "MUAT_톤", "톤_점유율_%"])
    fig.update_layout(height=max(400, top_n * 22),
                      margin=dict(t=10, b=10),
                      yaxis_title="", xaxis_title=metric_label,
                      coloraxis=dict(colorbar=dict(title="탱커수")))
    st.plotly_chart(fig, width="stretch")

    show_cols = ["op_norm", "행수", "고유_탱커", "고유_항구", "고유_항로",
                 "BONGKAR_톤", "MUAT_톤", "총_톤", "톤_점유율_%"]
    st.dataframe(
        top[show_cols].rename(columns={"op_norm": "운영사"}).round(2),
        width="stretch", hide_index=True,
    )
    _csv_button(
        op_sorted[show_cols].rename(columns={"op_norm": "운영사"}).round(2),
        f"tanker_operators_{snapshot}.csv",
        label="📥 운영사 전체 CSV", key="tk_dl_op",
    )

    st.markdown("---")

    # ---- Operator efficiency: tons-per-call & avg dwell ----
    st.subheader("운영사 효율 (톤/회 · 평균 체류시간)")
    # Compute dwell per row (re-parse here; cheap enough)
    tiba = pd.to_datetime(flows["tiba_tanggal"],
                          format="%d-%m-%Y %H:%M:%S", errors="coerce")
    dep = pd.to_datetime(flows["berangkat_tanggal"],
                         format="%d-%m-%Y %H:%M:%S", errors="coerce")
    dwell = (dep - tiba).dt.total_seconds() / 3600.0
    dwell = dwell.where((dwell >= 0) & (dwell <= 720))
    eff = (flows.assign(dwell_h=dwell)
                .dropna(subset=["op_norm"])
                .groupby("op_norm")
                .agg(행수=("kapal", "size"),
                     ton_per_call=("ton_total", "mean"),
                     median_dwell_h=("dwell_h", "median"))
                .reset_index())
    eff = eff[eff["행수"] >= 50]  # filter low-activity operators
    eff = eff.merge(op_sorted[["op_norm", "총_톤", "고유_탱커"]], on="op_norm", how="left")
    eff = eff.sort_values("총_톤", ascending=False).head(50)
    if not eff.empty:
        fig = px.scatter(
            eff, x="median_dwell_h", y="ton_per_call", size="총_톤",
            hover_name="op_norm", color="고유_탱커",
            color_continuous_scale=theme.SCALES["teal"], size_max=50,
            labels={"median_dwell_h": "평균 체류시간 (h, 중앙값)",
                    "ton_per_call": "회당 평균 거래량 (톤)",
                    "고유_탱커": "운영 탱커 수"},
        )
        fig.update_layout(height=460, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "버블 크기 = 총 거래량. 좌상단(낮은 dwell + 높은 톤/회) = 효율적 대형 운영사. "
            "행수 ≥ 50 운영사만 표시 (단발 양하 왜곡 방지)."
        )

    st.markdown("---")

    # ---- Operator dominant commodity ----
    st.subheader("운영사별 주력 화물 (BONGKAR + MUAT 합산)")
    # For each operator, find their dominant komoditi bucket
    b = flows[["op_norm", "bongkar_kom", "bton"]].rename(
        columns={"bongkar_kom": "kom", "bton": "ton"})
    m = flows[["op_norm", "muat_kom", "mton"]].rename(
        columns={"muat_kom": "kom", "mton": "ton"})
    long = pd.concat([b, m], ignore_index=True).dropna(subset=["op_norm", "kom"])
    long["bucket"] = long["kom"].map(_classify_kom_for_palette)
    by_op_bucket = (long.groupby(["op_norm", "bucket"])["ton"].sum()
                        .reset_index())
    # Top operators by ton, then dominant bucket per operator
    top_ops = op_sorted.head(30)["op_norm"].tolist()
    sub_ob = by_op_bucket[by_op_bucket["op_norm"].isin(top_ops)].copy()
    if not sub_ob.empty:
        # operator-level total for normalization
        op_total = sub_ob.groupby("op_norm")["ton"].sum().rename("op_total")
        sub_ob = sub_ob.merge(op_total, on="op_norm")
        sub_ob["share"] = (sub_ob["ton"] / sub_ob["op_total"] * 100).round(1)
        # order operators by total tons (desc)
        order = (sub_ob.groupby("op_norm")["ton"].sum()
                       .sort_values(ascending=False).index.tolist())
        fig = px.bar(sub_ob, x="op_norm", y="share", color="bucket",
                     color_discrete_map=_KOM_BUCKET_PALETTE,
                     category_orders={"op_norm": order},
                     labels={"share": "화물 카테고리 점유율 (%)",
                             "op_norm": "운영사"})
        fig.update_layout(height=460, margin=dict(t=10, b=10),
                          xaxis_tickangle=-45, barmode="stack")
        st.plotly_chart(fig, width="stretch")
        st.caption("Top 30 운영사 각각의 BONGKAR+MUAT 톤 기준 카테고리 mix. "
                   "단일 카테고리 비중 ↑ = specialized 운영사.")

    # ---- Monthly operator HHI trend (iter #22) ----
    st.markdown("---")
    _monthly_operator_hhi_view(flows)

    st.markdown("---")

    # ---- Operator vs Owner cross-check ----
    st.subheader("운영사 ↔ 소유주 매칭")
    # Owner side from tankers_full
    if fleet.empty:
        st.info("선대 데이터 없음")
    else:
        own_df = (fleet.dropna(subset=["nama_pemilik"])
                       .assign(owner_norm=fleet["nama_pemilik"].map(_norm_company))
                       .groupby("owner_norm")
                       .agg(소유_척수=("vessel_key", "count"),
                            소유_GT=("gt", lambda s: pd.to_numeric(s, errors="coerce")
                                                       .fillna(0).sum()))
                       .reset_index()
                       .sort_values("소유_척수", ascending=False))

        merged = op_sorted.merge(
            own_df, left_on="op_norm", right_on="owner_norm", how="outer",
        ).fillna({"행수": 0, "고유_탱커": 0, "총_톤": 0,
                   "소유_척수": 0, "소유_GT": 0})
        merged["회사"] = merged["op_norm"].fillna(merged["owner_norm"])
        # Top by combined tonnage (cargo) + fleet GT (rough composite)
        merged["combo_score"] = merged["총_톤"] + merged["소유_GT"] * 100
        top_match = merged.sort_values("combo_score", ascending=False).head(25)

        st.dataframe(
            top_match[[
                "회사", "행수", "고유_탱커", "총_톤", "톤_점유율_%",
                "소유_척수", "소유_GT",
            ]].round(2),
            width="stretch", hide_index=True,
        )
        st.caption(
            "**행수/고유_탱커/총_톤** = LK3 운영사(PERUSAHAAN)로서의 활동. "
            "**소유_척수/소유_GT** = vessels_snapshot 등기상 소유주로서의 자산. "
            "두 칸 모두 큰 회사 = 자가 운영. 차이 큼 = 차터아웃/차터인 모델. "
            "0 / 큰 값 = LK3에는 운영자로 등장하지만 등기 선대는 없음 (대리점·차터)."
        )

    # ---- Operator drill-down (iteration #11) ----
    st.markdown("---")
    st.subheader("🔬 운영사 Drill-down")
    if op_sorted.empty:
        st.info("선택할 운영사 데이터가 없습니다.")
        return

    # Default to top operator by ton
    op_choices = op_sorted["op_norm"].tolist()
    sel_idx = 0
    sel_op = st.selectbox(
        "운영사 선택", op_choices, index=sel_idx,
        help="LK3 PERUSAHAAN 정규화된 이름. 가나다순이 아닌 톤 점유율 순으로 정렬",
        key="tk_op_drill",
    )
    _operator_drilldown(flows, fleet, sel_op)

    # ---- Korean exposure (iter #19) ----
    st.markdown("---")
    _korean_exposure_view()

    # ---- IDX-listed cross-ref (iter #21) ----
    st.markdown("---")
    _idx_listed_view()


def _idx_listed_view() -> None:
    """💼 IDX-listed shipping issuer cross-reference + Tbk-suffix surface.

    Two complementary panels:
    1. Curated YAML cross-ref — known IDX shipping issuers + their fleet
    2. All Tbk-suffix owners — broader publicly-listed indicator
    """
    st.subheader("💼 IDX 상장 운용사 매칭")

    cur = _idx_listed_match(snapshot)
    tbk = _tbk_owners(snapshot)

    if cur.empty and tbk.empty:
        st.info("IDX 상장 매칭 또는 Tbk 접미사 owner를 찾을 수 없습니다.")
        return

    # ---- Panel 1: Curated YAML cross-ref ----
    if not cur.empty:
        st.markdown("##### 📊 curated 매칭 (data/companies_financials.yml 기반)")
        cur = cur.assign(
            gt_num=pd.to_numeric(cur["gt"], errors="coerce").fillna(0))
        agg = (cur.groupby(["ticker", "issuer_name", "sector_focus"])
                  .agg(매칭_척수=("vessel_key", "count"),
                       총_GT=("gt_num", "sum"),
                       평균_GT=("gt_num", "mean"))
                  .reset_index().sort_values("총_GT", ascending=False))
        cols = st.columns(4)
        kpi(cols[0], "매칭 issuer", fmt.fmt_int(len(agg)),
            help="curated YAML의 IDX 상장사 중 fleet에서 매칭된 회사")
        kpi(cols[1], "매칭 탱커", fmt.fmt_int(len(cur)))
        kpi(cols[2], "매칭 GT 총합", fmt.fmt_gt(float(cur["gt_num"].sum())))
        # Top issuer (by GT)
        top = agg.iloc[0] if not agg.empty else None
        kpi(cols[3], "Top issuer",
            f"{top['ticker']} ({fmt.fmt_int(top['매칭_척수'])}척)" if top is not None else "-")
        theme.dataframe(agg.round(0))

        # Per-ticker drill-down expander
        for tk in agg["ticker"].tolist():
            sub = cur[cur["ticker"] == tk].copy()
            with st.expander(
                f"🔍 {tk} ({sub['issuer_name'].iloc[0]}) — "
                f"{len(sub)}척 / {fmt.fmt_gt(float(sub['gt_num'].sum()))}"
            ):
                cols_show = ["nama_kapal", "tanker_subclass", "bendera",
                             "nama_pemilik", "gt", "loa", "tahun", "imo"]
                cols_show = [c for c in cols_show if c in sub.columns]
                st.dataframe(sub[cols_show].sort_values("gt", ascending=False),
                             width="stretch", hide_index=True)
                if not agg.empty:
                    sf = agg.loc[agg["ticker"] == tk, "sector_focus"].iloc[0]
                    st.caption(f"YAML sector_focus: {sf}")
    else:
        st.info("Curated 매칭 결과 없음 (YAML 키워드 보강 필요)")

    # ---- Panel 2: Tbk-suffix owners (broader surface) ----
    st.markdown("##### 🏛️ Tbk 접미사 owner (모든 IDX 상장 후보)")
    if tbk.empty:
        st.info("Tbk 접미사 owner 없음")
        return
    tbk = tbk.assign(
        gt_num=pd.to_numeric(tbk["gt"], errors="coerce").fillna(0))
    tbk_agg = (tbk.groupby("nama_pemilik")
                  .agg(척수=("vessel_key", "count"),
                       총_GT=("gt_num", "sum"))
                  .reset_index().sort_values("총_GT", ascending=False))
    cols = st.columns(3)
    kpi(cols[0], "Tbk 회사 수", fmt.fmt_int(len(tbk_agg)))
    kpi(cols[1], "Tbk 보유 탱커", fmt.fmt_int(len(tbk)))
    kpi(cols[2], "Tbk 보유 GT", fmt.fmt_gt(float(tbk["gt_num"].sum())))
    theme.dataframe(tbk_agg)

    cols_show = ["nama_kapal", "tanker_subclass", "nama_pemilik",
                 "bendera", "gt", "tahun", "imo"]
    cols_show = [c for c in cols_show if c in tbk.columns]
    st.dataframe(tbk[cols_show].sort_values("gt", ascending=False),
                 width="stretch", hide_index=True)
    _csv_button(tbk[cols_show], f"tbk_listed_owners_{snapshot}.csv",
                key="tk_dl_tbk")
    st.caption(
        "**Tbk** = Indonesian 'Terbuka' = publicly-listed (IDX). "
        "Curated 매칭에 누락된 issuer라도 여기에 노출됨 — "
        "직접 KSE/IDX 종목 매수로 인도네시아 탱커 사업 익스포저 가능."
    )


def _korean_exposure_view() -> None:
    """🇰🇷 Korean-affiliated tanker surface — flag, owner, vessel name signals."""
    st.subheader("🇰🇷 한국계 노출 탱커")
    kr = _korean_tankers(snapshot)
    if kr.empty:
        st.info("이 스냅샷에는 한국계 신호가 식별된 탱커가 없습니다.")
        return

    n = len(kr)
    n_flag = int((kr["kr_signal"] == "Korean Flag").sum())
    n_owner = int((kr["kr_signal"] == "Korean Owner").sum())
    n_name = int((kr["kr_signal"] == "Korean Name").sum())
    sum_gt = float(pd.to_numeric(kr["gt"], errors="coerce").fillna(0).sum())

    cols = st.columns(5)
    kpi(cols[0], "한국계 탱커", fmt.fmt_int(n),
        help="bendera (Korea South) / 소유주명 (KORINDO·HYUNDAI 등) / 선박명 어느 하나라도 매치")
    kpi(cols[1], "Korean Flag", fmt.fmt_int(n_flag),
        help="bendera = 'Korea South'")
    kpi(cols[2], "Korean Owner", fmt.fmt_int(n_owner),
        help="nama_pemilik에 KORINDO/KOREA/HYUNDAI 등 키워드")
    kpi(cols[3], "Korean Name", fmt.fmt_int(n_name),
        help="nama_kapal에 BUSAN/SEOUL 등 한국 도시명")
    kpi(cols[4], "총 GT", fmt.fmt_gt(sum_gt))

    st.caption(
        "한국 투자 법인이 직접 관계할 수 있는 탱커 후보. **Korean Flag**가 가장 "
        "강한 신호 (한국 등록선이 인도네시아 운항 중) — Charter-out / 매수 후보. "
        "**Korean Owner** 중 KORINDO는 한국-인도네시아 JV — 직접 협업 가능. "
        "**Korean Name**은 약신호 (단순 도시명 차용)."
    )

    # ---- subclass distribution
    if "tanker_subclass" in kr.columns:
        sub_counts = kr["tanker_subclass"].value_counts().reset_index()
        sub_counts.columns = ["subclass", "n"]
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("##### Subclass mix")
            fig = px.pie(sub_counts, names="subclass", values="n",
                         color="subclass", color_discrete_map=_TANKER_PALETTE,
                         hole=0.5)
            fig.update_traces(textinfo="percent+label")
            fig.update_layout(height=300, margin=dict(t=10, b=10),
                              legend=dict(font=dict(size=10)))
            st.plotly_chart(fig, width="stretch")
        with c2:
            st.markdown("##### 신호 카테고리")
            sig_counts = kr["kr_signal"].value_counts().reset_index()
            sig_counts.columns = ["signal", "n"]
            fig = px.bar(sig_counts, x="signal", y="n",
                         color="signal",
                         color_discrete_map={
                             "Korean Flag": "#dc2626",
                             "Korean Owner": "#0d9488",
                             "Korean Name": "#9ca3af",
                         })
            fig.update_layout(height=300, margin=dict(t=10, b=10),
                              showlegend=False)
            st.plotly_chart(fig, width="stretch")

    # ---- Top owners among Korean-affiliated
    own = (kr.dropna(subset=["nama_pemilik"])
              .groupby("nama_pemilik")
              .agg(척수=("vessel_key", "count"),
                   GT=("gt", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()))
              .reset_index().sort_values("척수", ascending=False))
    if not own.empty:
        st.markdown("##### Top 한국계 탱커 보유 회사")
        theme.dataframe(own.head(15))

    # ---- full list
    st.markdown("##### 한국계 탱커 전체 목록")
    cur_yr = int(snapshot[:4])
    show = kr.assign(age=cur_yr - pd.to_numeric(kr["tahun"], errors="coerce"))
    cols_show = ["nama_kapal", "kr_signal", "kr_reason", "tanker_subclass",
                 "bendera", "nama_pemilik", "gt", "loa", "tahun", "age",
                 "imo"]
    cols_show = [c for c in cols_show if c in show.columns]
    show = show[cols_show].sort_values("gt", ascending=False, na_position="last")
    theme.dataframe(show)
    _csv_button(show, f"korean_tankers_{snapshot}.csv",
                key="tk_dl_kr")


def _monthly_operator_hhi_view(flows: pd.DataFrame) -> None:
    """Operator HHI computed per (data_year, data_month) period.

    Surfaces whether tanker operator concentration is rising or falling over
    the 24-month LK3 window. Uses ton-share basis (percent shares 0-100 →
    HHI in [0, 10000], KPPU/DOJ-standard scale).
    """
    st.subheader("운영사 집중도 추이 (월별 HHI)")

    if flows.empty or "op_norm" not in flows.columns:
        st.info("월별 HHI 계산용 데이터 부족")
        return

    # Group by period × operator
    g = (flows.dropna(subset=["op_norm", "period"])
              .groupby(["period", "op_norm"])["ton_total"].sum()
              .reset_index())
    if g.empty:
        st.info("월별 데이터 없음")
        return

    rows = []
    for period, sub in g.groupby("period"):
        total = float(sub["ton_total"].sum())
        if total <= 0:
            continue
        shares_pct = sub["ton_total"] / total * 100
        hhi = float((shares_pct ** 2).sum())
        n_op = len(sub)
        top1 = float(shares_pct.max())
        # Effective number of operators = 10000 / HHI (Hannah-Kay equivalent)
        eff_n = 10000.0 / hhi if hhi > 0 else None
        rows.append({
            "period": period, "HHI": round(hhi, 0),
            "Top1_share_%": round(top1, 2),
            "n_operators": int(n_op),
            "effective_n": round(eff_n, 2) if eff_n else None,
            "total_ton": total,
        })
    if not rows:
        st.info("HHI 계산 가능한 기간 없음")
        return

    hdf = pd.DataFrame(rows).sort_values("period")

    # ---- KPI: latest vs earliest ----
    latest, earliest = hdf.iloc[-1], hdf.iloc[0]
    delta_hhi = latest["HHI"] - earliest["HHI"]
    band = ("낮음" if latest["HHI"] < 1500
            else "중간" if latest["HHI"] < 2500 else "높음")

    cols = st.columns(4)
    kpi(cols[0], f"최근 ({latest['period']}) HHI",
        f"{int(latest['HHI']):,} ({band})",
        help="ton-share 기반. 1500 미만 낮음 / 1500-2500 중간 / 2500+ 높음")
    kpi(cols[1], f"24mo Δ HHI",
        f"{int(delta_hhi):+,}",
        help=f"latest({latest['period']}) - earliest({earliest['period']})")
    kpi(cols[2], "Top1 점유율 (%)",
        fmt.fmt_pct(latest["Top1_share_%"]),
        help="최근 월의 1위 운영사 점유율")
    kpi(cols[3], "유효 운영사 수",
        f"{latest['effective_n']:.2f}" if latest["effective_n"] else "-",
        help="Hannah-Kay = 10000 / HHI. 1에 가까우면 사실상 단일 운영사")

    # ---- Trend chart ----
    fig = px.line(hdf, x="period", y="HHI", markers=True,
                  labels={"period": "기간", "HHI": "HHI (0-10000)"})
    # KPPU bands
    fig.add_hrect(y0=0, y1=1500, fillcolor="#16a34a", opacity=0.08,
                  line_width=0, annotation_text="낮음 < 1500",
                  annotation_position="top left", annotation_font_size=10)
    fig.add_hrect(y0=1500, y1=2500, fillcolor="#f59e0b", opacity=0.08,
                  line_width=0, annotation_text="중간 1500-2500",
                  annotation_position="top left", annotation_font_size=10)
    fig.add_hrect(y0=2500, y1=10000, fillcolor="#dc2626", opacity=0.08,
                  line_width=0, annotation_text="높음 ≥ 2500",
                  annotation_position="top left", annotation_font_size=10)
    fig.update_traces(line_color="#1e40af", line_width=3)
    fig.update_layout(height=360, margin=dict(t=20, b=10),
                      yaxis=dict(range=[0, max(10000, hdf["HHI"].max() * 1.1)]))
    st.plotly_chart(fig, width="stretch")

    # ---- Top1 share + effective_n side by side ----
    cA, cB = st.columns(2)
    with cA:
        fig2 = px.bar(hdf, x="period", y="Top1_share_%",
                      color="Top1_share_%", color_continuous_scale=theme.SCALES["red"],
                      labels={"period": "기간", "Top1_share_%": "Top1 점유율 (%)"})
        fig2.update_layout(height=300, margin=dict(t=20, b=10),
                           coloraxis_showscale=False)
        st.plotly_chart(fig2, width="stretch")
    with cB:
        fig3 = px.line(hdf, x="period", y="effective_n", markers=True,
                       labels={"period": "기간",
                               "effective_n": "유효 운영사 수 (10000/HHI)"})
        fig3.update_traces(line_color="#16a34a", line_width=3)
        fig3.update_layout(height=300, margin=dict(t=20, b=10))
        st.plotly_chart(fig3, width="stretch")

    theme.dataframe(hdf)
    _csv_button(hdf, f"operator_hhi_monthly_{snapshot}.csv",
                key="tk_dl_hhi")
    st.caption(
        "월별 ton-share HHI. 추세선이 우상향 = 시장 집중도↑ (Pertamina 강화 / "
        "신규 진입자 감소). 우하향 = 시장 분산↑ (경쟁 활발). "
        "Indonesian 탱커 시장은 구조적 highly-concentrated이라 "
        "변동폭은 보통 작지만 directional hint."
    )


def _operator_drilldown(flows: pd.DataFrame, fleet: pd.DataFrame,
                          op_name: str) -> None:
    """Per-operator deep dive — 5 panels on a single operator selection."""
    sub = flows[flows["op_norm"] == op_name].copy()
    if sub.empty:
        st.warning(f"'{op_name}' 운영사 활동 행 없음")
        return

    # ---- header KPIs ----
    n_rows = len(sub)
    n_kapal = sub["kapal"].nunique()
    n_ports = sub["kode_pelabuhan"].nunique()
    n_routes = (sub.dropna(subset=["origin", "destination"])
                   .drop_duplicates(["origin", "destination"]).shape[0])
    total_ton = float(sub["ton_total"].sum())

    # Match fleet by normalized owner name
    owner_match = fleet[
        fleet["nama_pemilik"].fillna("").map(_norm_company) == op_name
    ].copy()
    own_count = len(owner_match)
    own_gt = float(pd.to_numeric(owner_match["gt"], errors="coerce")
                                  .fillna(0).sum()) if own_count else 0.0

    cols = st.columns(6)
    kpi(cols[0], "행수", fmt.fmt_int(n_rows))
    kpi(cols[1], "운영 탱커 수", fmt.fmt_int(n_kapal),
        help="이 운영사의 LK3 KAPAL 필드 distinct count")
    kpi(cols[2], "기항 항구", fmt.fmt_int(n_ports))
    kpi(cols[3], "고유 항로", fmt.fmt_int(n_routes))
    kpi(cols[4], "총 운송 톤", fmt.fmt_ton(total_ton))
    kpi(cols[5], "보유 등기 선대",
        f"{own_count}척 / {fmt.fmt_gt(own_gt)}",
        help="vessels_snapshot에 같은 회사명으로 등기된 탱커 수")

    # ---- Their fleet (matched on normalized owner name) ----
    if own_count > 0:
        with st.expander(f"🚢 등기 선대 {own_count}척", expanded=False):
            cur_yr = int(snapshot[:4])
            owner_match["age"] = cur_yr - pd.to_numeric(
                owner_match["tahun"], errors="coerce")
            cols_show = ["nama_kapal", "tanker_subclass", "bendera",
                         "gt", "loa", "tahun", "age", "imo"]
            cols_show = [c for c in cols_show if c in owner_match.columns]
            st.dataframe(
                owner_match[cols_show].sort_values("gt", ascending=False),
                width="stretch", hide_index=True,
            )

    # ---- Top routes ----
    st.markdown("##### Top 항로 (Origin → Destination)")
    routes = (sub[(sub["origin"] != sub["destination"])
                    & sub["origin"].notna() & sub["destination"].notna()]
                .groupby(["origin", "destination"])
                .agg(톤=("ton_total", "sum"), 행수=("ton_total", "count"))
                .reset_index().sort_values("톤", ascending=False))
    if routes.empty:
        st.info("항로 데이터 없음")
    else:
        top_n = min(15, len(routes))
        rt = routes.head(top_n).copy()
        rt["pair"] = rt["origin"].astype(str) + " → " + rt["destination"].astype(str)
        rt = rt.sort_values("톤")
        fig = px.bar(rt, x="톤", y="pair", orientation="h",
                     color="톤", color_continuous_scale=theme.SCALES["blue"],
                     hover_data=["행수"])
        fig.update_layout(height=max(280, top_n * 24),
                          margin=dict(t=10, b=10),
                          yaxis_title="", coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")

    # ---- Two-column: dwell histogram + commodity mix ----
    cA, cB = st.columns(2)
    with cA:
        st.markdown("##### Dwell time 분포")
        tiba = pd.to_datetime(sub["tiba_tanggal"],
                              format="%d-%m-%Y %H:%M:%S", errors="coerce")
        dep = pd.to_datetime(sub["berangkat_tanggal"],
                             format="%d-%m-%Y %H:%M:%S", errors="coerce")
        dwell = (dep - tiba).dt.total_seconds() / 3600.0
        dwell = dwell.where((dwell >= 0) & (dwell <= 240))
        if dwell.notna().any():
            fig = px.histogram(
                dwell.dropna(), nbins=40,
                labels={"value": "체류 시간 (h)"},
                color_discrete_sequence=["#0d9488"],
            )
            med = float(dwell.median())
            fig.add_vline(x=med, line_dash="dash", line_color="#dc2626",
                          annotation_text=f"중앙값 {fmt.fmt_dwell(med)}",
                          annotation_position="top right")
            fig.update_layout(height=320, margin=dict(t=10, b=10),
                              showlegend=False, yaxis_title="행수")
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Dwell 시간 파싱 가능한 행 없음")

    with cB:
        st.markdown("##### 화물 카테고리 mix")
        b = sub[["bongkar_kom", "bton"]].rename(
            columns={"bongkar_kom": "kom", "bton": "ton"})
        m = sub[["muat_kom", "mton"]].rename(
            columns={"muat_kom": "kom", "mton": "ton"})
        long = pd.concat([b, m], ignore_index=True).dropna(subset=["kom"])
        long["bucket"] = long["kom"].map(_classify_kom_for_palette)
        bm = long.groupby("bucket")["ton"].sum().reset_index().sort_values(
            "ton", ascending=False)
        bm = bm[bm["ton"] > 0]
        if bm.empty:
            st.info("화물 카테고리 데이터 없음")
        else:
            fig = px.pie(bm, names="bucket", values="ton",
                         color="bucket", color_discrete_map=_KOM_BUCKET_PALETTE,
                         hole=0.5)
            fig.update_layout(height=320, margin=dict(t=10, b=10),
                              legend=dict(font=dict(size=10)))
            fig.update_traces(textinfo="percent+label")
            st.plotly_chart(fig, width="stretch")

    # ---- 24-month tonnage trend ----
    st.markdown("##### 24개월 운송 톤 트렌드")
    trend = (sub.groupby("period")
                .agg(BONGKAR=("bton", "sum"), MUAT=("mton", "sum"),
                     행수=("ton_total", "size"))
                .reset_index().sort_values("period"))
    if trend.empty:
        st.info("기간 데이터 없음")
    else:
        long_t = trend.melt(id_vars=["period"],
                             value_vars=["BONGKAR", "MUAT"],
                             var_name="방향", value_name="톤")
        fig = px.bar(long_t, x="period", y="톤", color="방향",
                     barmode="group",
                     color_discrete_map={"BONGKAR": "#1e40af", "MUAT": "#16a34a"})
        fig.update_layout(height=300, margin=dict(t=10, b=10),
                          xaxis_title="기간", yaxis_title="톤",
                          xaxis_tickangle=-30)
        st.plotly_chart(fig, width="stretch")
        theme.dataframe(trend)


# ------------- Tanker Investment Signals view (iteration #5) -------------

# Estimated DWT/GT ratios per tanker subclass — empirical medians from the
# LK3 dataset, used to project fleet GT into capacity (DWT) when DWT is
# missing. LNG/LPG ratios are notably <1 (low cargo density).
_DWT_GT_RATIO = {
    "Crude Oil":            1.6,
    "Product":              1.7,
    "Chemical":             1.55,
    "LPG":                  1.0,
    "LNG":                  0.8,
    "FAME / Vegetable Oil": 1.7,
    "Water":                1.5,
    "UNKNOWN":              1.5,
}

# Industry assumption: annual round trips per tanker (Indonesian inter-island
# average — varies hugely by class). 10 = conservative for VLCC/Suezmax,
# 18 = typical Product/MR. Use 12 as middle-ground default.
_ANNUAL_ROUND_TRIPS_DEFAULT = 12.0


def _kom_to_subclass(label: str | None) -> str:
    """Map a freeform LK3 komoditi text to a tanker subclass bucket."""
    if not isinstance(label, str):
        return "Product"
    s = label.upper()
    if "CRUDE" in s or "MENTAH" in s:                       return "Crude Oil"
    if "LNG" in s or "NATURAL GAS" in s or "GAS ALAM" in s: return "LNG"
    if any(k in s for k in ("LPG", "ELPIJI", "PROPANE", "BUTANE")): return "LPG"
    if any(k in s for k in ("CPO", "PALM OIL", "MINYAK SAWIT", "OLEIN",
                             "STEARIN", "PKO", "CPKO", "PALM KERNEL",
                             "FAME", "BIODIESEL", "VEGETABLE OIL",
                             "MINYAK NABATI")): return "FAME / Vegetable Oil"
    if "CHEMICAL" in s or "KIMIA" in s or "ACID" in s or "ASAM" in s: return "Chemical"
    if "AIR " in s or "WATER " in s:                       return "Water"
    return "Product"


def _tanker_investment_view():
    with st.spinner("투자 시그널 계산 중…"):
        flows = _tanker_cargo_flows(snapshot)
        fleet = _tankers_full(snapshot)
    if flows.empty or fleet.empty:
        st.info("이 스냅샷에는 분석에 충분한 데이터가 없습니다.")
        return

    flows = flows.assign(
        bton=pd.to_numeric(flows["bongkar_ton"], errors="coerce").fillna(0),
        mton=pd.to_numeric(flows["muat_ton"], errors="coerce").fillna(0),
    )
    flows["ton_total"] = flows["bton"] + flows["mton"]
    # Subclass per ROW: pick the side that has tons (BONGKAR if present, else MUAT).
    primary_kom = flows["bongkar_kom"].where(
        flows["bton"] > 0, flows["muat_kom"])
    flows["c_sub"] = primary_kom.map(_kom_to_subclass)

    periods = sorted(flows["period"].dropna().unique())
    if len(periods) < 4:
        st.warning(f"기간 데이터가 부족합니다 (n={len(periods)})")
        return
    half = min(12, len(periods) // 2)
    latest = set(periods[-half:])
    prior = set(periods[-2 * half:-half])
    months_span = half  # used to annualize

    st.caption(
        f"분석 윈도우: latest {half}개월 ({periods[-half]} ~ {periods[-1]}) "
        f"vs prior {half}개월 ({periods[-2*half]} ~ {periods[-half-1]}). "
        "톤은 BONGKAR + MUAT 합산. 자체 캡처 데이터로 산정한 _시그널_ — "
        "실제 투자 결정은 추가 due-diligence 필수."
    )

    # ---------- Section 1: Capacity utilization by subclass ----------
    st.subheader("1. Subclass 별 수급 압력")
    annual_rt = st.slider(
        "연간 round-trip 수 (가정)",
        min_value=6, max_value=20, value=int(_ANNUAL_ROUND_TRIPS_DEFAULT),
        help="인도네시아 inter-island 탱커 평균. VLCC ~10, Product/MR ~16-20",
        key="tk_inv_rt",
    )

    # Cargo throughput per subclass — annualized using span
    sub_cargo = (flows[flows["period"].isin(latest)]
                   .groupby("c_sub")["ton_total"].sum().rename("latest_ton"))
    sub_cargo_prior = (flows[flows["period"].isin(prior)]
                         .groupby("c_sub")["ton_total"].sum().rename("prior_ton"))
    cap = pd.concat([sub_cargo, sub_cargo_prior], axis=1).fillna(0)
    cap["annual_ton"] = cap["latest_ton"] * (12.0 / months_span)
    cap["yoy_pct"] = ((cap["latest_ton"] /
                       cap["prior_ton"].replace(0, pd.NA)) - 1) * 100

    # Fleet capacity per subclass: GT × DWT/GT ratio
    fleet = fleet.assign(
        gt_num=pd.to_numeric(fleet["gt"], errors="coerce").fillna(0))
    fl = (fleet.groupby("tanker_subclass")
                .agg(척수=("vessel_key", "count"),
                     sum_gt=("gt_num", "sum"))
                .reset_index()
                .rename(columns={"tanker_subclass": "c_sub"}))
    fl["est_DWT"] = fl.apply(
        lambda r: r["sum_gt"] * _DWT_GT_RATIO.get(r["c_sub"], 1.5), axis=1)
    fl["annual_capacity"] = fl["est_DWT"] * annual_rt * 0.85  # 85% load factor

    cap_view = cap.merge(fl, left_index=True, right_on="c_sub", how="outer").fillna(0)
    cap_view["util_pct"] = (cap_view["annual_ton"] /
                            cap_view["annual_capacity"].replace(0, pd.NA)) * 100
    cap_view["ton_per_vessel_yr"] = (cap_view["annual_ton"] /
                                      cap_view["척수"].replace(0, pd.NA))
    cap_view = cap_view.sort_values("annual_ton", ascending=False)
    cap_view = cap_view[cap_view["c_sub"].astype(bool)]  # drop empty bucket

    show_cols = ["c_sub", "척수", "sum_gt", "est_DWT", "annual_capacity",
                 "annual_ton", "util_pct", "ton_per_vessel_yr",
                 "prior_ton", "latest_ton", "yoy_pct"]
    show_cols = [c for c in show_cols if c in cap_view.columns]
    rename = {
        "c_sub": "Subclass", "sum_gt": "Fleet GT",
        "est_DWT": "Est. DWT", "annual_capacity": "연간 capacity (톤)",
        "annual_ton": "연간 cargo (톤)", "util_pct": "이용률 %",
        "ton_per_vessel_yr": "톤/선/년",
        "prior_ton": "prior 12mo (톤)", "latest_ton": "latest 12mo (톤)",
        "yoy_pct": "YoY %",
    }
    st.dataframe(cap_view[show_cols].rename(columns=rename).round(1),
                 width="stretch", hide_index=True)
    _csv_button(cap_view[show_cols].rename(columns=rename).round(1),
                f"tanker_capacity_utilization_{snapshot}.csv",
                label="📥 수급 압력 CSV", key="tk_dl_cap")

    # Visualize utilization
    cap_plot = cap_view[cap_view["util_pct"].notna() & (cap_view["util_pct"] > 0)].copy()
    if not cap_plot.empty:
        fig = px.bar(cap_plot.sort_values("util_pct"),
                     x="util_pct", y="c_sub", orientation="h",
                     color="util_pct", color_continuous_scale=theme.SCALES["diverging_r"],
                     labels={"util_pct": "이용률 (%)", "c_sub": "Subclass"},
                     hover_data=["척수", "annual_capacity", "annual_ton"])
        fig.add_vline(x=100, line_dash="dash", line_color="#dc2626",
                      annotation_text="이론 만재 100%",
                      annotation_position="top right")
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "이용률 > 100% = 현 fleet 이론 capacity로는 화물 처리 불가능 → "
            "공급 부족(=신규 진입/투자 기회), 또는 외국 fleet 의존. "
            "이용률 < 50% = 공급 과잉(=과당경쟁/마진 압박)."
        )

    st.markdown("---")

    # ---------- Section 2: Trade-lane YoY growth ----------
    st.subheader("2. 트레이드 레인 YoY 변화 (Top growers · decliners)")
    od = (flows[(flows["origin"] != flows["destination"])
                  & flows["origin"].notna() & flows["destination"].notna()]
            .copy())
    od["side"] = od["period"].map(
        lambda p: "latest" if p in latest else ("prior" if p in prior else None))
    od_agg = (od.dropna(subset=["side"])
                .groupby(["origin", "destination", "side"])["ton_total"].sum()
                .unstack(fill_value=0).reset_index())
    if "latest" not in od_agg.columns: od_agg["latest"] = 0
    if "prior" not in od_agg.columns: od_agg["prior"] = 0
    od_agg["delta"] = od_agg["latest"] - od_agg["prior"]
    od_agg["yoy_pct"] = ((od_agg["latest"] /
                          od_agg["prior"].replace(0, pd.NA)) - 1) * 100

    min_prior = st.slider(
        "유효성 필터: prior 윈도우 최소 톤", 0, 50000, 5000, 1000,
        help="단발성 양하 노이즈를 걸러내기 위한 임계치", key="tk_inv_minprior",
    )
    od_clean = od_agg[od_agg["prior"] >= min_prior].copy()

    cN = st.columns(2)
    with cN[0]:
        st.markdown("##### 🔼 Top 15 성장 항로")
        growers = od_clean.sort_values("delta", ascending=False).head(15).copy()
        growers["pair"] = growers["origin"] + " → " + growers["destination"]
        if not growers.empty:
            fig = px.bar(growers.sort_values("delta"),
                         x="delta", y="pair", orientation="h",
                         color="yoy_pct", color_continuous_scale=theme.SCALES["green"],
                         hover_data=["prior", "latest", "yoy_pct"])
            fig.update_layout(height=520, margin=dict(t=10, b=10),
                              yaxis_title="", xaxis_title="ΔTON (latest - prior)",
                              coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")
    with cN[1]:
        st.markdown("##### 🔽 Top 15 감소 항로")
        decliners = od_clean.sort_values("delta").head(15).copy()
        decliners["pair"] = decliners["origin"] + " → " + decliners["destination"]
        if not decliners.empty:
            fig = px.bar(decliners.sort_values("delta", ascending=False),
                         x="delta", y="pair", orientation="h",
                         color="yoy_pct", color_continuous_scale=theme.SCALES["diverging"],
                         hover_data=["prior", "latest", "yoy_pct"])
            fig.update_layout(height=520, margin=dict(t=10, b=10),
                              yaxis_title="", xaxis_title="ΔTON",
                              coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")

    with st.expander("전체 YoY 항로 표 (필터 적용)"):
        st.dataframe(
            od_clean.sort_values("delta", ascending=False)
                    .rename(columns={"prior": "prior 12mo", "latest": "latest 12mo",
                                     "delta": "ΔTON", "yoy_pct": "YoY %"}).round(1),
            width="stretch", hide_index=True,
        )

    st.markdown("---")

    # ---------- Section 3: Supply-demand by tanker class (LOA bucket) ----------
    st.subheader("3. 클래스별 공급-수요 압력")
    # Cargo: classify each row's class via observed LOA
    flows["loa_num"] = pd.to_numeric(flows["loa"], errors="coerce")
    flows["class_capacity"] = flows["loa_num"].map(_classify_loa_bucket)
    cargo_class = (flows[flows["period"].isin(latest)]
                     .groupby("class_capacity")
                     .agg(연간_cargo_톤=("ton_total", "sum"),
                          기항=("kapal", "size"),
                          고유_탱커_관측=("kapal", "nunique"))
                     .reset_index())
    cargo_class["연간_cargo_톤"] *= (12.0 / months_span)

    # Fleet: classify by panjang/loa
    fleet["loa_for_class"] = pd.to_numeric(fleet["loa"], errors="coerce")
    fleet["class_capacity"] = fleet["loa_for_class"].map(_classify_loa_bucket)
    fleet_class = (fleet.groupby("class_capacity")
                          .agg(fleet_척수=("vessel_key", "count"),
                               fleet_GT=("gt_num", "sum"))
                          .reset_index())

    cls_view = cargo_class.merge(fleet_class, on="class_capacity", how="outer").fillna(0)
    cls_view["TON_per_fleet_vessel"] = (
        cls_view["연간_cargo_톤"] / cls_view["fleet_척수"].replace(0, pd.NA)
    )
    # Order by class size (large → small) for readability
    order = [lbl for _, lbl in _TANKER_LOA_CLASS] + ["Unknown"]
    cls_view["__order"] = cls_view["class_capacity"].map(
        {lbl: i for i, lbl in enumerate(order)})
    cls_view = cls_view.sort_values("__order").drop(columns="__order")

    theme.dataframe(cls_view.round(1))

    plot_df = cls_view[cls_view["fleet_척수"] > 0].copy()
    if not plot_df.empty:
        fig = px.bar(plot_df, x="class_capacity", y="TON_per_fleet_vessel",
                     color="TON_per_fleet_vessel",
                     color_continuous_scale=theme.SCALES["red"],
                     labels={"TON_per_fleet_vessel": "연간 톤 / 선",
                             "class_capacity": "클래스"},
                     hover_data=["fleet_척수", "fleet_GT", "연간_cargo_톤"])
        fig.update_layout(height=380, margin=dict(t=10, b=10),
                          coloraxis_showscale=False, xaxis_tickangle=-30)
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "**연간 톤 / 선** = (해당 LOA 클래스의 12개월 cargo) / (인도네시아 등기 fleet 척수). "
            "수치가 클수록 fleet이 _상대적으로_ 적은 클래스 — 외국선 의존 또는 신규 투자 여지. "
            "단, 클래스 미상(LOA 결측)은 해석 주의."
        )


# ------------- Tanker snapshot-to-snapshot trend (iteration #12) -------------

def _tanker_trend_view():
    with st.spinner("스냅샷 트렌드 집계 중…"):
        df = _tanker_snapshot_trend()
    if df.empty:
        st.info("스냅샷 데이터가 없습니다.")
        return

    n_snap = len(df)
    if n_snap < 2:
        st.info(
            f"📌 트렌드 차트는 최소 2개 스냅샷이 있을 때 활성화됩니다. "
            f"현재 보유 스냅샷: **{n_snap}개** ({df['snapshot'].iloc[0]}). "
            f"매월 1일 스크레이프가 누적되면 자동으로 그려집니다."
        )
        # Still show the single snapshot's KPI snapshot as a one-row table
        st.markdown("##### 현재 스냅샷 KPI (단일)")
        st.dataframe(df.T.rename(columns={0: "value"}),
                     width="stretch")
        _csv_button(df, f"tanker_trend_{df['snapshot'].iloc[0]}.csv",
                    label="📥 트렌드 KPI CSV", key="tk_trend_dl")
        return

    # ---- KPI delta header (latest vs previous) ----
    latest, prev = df.iloc[-1], df.iloc[-2]
    cols = st.columns(5)

    def _delta(curr, prior, fmt_fn):
        if prior is None or pd.isna(prior) or prior == 0:
            return None
        d = curr - prior
        sign = "+" if d > 0 else ""
        return f"{sign}{fmt_fn(d)} ({(d/prior*100):+.1f}%)"

    kpi(cols[0], "Fleet 척수", fmt.fmt_int(latest["fleet_count"]),
        delta=_delta(latest["fleet_count"], prev["fleet_count"], fmt.fmt_int))
    kpi(cols[1], "Fleet GT 합", fmt.fmt_gt(latest["fleet_gt_sum"]),
        delta=_delta(latest["fleet_gt_sum"], prev["fleet_gt_sum"], fmt.fmt_gt))
    kpi(cols[2], "평균 선령",
        f"{latest['fleet_avg_age']:.1f}년"
        if pd.notna(latest['fleet_avg_age']) else "-")
    kpi(cols[3], "Top 운영사 점유율",
        fmt.fmt_pct(latest.get("top_op_share_pct", 0)),
        delta=_delta(latest.get("top_op_share_pct", 0),
                     prev.get("top_op_share_pct", 0),
                     lambda v: f"{v:+.1f}%p"))
    kpi(cols[4], "총 cargo 톤",
        fmt.fmt_ton(latest.get("cargo_total_ton", 0)),
        delta=_delta(latest.get("cargo_total_ton", 0),
                     prev.get("cargo_total_ton", 0), fmt.fmt_ton))

    st.markdown("---")

    # ---- Fleet trend ----
    st.subheader("Fleet 추이")
    fleet_long = df.melt(
        id_vars=["snapshot"],
        value_vars=["fleet_count", "fleet_gt_sum", "aged_25_count"],
        var_name="metric", value_name="value",
    )
    label_map = {
        "fleet_count": "탱커 척수",
        "fleet_gt_sum": "총 GT",
        "aged_25_count": "25년+ 척수",
    }
    fleet_long["metric"] = fleet_long["metric"].map(label_map)
    fig = px.line(fleet_long, x="snapshot", y="value", color="metric",
                  markers=True,
                  labels={"snapshot": "스냅샷", "value": "값"})
    fig.update_layout(height=320, margin=dict(t=10, b=10),
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")

    # ---- Subclass mix trend ----
    sub_cols = [c for c in df.columns if c.startswith("fleet_")
                and c not in ("fleet_count", "fleet_gt_sum", "fleet_avg_age")]
    if sub_cols:
        st.subheader("Subclass 척수 추이")
        sub_long = df.melt(id_vars=["snapshot"], value_vars=sub_cols,
                           var_name="subclass", value_name="count")
        sub_long["subclass"] = sub_long["subclass"].str.replace(
            "fleet_", "", regex=False).str.replace("_", " ", regex=False)
        fig = px.line(sub_long, x="snapshot", y="count", color="subclass",
                      markers=True)
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch")

    # ---- Cargo (commodity bucket) trend ----
    cargo_buckets = [c for c in df.columns if c.startswith("ton_")]
    if cargo_buckets:
        st.subheader("화물 카테고리 톤 추이 (BONGKAR + MUAT)")
        cargo_long = df.melt(id_vars=["snapshot"], value_vars=cargo_buckets,
                             var_name="bucket", value_name="ton")
        cargo_long["bucket"] = cargo_long["bucket"].str.replace(
            "ton_", "", regex=False)
        fig = px.line(cargo_long, x="snapshot", y="ton", color="bucket",
                      markers=True,
                      labels={"snapshot": "스냅샷", "ton": "톤"})
        fig.update_layout(height=380, margin=dict(t=10, b=10),
                          legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch")

    # ---- Top operator share trend ----
    if "top_op_share_pct" in df.columns:
        st.subheader("Top 운영사 점유율 추이")
        op_disp = df[["snapshot", "top_op_name", "top_op_share_pct"]].copy()
        fig = px.bar(op_disp, x="snapshot", y="top_op_share_pct",
                     color="top_op_name",
                     hover_data=["top_op_name"],
                     labels={"snapshot": "스냅샷",
                             "top_op_share_pct": "Top1 점유율 (%)"})
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          legend=dict(orientation="h", y=-0.3,
                                      font=dict(size=10)))
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")
    st.subheader("전체 스냅샷 KPI 표")
    theme.dataframe(df)
    _csv_button(df, "tanker_snapshot_trend.csv",
                label="📥 트렌드 KPI CSV", key="tk_trend_dl_full")
    st.caption(
        "각 스냅샷은 그 시점의 fleet 등기 + 24개월 LK3 스냅샷을 의미. "
        "월 1회 자동 누적되며, 월별 변화는 최근 vs 이전 스냅샷의 KPI delta로 확인."
    )


# ------------- Tanker vessel lookup (iteration #16) -------------

def _tanker_search_view():
    st.markdown(
        "**선박명** 또는 **IMO 번호**를 입력해 등기 선대 + LK3 활동 이력을 조회합니다. "
        "부분 일치, 대소문자 무시. 모든 스냅샷에서 검색합니다."
    )
    cA, cB = st.columns([3, 1])
    name_q = cA.text_input("선박명 (부분 일치)", value="",
                            placeholder="예: PERTAMINA, TANTO, JAYA, BUNGA",
                            key="tk_search_name")
    imo_q = cB.text_input("IMO", value="", placeholder="9123456",
                           key="tk_search_imo")

    if not name_q.strip() and not imo_q.strip():
        st.info(
            "검색어 입력 대기 중. **운영자 관점 활용**: "
            "예) 'TANTO' → Tanto Intim Line 운영 선대 / "
            "'PERTAMINA' → 등기 fleet → 활동 history 비교 / "
            "'9' (IMO 첫 자리) → IMO 등록 탱커 일괄 조회."
        )
        return

    # ---- Fleet matches (across all snapshots) ----
    with st.spinner("등기 선대 검색 중…"):
        fleet_hits = _vessel_lookup(name_q, imo_q, limit=100)

    if fleet_hits.empty:
        st.warning(
            "등기 선대(`vessels_snapshot`)에서 일치하는 선박이 없습니다. "
            "철자 / 약자(call sign) / IMO 정확도 확인."
        )
    else:
        # Collapse identical (vessel_key) across snapshots → 1 row + first/last seen
        agg = (fleet_hits.groupby("vessel_key")
                          .agg(snapshots=("snapshot_month",
                                          lambda s: ", ".join(sorted(set(s)))),
                               nama_kapal=("nama_kapal", "first"),
                               eks_nama_kapal=("eks_nama_kapal", "first"),
                               call_sign=("call_sign", "first"),
                               jenis_kapal=("jenis_kapal", "first"),
                               nama_pemilik=("nama_pemilik", "first"),
                               gt=("gt", "first"),
                               panjang=("panjang", "first"),
                               lebar=("lebar", "first"),
                               dalam=("dalam", "first"),
                               imo=("imo", "first"),
                               tahun=("tahun", "first"))
                          .reset_index())
        st.subheader(f"🚢 등기 선대 매치 ({len(agg)}건)")
        cols = st.columns(3)
        kpi(cols[0], "고유 선박", fmt.fmt_int(len(agg)),
            help="vessel_key 기준 distinct")
        kpi(cols[1], "총 매치 행", fmt.fmt_int(len(fleet_hits)),
            help="(vessel_key, snapshot_month) 단위 row 수")
        kpi(cols[2], "스냅샷 범위",
            f"{fleet_hits['snapshot_month'].min()} ~ {fleet_hits['snapshot_month'].max()}")
        theme.dataframe(agg)
        _csv_button(agg, f"vessel_lookup_fleet_{name_q[:12] or imo_q[:8]}.csv",
                    key="tk_search_dl_fleet")

    # ---- Cargo activity (only if we have a name to match against KAPAL) ----
    if name_q.strip():
        st.markdown("---")
        st.subheader("🌊 LK3 활동 이력")
        scope = st.radio(
            "범위", ["선택 스냅샷", "현재 스냅샷"], horizontal=True,
            help="선택 스냅샷 = 사이드바의 Snapshot",
            key="tk_search_scope",
        )
        with st.spinner("LK3 활동 조회 중 (단일 SQL pass)…"):
            act = _vessel_cargo_activity(
                name_q,
                snapshot if scope == "선택 스냅샷" else None,
                limit=1000,
            )
        if act.empty:
            st.info("일치하는 LK3 활동 행 없음")
        else:
            n_rows = len(act)
            n_kapal = act["kapal"].nunique()
            n_op = act["operator"].nunique()
            n_ports = act["kode_pelabuhan"].nunique()
            total_ton = float(act["bongkar_ton"].fillna(0).sum()
                              + act["muat_ton"].fillna(0).sum())
            cols = st.columns(5)
            kpi(cols[0], "활동 행", fmt.fmt_int(n_rows))
            kpi(cols[1], "고유 KAPAL", fmt.fmt_int(n_kapal),
                help="이름 부분일치 → 동명/유사 선박 다수 매치 가능")
            kpi(cols[2], "운영사", fmt.fmt_int(n_op))
            kpi(cols[3], "기항 항구", fmt.fmt_int(n_ports))
            kpi(cols[4], "총 톤", fmt.fmt_ton(total_ton))

            # Top operators that operated this vessel
            act["ton_total"] = (act["bongkar_ton"].fillna(0)
                                 + act["muat_ton"].fillna(0))
            op_summary = (act.dropna(subset=["operator"])
                              .groupby("operator")
                              .agg(행수=("operator", "size"),
                                   톤=("ton_total", "sum"))
                              .reset_index().sort_values("톤", ascending=False))
            if not op_summary.empty:
                st.markdown("##### 운영사 분포 (이 검색어의 KAPAL을 누가 운항?)")
                st.dataframe(op_summary.head(15), width="stretch",
                             hide_index=True)

            # Top ports
            port_summary = (act.groupby("kode_pelabuhan")
                                .agg(행수=("kode_pelabuhan", "size"),
                                     톤=("ton_total", "sum"))
                                .reset_index().sort_values("톤", ascending=False))
            if not port_summary.empty:
                st.markdown("##### 기항 항구 분포")
                st.dataframe(port_summary.head(15), width="stretch",
                             hide_index=True)

            # Activity timeline
            st.markdown("##### 활동 row 목록 (최대 1,000행)")
            show_cols = ["snapshot_month", "data_year", "data_month",
                         "kode_pelabuhan", "kapal", "operator", "jenis_kapal",
                         "origin", "destination", "tiba_tanggal",
                         "berangkat_tanggal", "bongkar_kom", "bongkar_ton",
                         "muat_kom", "muat_ton", "gt", "dwt"]
            show_cols = [c for c in show_cols if c in act.columns]
            theme.dataframe(act[show_cols])
            _csv_button(act,
                        f"vessel_lookup_activity_{name_q[:12]}.csv",
                        key="tk_search_dl_act")
            st.caption(
                "⚠️ 부분일치(LIKE) 결과 — 'JAYA' 같이 흔한 토큰은 동명선 다수 포함될 수 있음. "
                "정밀 매칭은 IMO + 정확한 KAPAL 명 사용 권장."
            )


# ------------- Pertamina ecosystem page (iter #25) -------------

def page_pertamina():
    st.title("🇮🇩 Pertamina Ecosystem")
    st.caption(
        f"Snapshot: **{snapshot}** · "
        "인도네시아 탱커 시장의 ~55% 톤 점유 — Trans Kontinental + Patra Niaga + "
        "International Shipping(PIS) + 9개 subsidiary 통합 분석"
    )

    fleet = _pertamina_fleet(snapshot)
    flows = _pertamina_op(snapshot)

    if fleet.empty and flows.empty:
        st.info("Pertamina 데이터가 없습니다.")
        return

    fleet = fleet.assign(
        gt_num=pd.to_numeric(fleet["gt"], errors="coerce").fillna(0))
    if not flows.empty:
        flows = flows.assign(
            ton=pd.to_numeric(flows["bongkar_ton"], errors="coerce").fillna(0)
                + pd.to_numeric(flows["muat_ton"], errors="coerce").fillna(0))

    # ---- KPI hero ----
    n_fleet = len(fleet)
    fleet_gt = float(fleet["gt_num"].sum())
    cur_yr = int(snapshot[:4])
    yrs = pd.to_numeric(fleet["tahun"], errors="coerce")
    avg_age = float((cur_yr - yrs).where(cur_yr - yrs >= 0).mean()) \
        if yrs.notna().any() else None
    n_op_rows = len(flows)
    total_ton = float(flows["ton"].sum()) if not flows.empty else 0
    n_ports = flows["kode_pelabuhan"].nunique() if not flows.empty else 0

    cols = st.columns(6)
    kpi(cols[0], "보유 탱커", fmt.fmt_int(n_fleet),
        help="9개 Pertamina subsidiary 합산 owned tanker 수")
    kpi(cols[1], "보유 GT", fmt.fmt_gt(fleet_gt))
    kpi(cols[2], "평균 선령",
        f"{avg_age:.1f} 년" if avg_age is not None else "-")
    kpi(cols[3], "운영 행수", fmt.fmt_int(n_op_rows),
        help="LK3 PERUSAHAAN에 PERTAMINA 포함 (사실상 Trans Kontinental 단일)")
    kpi(cols[4], "운송 톤", fmt.fmt_ton(total_ton))
    kpi(cols[5], "기항 항구", fmt.fmt_int(n_ports))

    st.caption(
        "**시장 구조 핵심**: Pertamina는 자체 fleet (Patra Niaga·PIS 등) + "
        "외부 차터 (Trans Kontinental이 charter operator) 분리 모델. "
        "tanker 시장 진입자는 Pertamina와의 charter agreement이 사실상 필수."
    )

    st.markdown("---")

    # ---- Per-entity breakdown ----
    st.subheader("🏛️ Pertamina 엔티티별 역할")
    own_groups = (fleet.groupby("nama_pemilik")
                       .agg(척수=("vessel_key", "count"),
                            총_GT=("gt_num", "sum"),
                            평균_GT=("gt_num", "mean"),
                            avg_age=("tahun", lambda s:
                                       (cur_yr - pd.to_numeric(s, errors="coerce"))
                                       .where((cur_yr - pd.to_numeric(s, errors="coerce")) >= 0)
                                       .mean()))
                       .reset_index().sort_values("척수", ascending=False))
    own_groups["역할"] = own_groups.apply(
        lambda r: ("자산 보유 (charter-out)" if r["척수"] >= 30
                   else "직영 운영 (charter operator)" if "TRANS KONTINENTAL" in r["nama_pemilik"].upper()
                   else "국제 charter (PIS)" if "INTERNATIONAL SHIPPING" in r["nama_pemilik"].upper()
                   else "기타 / 모회사"), axis=1)
    own_groups["avg_age"] = own_groups["avg_age"].round(1)
    own_groups["평균_GT"] = own_groups["평균_GT"].round(0)
    theme.dataframe(own_groups)
    _csv_button(own_groups, f"pertamina_entities_{snapshot}.csv",
                key="pert_dl_entities")

    st.markdown("---")

    # ---- Pertamina fleet by subclass ----
    cA, cB = st.columns(2)
    with cA:
        st.markdown("##### Pertamina 보유 fleet — subclass mix")
        sub_mix = (fleet.groupby("tanker_subclass")
                          .agg(n=("vessel_key", "count"),
                               sum_gt=("gt_num", "sum"))
                          .reset_index().sort_values("n", ascending=False))
        if not sub_mix.empty:
            fig = px.pie(sub_mix, names="tanker_subclass", values="n",
                         color="tanker_subclass",
                         color_discrete_map=_TANKER_PALETTE, hole=0.5)
            fig.update_traces(textinfo="percent+label", textposition="outside")
            fig.update_layout(height=320, margin=dict(t=10, b=10),
                              legend=dict(font=dict(size=10)))
            theme.donut_center(fig, fmt.fmt_int(int(sub_mix["n"].sum())),
                               "보유 척수")
            st.plotly_chart(fig, width="stretch")
    with cB:
        st.markdown("##### Pertamina 운송 화물 카테고리 mix (24mo)")
        if not flows.empty:
            bk = flows[["bongkar_kom", "bongkar_ton"]].rename(
                columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
            mk = flows[["muat_kom", "muat_ton"]].rename(
                columns={"muat_kom": "kom", "muat_ton": "ton"})
            long = pd.concat([bk, mk], ignore_index=True).dropna(subset=["kom"])
            long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
            long["bucket"] = long["kom"].map(_classify_kom_for_palette)
            mix = (long.groupby("bucket")["ton"].sum()
                       .reset_index().sort_values("ton", ascending=False))
            mix = mix[mix["ton"] > 0]
            if not mix.empty:
                fig = px.pie(mix, names="bucket", values="ton",
                             color="bucket",
                             color_discrete_map=_KOM_BUCKET_PALETTE, hole=0.5)
                fig.update_traces(textinfo="percent+label", textposition="outside")
                fig.update_layout(height=320, margin=dict(t=10, b=10),
                                  legend=dict(font=dict(size=10)))
                theme.donut_center(fig, fmt.fmt_ton(float(mix["ton"].sum())),
                                   "총 운송")
                st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # ---- Pertamina top ports ----
    st.subheader("⚓ Pertamina 주요 기항 항구 (Top 20)")
    if flows.empty:
        st.info("Pertamina 운영 LK3 데이터 없음")
    else:
        ports_meta = _ports()
        top_p = (flows.groupby("kode_pelabuhan")
                       .agg(기항=("kapal", "size"),
                            톤=("ton", "sum"),
                            고유_탱커=("kapal", "nunique"))
                       .reset_index()
                       .sort_values("톤", ascending=False).head(20))
        top_p = top_p.merge(ports_meta, on="kode_pelabuhan", how="left")
        cols_show = ["kode_pelabuhan", "nama_pelabuhan", "기항", "고유_탱커", "톤"]
        cols_show = [c for c in cols_show if c in top_p.columns]
        top_disp = top_p[cols_show].copy()
        top_disp["톤"] = top_disp["톤"].round(0)
        theme.dataframe(top_disp)
        # bar chart
        fig = px.bar(top_p.head(15).sort_values("톤"),
                     x="톤", y="kode_pelabuhan", orientation="h",
                     color="톤", color_continuous_scale=theme.SCALES["blue"],
                     hover_data=["nama_pelabuhan", "기항", "고유_탱커"])
        fig.update_layout(height=420, margin=dict(t=10, b=10),
                          coloraxis_showscale=False, yaxis_title="")
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # ---- Monthly Pertamina activity trend ----
    st.subheader("📈 Pertamina 운송 24mo 추이")
    if flows.empty:
        st.info("월별 추이 데이터 없음")
    else:
        m = (flows.groupby("period")
                  .agg(BONGKAR=("bongkar_ton",
                                 lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
                       MUAT=("muat_ton",
                              lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
                       행수=("kapal", "size"))
                  .reset_index().sort_values("period"))
        long_t = m.melt(id_vars=["period"], value_vars=["BONGKAR", "MUAT"],
                          var_name="방향", value_name="톤")
        fig = px.bar(long_t, x="period", y="톤", color="방향",
                     barmode="group",
                     color_discrete_map={"BONGKAR": "#1e40af", "MUAT": "#16a34a"})
        fig.update_layout(height=320, margin=dict(t=10, b=10),
                          xaxis_title="기간", xaxis_tickangle=-30)
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # ---- Aged Pertamina fleet (replacement candidates) ----
    st.subheader("🛠️ Pertamina 노후 fleet (대체 후보)")
    age_series = cur_yr - yrs
    aged25 = fleet[age_series >= 25].copy()
    aged25["age"] = (cur_yr - pd.to_numeric(aged25["tahun"], errors="coerce")).astype("Int64")
    if aged25.empty:
        st.info("25년+ Pertamina 탱커 없음")
    else:
        cols_show = ["nama_kapal", "tanker_subclass", "nama_pemilik",
                     "bendera", "gt", "tahun", "age", "imo"]
        cols_show = [c for c in cols_show if c in aged25.columns]
        st.dataframe(aged25[cols_show].sort_values("gt", ascending=False),
                     width="stretch", hide_index=True)
        st.caption(
            f"Pertamina ecosystem 내 25년+ 노후 탱커 **{len(aged25)}**척. "
            "대체 발주 후보 — 한국 조선소 / 탱커 매수 협상 시 우선 검토군."
        )
        _csv_button(aged25[cols_show], f"pertamina_aged_{snapshot}.csv",
                    key="pert_dl_aged")


@st.cache_data(ttl=3600)
def _classify_jk_to_vessel_class(jk_unique: tuple[str, ...]) -> dict[str, str]:
    """Vectorized backend.taxonomy classification for unique LK3 JENIS KAPAL
    labels. Caches the lookup across reruns — labels are stable strings,
    typically ~80 distinct values across all of LK3.
    """
    from backend.taxonomy import classify_vessel_type
    return {jk: classify_vessel_type(jk)[1] for jk in jk_unique}


def _cargo_long_form(flows: pd.DataFrame) -> pd.DataFrame:
    """Reshape `cargo_flows()` rows into a long-form (one row per ton movement)
    DataFrame with kapal/operator/origin/destination/kom/ton/direction/bucket
    and a derived `vessel_class` from the LK3 ``jenis_kapal`` label.
    """
    if flows.empty:
        return flows
    b = flows[["period", "kapal", "operator", "jenis_kapal",
                "origin", "destination",
                "bongkar_kom", "bongkar_ton", "gt", "dwt"]].rename(
        columns={"bongkar_kom": "kom", "bongkar_ton": "ton"})
    b["direction"] = "BONGKAR"
    m = flows[["period", "kapal", "operator", "jenis_kapal",
                "origin", "destination",
                "muat_kom", "muat_ton", "gt", "dwt"]].rename(
        columns={"muat_kom": "kom", "muat_ton": "ton"})
    m["direction"] = "MUAT"
    long = pd.concat([b, m], ignore_index=True)
    long["ton"] = pd.to_numeric(long["ton"], errors="coerce").fillna(0)
    long = long[long["ton"] > 0].copy()
    long["bucket"] = long["kom"].map(_classify_kom_for_palette)

    jk_unique = tuple(sorted(long["jenis_kapal"].dropna().unique().tolist()))
    jk_map = _classify_jk_to_vessel_class(jk_unique)
    long["vessel_class"] = long["jenis_kapal"].map(jk_map).fillna("UNMAPPED")
    return long


def _cargo_od_map(long: pd.DataFrame, top_n: int = 60,
                   key_prefix: str = "cg") -> None:
    """🗺️ Indonesia OD map for the (filtered) generic cargo flow set.

    Mirrors the tanker map's design (great-circle lines colored by commodity
    bucket, port bubbles sized by total ton) but uses the broader cargo
    palette from `_KOM_BUCKET_PALETTE` and the global port-coord lookup.
    """
    if long.empty:
        st.info("표시할 화물 흐름이 없습니다.")
        return

    coord_map, foreign_set = _port_name_to_coords()
    f = long.copy()
    f["o_norm"] = f["origin"].map(_normalize_port_name)
    f["d_norm"] = f["destination"].map(_normalize_port_name)
    f["o_coord"] = f["o_norm"].map(lambda k: coord_map.get(k))
    f["d_coord"] = f["d_norm"].map(lambda k: coord_map.get(k))
    f["o_foreign"] = f["o_norm"].isin(foreign_set)
    f["d_foreign"] = f["d_norm"].isin(foreign_set)

    total_ton = float(f["ton"].sum())
    intl_ton = float(f.loc[f["o_foreign"] | f["d_foreign"], "ton"].sum())
    plottable = f.dropna(subset=["o_coord", "d_coord"]).copy()
    plottable = plottable[~(plottable["o_foreign"] | plottable["d_foreign"])]
    plot_ton = float(plottable["ton"].sum())
    unknown_ton = total_ton - intl_ton - plot_ton

    cN = st.columns(4)
    kpi(cN[0], "필터 톤 합", fmt.fmt_ton(total_ton))
    kpi(cN[1], "지도 표시 톤", fmt.fmt_ton(plot_ton),
        help="origin/destination 양쪽 좌표 매핑된 항로의 톤 합")
    kpi(cN[2], "국제 항해 톤", fmt.fmt_ton(intl_ton),
        help="외국 항구 — 지도 밖")
    kpi(cN[3], "미매핑 톤", fmt.fmt_ton(unknown_ton),
        help="origin/destination 텍스트가 좌표 사전에 없음")

    if plottable.empty:
        st.info("좌표 매핑 가능한 항로가 없습니다.")
        return

    plottable["lat_o"] = plottable["o_coord"].map(lambda c: c[0])
    plottable["lon_o"] = plottable["o_coord"].map(lambda c: c[1])
    plottable["lat_d"] = plottable["d_coord"].map(lambda c: c[0])
    plottable["lon_d"] = plottable["d_coord"].map(lambda c: c[1])

    od_bucket = (plottable.groupby(
                    ["o_norm", "d_norm", "lat_o", "lon_o", "lat_d", "lon_d",
                     "bucket"])
                          .agg(ton=("ton", "sum"), n_calls=("ton", "size"),
                                n_vessels=("kapal", "nunique"))
                          .reset_index())
    od_bucket = od_bucket[od_bucket["o_norm"] != od_bucket["d_norm"]]
    if od_bucket.empty:
        st.info("Origin ≠ Destination 항로가 없습니다 (모두 self-loop).")
        return
    od_bucket = od_bucket.sort_values("ton", ascending=False).head(top_n)

    port_ton = pd.concat([
        plottable[["o_norm", "lat_o", "lon_o", "ton"]].rename(
            columns={"o_norm": "port", "lat_o": "lat", "lon_o": "lon"}),
        plottable[["d_norm", "lat_d", "lon_d", "ton"]].rename(
            columns={"d_norm": "port", "lat_d": "lat", "lon_d": "lon"}),
    ], ignore_index=True)
    port_agg = (port_ton.groupby(["port", "lat", "lon"])["ton"].sum()
                          .reset_index().sort_values("ton", ascending=False))

    max_ton = float(od_bucket["ton"].max())
    fig = go.Figure()
    for bucket, sub in od_bucket.groupby("bucket"):
        color = _KOM_BUCKET_PALETTE.get(bucket, "#64748b")
        first = True
        for r in sub.itertuples(index=False):
            width = 1.0 + 8.0 * (r.ton / max_ton) ** 0.5
            fig.add_trace(go.Scattergeo(
                lon=[r.lon_o, r.lon_d], lat=[r.lat_o, r.lat_d],
                mode="lines",
                line=dict(width=width, color=color),
                opacity=0.75,
                hoverinfo="text",
                text=(f"<b>{bucket}</b><br>{r.o_norm} → {r.d_norm}<br>"
                      f"{fmt.fmt_compact(r.ton, 1)}t · {r.n_vessels}척 · "
                      f"{int(r.n_calls)}회"),
                name=bucket, legendgroup=bucket, showlegend=first,
            ))
            first = False

    fig.add_trace(go.Scattergeo(
        lon=port_agg["lon"], lat=port_agg["lat"], mode="markers",
        marker=dict(
            size=(port_agg["ton"] / port_agg["ton"].max() * 26 + 4),
            color="#0f172a", opacity=0.85,
            line=dict(width=0.5, color="#ffffff"),
        ),
        text=port_agg.apply(
            lambda r: f"<b>{r['port']}</b><br>{fmt.fmt_compact(r['ton'], 1)}t",
            axis=1),
        hoverinfo="text", name="항구 (총 톤)", showlegend=True,
    ))

    fig.update_layout(
        height=620, margin=dict(t=10, b=10, l=10, r=10),
        legend=dict(orientation="h", y=-0.05, x=0,
                    bgcolor="rgba(255,255,255,0.85)",
                    bordercolor="#e2e8f0", borderwidth=1,
                    font=dict(size=11)),
        geo=dict(
            scope="asia", projection_type="natural earth",
            showcountries=True, showcoastlines=True, showland=True,
            showocean=True, oceancolor="#f1f5f9",
            landcolor="#fefefe", countrycolor="#cbd5e1",
            coastlinecolor="#94a3b8",
            lataxis=dict(range=[-12, 8]),
            lonaxis=dict(range=[94, 142]),
        ),
    )
    st.plotly_chart(fig, width="stretch")

    with st.expander(f"📋 항로 테이블 — Top {len(od_bucket)}"):
        lane_show = (od_bucket[["o_norm", "d_norm", "bucket",
                                 "ton", "n_calls", "n_vessels"]]
                        .rename(columns={"o_norm": "출발", "d_norm": "도착",
                                          "bucket": "카테고리", "ton": "총_톤",
                                          "n_calls": "항해수",
                                          "n_vessels": "선박수"}))
        theme.dataframe(lane_show)
        _csv_button(lane_show,
                     f"cargo_flow_map_lanes_{snapshot}.csv",
                     label="📥 항로 CSV", key=f"{key_prefix}_lanes_dl")


def page_cargo():
    st.title("📦 Cargo (LK3) — 화물 분석")
    st.caption(
        f"Snapshot: **{snapshot}** · "
        "어선·여객선·예인선 등 비-화물 행 제외 (탱커·일반화물·벌크·컨테이너·바지 중심)"
    )

    flows = _cargo_flows(snapshot)
    if flows.empty:
        st.info("LK3 화물 데이터가 없습니다.")
        return

    # Build long-form (per direction/ton) view used by all sub-tabs
    long_all = _cargo_long_form(flows)

    # ---------------- Top filters (shared across sub-tabs) ----------------
    with st.expander("🔍 필터", expanded=True):
        all_buckets = (long_all.groupby("bucket")["ton"].sum()
                                  .sort_values(ascending=False).index.tolist())
        all_periods = sorted(long_all["period"].dropna().unique().tolist())
        period_default = (all_periods[-12:] if len(all_periods) > 12
                           else all_periods)
        all_classes = (long_all.groupby("vessel_class")["ton"].sum()
                                   .sort_values(ascending=False).index.tolist())
        # Pre-compute top operators (ton) so the operator multiselect ranks them
        op_ton_lookup = (long_all.dropna(subset=["operator"])
                                    .groupby("operator")["ton"].sum()
                                    .sort_values(ascending=False))
        top_operators = op_ton_lookup.head(50).index.tolist()

        c1, c2 = st.columns([2, 3])
        with c1:
            sel_buckets = st.multiselect(
                "화물 카테고리 (비어두면 전체)",
                all_buckets, default=[], key="cg_buckets",
                help="복수 선택 가능. 비어두면 전체 카테고리.",
            )
        with c2:
            sel_periods = st.multiselect(
                "기간 (YYYY-MM)", all_periods, default=period_default,
                key="cg_periods",
                help=f"전체 {len(all_periods)}개월 · 기본값 = 최근 12개월",
            )

        c3, c4, c5 = st.columns([2, 2, 1])
        with c3:
            dir_pick = st.radio(
                "방향", ["전체", "BONGKAR (양하)", "MUAT (적재)"],
                horizontal=True, key="cg_dir",
            )
        with c4:
            port_q = st.text_input(
                "항구명 포함 (origin 또는 destination)", key="cg_port",
                help="대소문자 무시 substring 매칭",
            )
        with c5:
            top_n_lanes = st.slider("Top N 항로", 10, 200, 60, 10,
                                      key="cg_topn")

        c6, c7 = st.columns([2, 3])
        with c6:
            sel_classes = st.multiselect(
                "선종 (Vessel Class)", all_classes, default=[],
                key="cg_class",
                help="LK3 JENIS KAPAL → 분류. 비어두면 전체 선종. "
                      "Tanker, General Cargo, Container, Bulk Carrier, Other Cargo.",
            )
        with c7:
            sel_operators = st.multiselect(
                f"운영사 (PERUSAHAAN) — 상위 {len(top_operators)}개 미리보기",
                top_operators, default=[], key="cg_operator",
                help="비어두면 전체 운영사. 텍스트 검색은 항목명 일부 입력 가능.",
            )

    # ---------------- Apply filters ----------------
    f = long_all
    if sel_buckets:
        f = f[f["bucket"].isin(sel_buckets)]
    if sel_periods:
        f = f[f["period"].isin(sel_periods)]
    if sel_classes:
        f = f[f["vessel_class"].isin(sel_classes)]
    if sel_operators:
        f = f[f["operator"].isin(sel_operators)]
    if dir_pick.startswith("BONGKAR"):
        f = f[f["direction"] == "BONGKAR"]
    elif dir_pick.startswith("MUAT"):
        f = f[f["direction"] == "MUAT"]
    if port_q:
        pq = port_q.upper()
        mask = (f["origin"].fillna("").str.upper().str.contains(pq)
                | f["destination"].fillna("").str.upper().str.contains(pq))
        f = f[mask]

    n_flows = len(f)
    n_kapal = int(f["kapal"].dropna().nunique())
    n_op = int(f["operator"].dropna().nunique())
    total_ton = float(f["ton"].sum())
    n_buckets = int(f["bucket"].nunique())
    n_classes = int(f["vessel_class"].nunique())

    cols = st.columns(6)
    kpi(cols[0], "행 수", fmt.fmt_int(n_flows))
    kpi(cols[1], "총 톤", fmt.fmt_ton(total_ton))
    kpi(cols[2], "고유 선박", fmt.fmt_int(n_kapal))
    kpi(cols[3], "운영사", fmt.fmt_int(n_op))
    kpi(cols[4], "화물 카테고리", fmt.fmt_int(n_buckets))
    kpi(cols[5], "선종", fmt.fmt_int(n_classes))

    if f.empty:
        st.info("필터 조건에 해당하는 데이터가 없습니다.")
        return

    st.markdown("---")

    tab_sum, tab_map, tab_port, tab_intl, tab_sts, tab_list = st.tabs(
        ["📊 화물 요약", "🗺️ OD 지도", "🏗️ 항구별",
         "🌐 국제 무역", "🔄 STS / 자체 환적", "📋 상세 리스트"]
    )

    # ============ 1) Summary ============
    with tab_sum:
        cA, cB = st.columns(2)
        with cA:
            st.markdown("**화물 카테고리별 총 톤**")
            ag = (f.groupby("bucket")["ton"].sum()
                       .sort_values(ascending=True).reset_index())
            fig = px.bar(ag, x="ton", y="bucket", orientation="h",
                          color="bucket",
                          color_discrete_map=_KOM_BUCKET_PALETTE,
                          labels={"ton": "총 톤", "bucket": ""})
            fig.update_layout(height=420, margin=dict(t=10, b=10),
                              showlegend=False)
            st.plotly_chart(fig, width="stretch")
        with cB:
            st.markdown("**월별 톤수 추이 (카테고리 누적)**")
            mt = (f.groupby(["period", "bucket"])["ton"].sum()
                       .reset_index().sort_values("period"))
            fig = px.area(mt, x="period", y="ton",
                           color="bucket",
                           color_discrete_map=_KOM_BUCKET_PALETTE,
                           labels={"period": "월", "ton": "톤"})
            fig.update_layout(height=420, margin=dict(t=10, b=10),
                              legend=dict(orientation="h", y=-0.2,
                                           font=dict(size=10)))
            st.plotly_chart(fig, width="stretch")

        cC, cD = st.columns(2)
        with cC:
            st.markdown("**선종 × 카테고리 매트릭스** (톤)")
            xt = (f.groupby(["vessel_class", "bucket"])["ton"]
                       .sum().reset_index())
            if xt.empty:
                st.info("매트릭스 데이터 없음")
            else:
                pivot = xt.pivot(index="vessel_class", columns="bucket",
                                   values="ton").fillna(0)
                # Order rows by total tonnage
                pivot = pivot.loc[pivot.sum(axis=1).sort_values(
                    ascending=False).index]
                fig = px.imshow(pivot, aspect="auto",
                                 color_continuous_scale=theme.SCALES["blue"],
                                 labels=dict(x="화물 카테고리",
                                              y="선종",
                                              color="톤"))
                fig.update_layout(height=420, margin=dict(t=20, b=20))
                st.plotly_chart(fig, width="stretch")
        with cD:
            st.markdown("**선종별 월별 톤수 추이**")
            mc = (f.groupby(["period", "vessel_class"])["ton"]
                       .sum().reset_index().sort_values("period"))
            if mc.empty:
                st.info("데이터 없음")
            else:
                fig = px.area(mc, x="period", y="ton",
                                color="vessel_class",
                                color_discrete_map=_CARGO_CLASS_PALETTE,
                                labels={"period": "월", "ton": "톤",
                                          "vessel_class": "선종"})
                fig.update_layout(height=420, margin=dict(t=10, b=10),
                                  legend=dict(orientation="h", y=-0.2,
                                               font=dict(size=10)))
                st.plotly_chart(fig, width="stretch")

        st.markdown("**Top 화물 (raw komoditi 텍스트 기준)**")
        kom_top = (f.dropna(subset=["kom"])
                       .groupby(["kom", "bucket"])
                       .agg(톤=("ton", "sum"),
                            행수=("ton", "size"),
                            선박수=("kapal", "nunique"))
                       .reset_index().sort_values("톤", ascending=False)
                       .head(30))
        kom_top["톤"] = kom_top["톤"].round(0)
        theme.dataframe(kom_top)
        _csv_button(kom_top, f"cargo_top_komoditi_{snapshot}.csv",
                     key="cg_dl_komtop")

        st.markdown("**Top 운영사 (총 톤)**")
        op_top = (f.dropna(subset=["operator"])
                       .groupby("operator")
                       .agg(톤=("ton", "sum"),
                            행수=("ton", "size"),
                            선박수=("kapal", "nunique"))
                       .reset_index().sort_values("톤", ascending=False)
                       .head(25))
        op_top["톤"] = op_top["톤"].round(0)
        theme.dataframe(op_top)
        _csv_button(op_top, f"cargo_top_operators_{snapshot}.csv",
                     key="cg_dl_optop")

    # ============ 2) OD Map ============
    with tab_map:
        st.subheader("🗺️ 화물 OD 흐름 지도")
        st.caption(
            "버블 = 항구별 총 톤, 선 두께 ∝ 항로 톤, 색상 = 화물 카테고리. "
            "외국 항구는 지도 밖 — KPI에 합산."
        )
        _cargo_od_map(f, top_n=top_n_lanes, key_prefix="cg_map")

        st.markdown("---")

        # ---- Sankey of top OD pairs ----
        st.subheader("🔀 OD Sankey (Top 항로)")
        st.caption(
            "출발 항구 → 도착 항구 흐름. 화살 두께 ∝ 톤. self-loop "
            "(origin = destination, 즉 STS 자체 이동) 제외."
        )
        od_pairs = (f.dropna(subset=["origin", "destination"])
                       .assign(o_norm=lambda d: d["origin"].map(_normalize_port_name),
                                d_norm=lambda d: d["destination"].map(_normalize_port_name))
                       .dropna(subset=["o_norm", "d_norm"]))
        od_pairs = od_pairs[od_pairs["o_norm"] != od_pairs["d_norm"]]
        od_top = (od_pairs.groupby(["o_norm", "d_norm"])["ton"].sum()
                            .reset_index()
                            .rename(columns={"o_norm": "origin",
                                              "d_norm": "destination",
                                              "ton": "총_톤"})
                            .sort_values("총_톤", ascending=False))
        sankey_top_n = st.slider("Sankey Top N", 10, 80, 30, 5,
                                    key="cg_sankey_n")
        _render_sankey(od_top.head(sankey_top_n), ton_col="총_톤")

        st.markdown("---")

        # ---- YoY growth analysis ----
        st.subheader("📈 항로 YoY 성장 분석 (최근 vs 직전 기간)")
        st.caption(
            "현재 필터된 기간을 절반으로 나눠 후반(latest) vs 전반(prior) "
            "톤수 변화를 비교. 후반 톤 ≥ 50,000 행만 표시 — 단일 운송 노이즈 컷."
        )
        # Use the periods currently in `f` (already period-filtered by sidebar)
        periods_in_f = sorted(f["period"].dropna().unique().tolist())
        half = len(periods_in_f) // 2
        if half < 2 or len(periods_in_f) < 4:
            st.info("성장률 분석은 4개월 이상 필터 시 가능 (현재 "
                     f"{len(periods_in_f)}개월).")
        else:
            latest_set = set(periods_in_f[-half:])
            prior_set = set(periods_in_f[:half] if half * 2 == len(periods_in_f)
                            else periods_in_f[-2 * half:-half])
            yoy = od_pairs.assign(side=od_pairs["period"].map(
                lambda p: "latest" if p in latest_set
                else ("prior" if p in prior_set else None)))
            yoy = yoy.dropna(subset=["side"])
            agg = (yoy.groupby(["o_norm", "d_norm", "side"])["ton"].sum()
                       .unstack(fill_value=0).reset_index())
            if "latest" not in agg.columns: agg["latest"] = 0
            if "prior" not in agg.columns: agg["prior"] = 0
            agg = agg[(agg["prior"] >= 50_000) | (agg["latest"] >= 50_000)]
            agg["delta_ton"] = agg["latest"] - agg["prior"]
            agg["growth_pct"] = ((agg["latest"] - agg["prior"])
                                    / agg["prior"].replace(0, pd.NA) * 100)
            agg = agg.dropna(subset=["growth_pct"])
            agg["growth_pct"] = agg["growth_pct"].round(1)

            if agg.empty:
                st.info("성장률 분석할 항로가 없습니다.")
            else:
                cA, cB = st.columns(2)
                with cA:
                    st.markdown("**🚀 Top 성장 항로**")
                    growers = agg.sort_values("delta_ton",
                                                 ascending=False).head(15)
                    growers["route"] = (growers["o_norm"] + " → "
                                          + growers["d_norm"])
                    fig = px.bar(growers.sort_values("delta_ton"),
                                  x="delta_ton", y="route", orientation="h",
                                  color="growth_pct",
                                  color_continuous_scale=theme.SCALES["green"],
                                  hover_data=["latest", "prior", "growth_pct"],
                                  labels={"delta_ton": "증가 톤",
                                            "route": "",
                                            "growth_pct": "%"})
                    fig.update_layout(height=460, margin=dict(t=10, b=10),
                                       coloraxis_showscale=True)
                    st.plotly_chart(fig, width="stretch")
                with cB:
                    st.markdown("**📉 Top 감소 항로**")
                    losers = agg.sort_values("delta_ton",
                                                ascending=True).head(15)
                    losers["route"] = (losers["o_norm"] + " → "
                                         + losers["d_norm"])
                    fig = px.bar(losers.sort_values("delta_ton",
                                                       ascending=False),
                                  x="delta_ton", y="route", orientation="h",
                                  color="growth_pct",
                                  color_continuous_scale=theme.SCALES["red"],
                                  hover_data=["latest", "prior", "growth_pct"],
                                  labels={"delta_ton": "감소 톤 (음수)",
                                            "route": "",
                                            "growth_pct": "%"})
                    fig.update_layout(height=460, margin=dict(t=10, b=10),
                                       coloraxis_showscale=True)
                    st.plotly_chart(fig, width="stretch")

                # Table
                with st.expander("📋 전체 YoY 변동 테이블"):
                    show = agg[["o_norm", "d_norm", "prior", "latest",
                                  "delta_ton", "growth_pct"]].rename(
                        columns={"o_norm": "출발", "d_norm": "도착",
                                  "prior": "전반", "latest": "후반",
                                  "delta_ton": "증감",
                                  "growth_pct": "성장률_%"})
                    show["전반"] = show["전반"].round(0)
                    show["후반"] = show["후반"].round(0)
                    show["증감"] = show["증감"].round(0)
                    theme.dataframe(show.sort_values("증감", ascending=False))
                    _csv_button(show, f"cargo_yoy_routes_{snapshot}.csv",
                                 label="📥 YoY 항로 CSV", key="cg_dl_yoy")

    # ============ 3) Per-port ============
    with tab_port:
        st.markdown("**항구별 톤수 Top 30** (origin / destination 합산)")
        po = pd.concat([
            f[["origin", "ton"]].rename(columns={"origin": "port"}),
            f[["destination", "ton"]].rename(columns={"destination": "port"}),
        ], ignore_index=True).dropna(subset=["port"])
        po["port_norm"] = po["port"].map(_normalize_port_name)
        port_agg = (po.dropna(subset=["port_norm"])
                       .groupby("port_norm")["ton"].sum()
                       .sort_values(ascending=False).head(30)
                       .reset_index())
        if port_agg.empty:
            st.info("항구 데이터 없음")
        else:
            fig = px.bar(port_agg.sort_values("ton"),
                          x="ton", y="port_norm", orientation="h",
                          color="ton",
                          color_continuous_scale=theme.SCALES["blue"],
                          labels={"port_norm": "", "ton": "총 톤"})
            fig.update_layout(height=620, margin=dict(t=10, b=10),
                              coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")

        st.markdown("**카테고리 × 항구 매트릭스** (Top 20 항구)")
        top20 = set(port_agg.head(20)["port_norm"].tolist())
        cb = pd.concat([
            f[["origin", "bucket", "ton"]].rename(columns={"origin": "port"}),
            f[["destination", "bucket", "ton"]].rename(
                columns={"destination": "port"}),
        ], ignore_index=True).dropna(subset=["port"])
        cb["port_norm"] = cb["port"].map(_normalize_port_name)
        cb = cb[cb["port_norm"].isin(top20)]
        if cb.empty:
            st.info("매트릭스 데이터 없음")
        else:
            pivot = (cb.groupby(["port_norm", "bucket"])["ton"].sum()
                        .reset_index()
                        .pivot(index="port_norm", columns="bucket",
                                values="ton").fillna(0))
            fig = px.imshow(pivot, aspect="auto",
                             color_continuous_scale=theme.SCALES["blue"],
                             labels=dict(x="카테고리", y="항구",
                                          color="톤"))
            fig.update_layout(height=520, margin=dict(t=20, b=20))
            st.plotly_chart(fig, width="stretch")

    # ============ 4) International trade ============
    with tab_intl:
        st.subheader("🌐 국제 무역 — 외국 항구가 endpoint인 화물 흐름")
        st.caption(
            "**정의**: origin 또는 destination이 외국 항구 사전(SINGAPORE / "
            "PORT KLANG / KAOHSIUNG / RAS TANURA 등 ~40개)에 매칭된 행. "
            "**EXPORT** = origin이 ID, destination이 외국. "
            "**IMPORT** = origin이 외국, destination이 ID. "
            "**Transshipment** = 양쪽 모두 외국 (LK3에 거의 없음)."
        )

        _coord_map, _foreign = _port_name_to_coords()
        intl = f.copy()
        intl["o_norm"] = intl["origin"].map(_normalize_port_name)
        intl["d_norm"] = intl["destination"].map(_normalize_port_name)
        intl["o_foreign"] = intl["o_norm"].isin(_foreign)
        intl["d_foreign"] = intl["d_norm"].isin(_foreign)
        intl = intl[intl["o_foreign"] | intl["d_foreign"]].copy()

        if intl.empty:
            st.info(
                "현재 필터에 국제 항해 행이 없습니다. 화물 카테고리 / 기간 / "
                "운영사 필터를 풀어보세요."
            )
        else:
            def _direction(r):
                if r.o_foreign and r.d_foreign:
                    return "Transshipment"
                return "IMPORT" if r.o_foreign else "EXPORT"

            intl["trade"] = intl.apply(_direction, axis=1)
            intl["foreign_port"] = intl.apply(
                lambda r: r.o_norm if r.o_foreign else r.d_norm, axis=1)
            intl["id_port"] = intl.apply(
                lambda r: r.d_norm if r.o_foreign else r.o_norm, axis=1)

            total_intl = float(intl["ton"].sum())
            export_ton = float(intl.loc[intl["trade"] == "EXPORT",
                                          "ton"].sum())
            import_ton = float(intl.loc[intl["trade"] == "IMPORT",
                                          "ton"].sum())
            total_all = float(f["ton"].sum())
            share = (total_intl / total_all * 100) if total_all else 0
            n_foreign = int(intl["foreign_port"].nunique())

            cols = st.columns(5)
            kpi(cols[0], "국제 톤 합", fmt.fmt_ton(total_intl))
            kpi(cols[1], "EXPORT 톤", fmt.fmt_ton(export_ton),
                help="origin = ID, destination = 외국")
            kpi(cols[2], "IMPORT 톤", fmt.fmt_ton(import_ton),
                help="origin = 외국, destination = ID")
            kpi(cols[3], "전체 비중", fmt.fmt_pct(share),
                help="필터 화물 중 국제 항해의 톤 비중")
            kpi(cols[4], "외국 endpoint 수", fmt.fmt_int(n_foreign))

            st.markdown("---")

            # ---- Top foreign endpoints ----
            cA, cB = st.columns(2)
            with cA:
                st.markdown("**Top 외국 항구 (총 톤)**")
                fp = (intl.groupby(["foreign_port", "trade"])["ton"].sum()
                          .reset_index())
                pivot = fp.pivot_table(index="foreign_port",
                                         columns="trade", values="ton",
                                         fill_value=0)
                for col in ("EXPORT", "IMPORT", "Transshipment"):
                    if col not in pivot.columns:
                        pivot[col] = 0
                pivot["Total"] = pivot.sum(axis=1)
                pivot = pivot.sort_values("Total",
                                            ascending=False).head(20)
                top_p = pivot.reset_index()
                fp_long = top_p.melt(
                    id_vars="foreign_port",
                    value_vars=["EXPORT", "IMPORT", "Transshipment"],
                    var_name="trade", value_name="ton")
                fp_long = fp_long[fp_long["ton"] > 0]
                fig = px.bar(fp_long, x="ton", y="foreign_port",
                              color="trade", orientation="h",
                              barmode="stack",
                              color_discrete_map={
                                  "EXPORT": "#16a34a",
                                  "IMPORT": "#dc2626",
                                  "Transshipment": "#7c3aed"},
                              labels={"foreign_port": "",
                                       "ton": "톤", "trade": ""})
                fig.update_layout(height=500, margin=dict(t=10, b=10),
                                  legend=dict(orientation="h", y=-0.1,
                                               font=dict(size=10)),
                                  yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, width="stretch")

            with cB:
                st.markdown("**국제 무역 화물 카테고리 mix**")
                cm = (intl.groupby("bucket")["ton"].sum()
                          .sort_values(ascending=False).reset_index())
                cm = cm[cm["ton"] > 0]
                if cm.empty:
                    st.info("국제 무역 카테고리 데이터 없음")
                else:
                    fig = px.pie(cm, names="bucket", values="ton",
                                  color="bucket",
                                  color_discrete_map=_KOM_BUCKET_PALETTE,
                                  hole=0.5)
                    fig.update_traces(textinfo="percent+label",
                                        textposition="outside")
                    fig.update_layout(height=500, margin=dict(t=10, b=10),
                                       legend=dict(font=dict(size=10)))
                    theme.donut_center(fig, fmt.fmt_ton(float(cm["ton"].sum())),
                                         "국제 톤")
                    st.plotly_chart(fig, width="stretch")

            # ---- Top intl routes (ID port ↔ foreign port) ----
            st.markdown("**Top 국제 항로 (ID 항구 ↔ 외국 항구)**")
            route_top = (intl.groupby(["id_port", "foreign_port",
                                         "trade", "bucket"])
                              .agg(톤=("ton", "sum"),
                                   행수=("ton", "size"),
                                   선박수=("kapal", "nunique"))
                              .reset_index()
                              .sort_values("톤", ascending=False).head(40))
            route_top["톤"] = route_top["톤"].round(0)
            theme.dataframe(route_top)
            _csv_button(route_top, f"cargo_intl_routes_{snapshot}.csv",
                         label="📥 국제 항로 CSV", key="cg_dl_intl")

            # ---- ID port export/import pair table ----
            st.markdown("**ID 항구별 EXPORT / IMPORT 균형**")
            id_pair = (intl.groupby(["id_port", "trade"])["ton"]
                            .sum().reset_index()
                            .pivot_table(index="id_port", columns="trade",
                                          values="ton", fill_value=0))
            for col in ("EXPORT", "IMPORT", "Transshipment"):
                if col not in id_pair.columns:
                    id_pair[col] = 0
            id_pair["Net_Export"] = id_pair["EXPORT"] - id_pair["IMPORT"]
            id_pair["Total"] = (id_pair["EXPORT"] + id_pair["IMPORT"]
                                  + id_pair["Transshipment"])
            id_pair = id_pair.sort_values("Total", ascending=False).head(20)
            for c in ("EXPORT", "IMPORT", "Transshipment",
                       "Net_Export", "Total"):
                id_pair[c] = id_pair[c].round(0)
            theme.dataframe(id_pair.reset_index())

    # ============ 5) STS / self-loop analysis ============
    with tab_sts:
        st.subheader("🔄 STS (Ship-to-Ship) / 자체 환적")
        st.caption(
            "**정의**: LK3 행 중 origin = destination (동일 항구) — 정유 단지·터미널 "
            "내부 환적이나 닻 정박 중 STS 운영을 의미. "
            "한국 메모리: 2026-05 기준 ID 탱커 LK3의 약 40%가 self-loop, 약 252M 톤 "
            "(Pertamina Trans Kontinental이 50%+ 점유). "
            "본 sub-tab은 **현재 필터 (선종·카테고리·기간·운영사 등)에 한정**."
        )
        sts = f.copy()
        sts["o_norm"] = sts["origin"].map(_normalize_port_name)
        sts["d_norm"] = sts["destination"].map(_normalize_port_name)
        sts = sts.dropna(subset=["o_norm", "d_norm"])
        sts = sts[sts["o_norm"] == sts["d_norm"]].copy()
        sts["hub"] = sts["o_norm"]

        if sts.empty:
            st.info("현재 필터에 self-loop (STS) 행이 없습니다.")
        else:
            total_ton_all = float(f["ton"].sum())
            sts_ton = float(sts["ton"].sum())
            sts_share = (sts_ton / total_ton_all * 100) if total_ton_all else 0
            n_hubs = int(sts["hub"].nunique())
            n_op = int(sts["operator"].dropna().nunique())
            n_kapal = int(sts["kapal"].dropna().nunique())

            cols = st.columns(5)
            kpi(cols[0], "STS 톤 합", fmt.fmt_ton(sts_ton))
            kpi(cols[1], "전체 대비", fmt.fmt_pct(sts_share),
                help="현재 필터 화물 중 self-loop 톤 비중")
            kpi(cols[2], "STS 허브 수", fmt.fmt_int(n_hubs))
            kpi(cols[3], "STS 운영사", fmt.fmt_int(n_op))
            kpi(cols[4], "STS 선박", fmt.fmt_int(n_kapal))

            st.markdown("---")

            # ---- Top hubs & top operators ----
            cA, cB = st.columns(2)
            with cA:
                st.markdown("**Top STS 허브 (총 톤)**")
                hub_ton = (sts.groupby("hub")["ton"].sum()
                                .sort_values(ascending=False).head(20)
                                .reset_index())
                fig = px.bar(hub_ton.sort_values("ton"),
                              x="ton", y="hub", orientation="h",
                              color="ton",
                              color_continuous_scale=theme.SCALES["blue"],
                              labels={"hub": "", "ton": "톤"})
                fig.update_layout(height=520, margin=dict(t=10, b=10),
                                   coloraxis_showscale=False)
                st.plotly_chart(fig, width="stretch")

            with cB:
                st.markdown("**Top STS 운영사 (총 톤)**")
                op_ton = (sts.dropna(subset=["operator"])
                                .groupby("operator")["ton"].sum()
                                .sort_values(ascending=False).head(20)
                                .reset_index())
                fig = px.bar(op_ton.sort_values("ton"),
                              x="ton", y="operator", orientation="h",
                              color="ton",
                              color_continuous_scale=theme.SCALES["amber"],
                              labels={"operator": "", "ton": "톤"})
                fig.update_layout(height=520, margin=dict(t=10, b=10),
                                   coloraxis_showscale=False)
                st.plotly_chart(fig, width="stretch")

            # ---- STS commodity mix + monthly trend ----
            cC, cD = st.columns(2)
            with cC:
                st.markdown("**STS 화물 카테고리 mix**")
                cm = (sts.groupby("bucket")["ton"].sum()
                          .sort_values(ascending=False).reset_index())
                cm = cm[cm["ton"] > 0]
                if cm.empty:
                    st.info("STS 카테고리 데이터 없음")
                else:
                    fig = px.pie(cm, names="bucket", values="ton",
                                  color="bucket",
                                  color_discrete_map=_KOM_BUCKET_PALETTE,
                                  hole=0.5)
                    fig.update_traces(textinfo="percent+label",
                                        textposition="outside")
                    fig.update_layout(height=420, margin=dict(t=10, b=10),
                                       legend=dict(font=dict(size=10)))
                    theme.donut_center(fig, fmt.fmt_ton(sts_ton),
                                         "STS 톤")
                    st.plotly_chart(fig, width="stretch")
            with cD:
                st.markdown("**STS 월별 톤수 추이 (카테고리 누적)**")
                mt = (sts.groupby(["period", "bucket"])["ton"].sum()
                           .reset_index().sort_values("period"))
                if mt.empty:
                    st.info("월별 데이터 없음")
                else:
                    fig = px.area(mt, x="period", y="ton",
                                   color="bucket",
                                   color_discrete_map=_KOM_BUCKET_PALETTE,
                                   labels={"period": "월", "ton": "톤"})
                    fig.update_layout(height=420, margin=dict(t=10, b=10),
                                       legend=dict(orientation="h", y=-0.2,
                                                    font=dict(size=10)))
                    st.plotly_chart(fig, width="stretch")

            # ---- HHI of STS hub concentration ----
            st.markdown("##### STS 허브 집중도 (HHI)")
            hub_pct = (hub_ton["ton"] / hub_ton["ton"].sum() * 100)
            hhi = float((hub_pct ** 2).sum())
            band = ("저집중" if hhi < 1500
                     else "중집중" if hhi < 2500
                     else "고집중")
            cE = st.columns(4)
            kpi(cE[0], "Top-20 HHI", f"{hhi:,.0f}",
                help="KPPU 기준 1500/2500 — 0~10,000 percent-share HHI")
            kpi(cE[1], "Top-1 점유율",
                fmt.fmt_pct(float(hub_pct.max())))
            kpi(cE[2], "Top-3 누적",
                fmt.fmt_pct(float(hub_pct.head(3).sum())))
            kpi(cE[3], "분류", band)

            # ---- Detail table ----
            st.markdown("##### STS 허브 × 운영사 × 카테고리 Top 50")
            tbl = (sts.groupby(["hub", "operator", "bucket"])["ton"]
                        .sum().reset_index()
                        .sort_values("ton", ascending=False).head(50))
            tbl["ton"] = tbl["ton"].round(0)
            tbl = tbl.rename(columns={"hub": "STS_허브",
                                          "operator": "운영사",
                                          "bucket": "카테고리",
                                          "ton": "톤"})
            theme.dataframe(tbl)
            _csv_button(tbl, f"cargo_sts_detail_{snapshot}.csv",
                         label="📥 STS 상세 CSV", key="cg_dl_sts")

    # ============ 6) Detail list ============
    with tab_list:
        st.markdown(
            "**상세 화물 행 리스트** — 현재 필터에 매치되는 LK3 raw 행 (정렬·CSV)"
        )
        cA, cB = st.columns([1, 1])
        with cA:
            sort_col = st.selectbox(
                "정렬 기준",
                ["ton", "period", "kapal", "operator", "origin",
                 "destination", "bucket"],
                key="cg_sort_col",
            )
        with cB:
            sort_dir = st.radio(
                "정렬 방향", ["내림차순", "오름차순"], horizontal=True,
                key="cg_sort_dir",
            )
        ascending = sort_dir == "오름차순"
        tbl = f.sort_values(sort_col, ascending=ascending,
                               na_position="last")

        show_cols = ["period", "direction", "bucket", "kom",
                      "kapal", "operator", "jenis_kapal", "vessel_class",
                      "origin", "destination", "ton", "gt", "dwt"]
        show_cols = [c for c in show_cols if c in tbl.columns]
        tbl_show = tbl[show_cols].head(3000).copy()
        tbl_show["ton"] = tbl_show["ton"].round(1)
        st.caption(f"표시 {len(tbl_show):,} / 필터 {len(f):,} rows (최대 3,000)")
        theme.dataframe(tbl_show)
        _csv_button(tbl[show_cols], f"cargo_flows_{snapshot}.csv",
                     label="📥 화물 흐름 CSV (필터 전체)",
                     key="cg_csv_full")


def page_changes():
    st.title("🔄 Changes")
    st.caption(f"Change month: **{change_month}**")
    k = _change_kpis(change_month)

    cols = st.columns(6)
    kpi(cols[0], "선박 ADDED", k["vessel_added"])
    kpi(cols[1], "선박 REMOVED", k["vessel_removed"])
    kpi(cols[2], "선박 MODIFIED", k["vessel_modified_cells"])
    kpi(cols[3], "Cargo ADDED", k["cargo_added"])
    kpi(cols[4], "Cargo REMOVED", k["cargo_removed"])
    kpi(cols[5], "Cargo REVISED 셀", k["cargo_revised_cells"])

    tab_v, tab_c = st.tabs(["선박 변경", "물동량 변경"])

    with tab_v:
        col1, col2, col3 = st.columns([1, 1, 3])
        ct = col1.selectbox("type", ["ALL", "ADDED", "REMOVED", "MODIFIED"], key="vct")
        fields = ["ALL", "nama_kapal", "call_sign", "jenis_kapal", "nama_pemilik",
                  "gt", "panjang", "lebar", "dalam", "imo", "tahun", "tpk"]
        fn = col2.selectbox("field", fields, key="vfn")
        s = col3.text_input("검색", key="vsrch")
        df = q.vessel_changes(change_month, change_type=ct, field_name=fn, search=s, limit=5000)
        st.caption(f"{len(df):,} rows (limit 5000)")
        theme.dataframe(df)

    with tab_c:
        col1, col2, col3 = st.columns([1, 1, 2])
        ct = col1.selectbox("type", ["ALL", "ADDED", "REMOVED", "REVISED"], key="cct")
        kind = col2.selectbox("kind", ["ALL", "dn", "ln"], key="ckd")
        ports_df = _ports()
        port_options = ["ALL"] + ports_df["kode_pelabuhan"].tolist()
        p = col3.selectbox("port", port_options, key="cprt")
        df = q.cargo_changes(change_month, change_type=ct, port=p, kind=kind, limit=5000)
        st.caption(f"{len(df):,} rows (limit 5000)")
        theme.dataframe(df)


def page_data_quality():
    st.title("🔍 데이터 품질")
    st.caption(
        f"Snapshot: **{snapshot}** · validator 활동, 커버리지 갭, "
        "스크레이프 실패를 한눈에 확인"
    )

    cov = _coverage_status(snapshot)
    vs = _validator_summary(snapshot)

    # ---- KPI hero ----
    fleet_fixes = sum(vs.get("fleet", {}).values())
    cargo_fixes = sum(vs.get("cargo", {}).values())
    cargo_cov_pct = (
        cov["cargo_key_count"] / cov["cargo_key_expected"] * 100
        if cov["cargo_key_expected"] else 0
    )

    cols = st.columns(5)
    kpi(cols[0], "Fleet 보정 건수",
        fmt.fmt_int(fleet_fixes),
        help="vessels_validation_log에 기록된 누적 자동 보정 셀 수")
    kpi(cols[1], "Cargo 보정 건수",
        fmt.fmt_int(cargo_fixes),
        help="cargo_validation_log에 기록된 누적 자동 보정 셀 수")
    kpi(cols[2], "Search 코드",
        f"{cov['fleet_codes_present']}/{cov['fleet_codes_expected']}",
        help=f"56개 카테고리 코드 중 데이터가 적재된 코드 수. 누락 코드: "
             f"{', '.join(cov['fleet_codes_missing']) or '없음'}")
    kpi(cols[3], "Cargo 기간 커버",
        f"{cov['cargo_period_count']} 개월",
        help="이 스냅샷에 포함된 LK3 기간 수 (정상 ≥ 24)")
    kpi(cols[4], "Cargo 키 커버",
        fmt.fmt_pct(cargo_cov_pct),
        help=f"(port × period × kind) 키 커버율. 보유 {cov['cargo_key_count']:,} / "
             f"이론 {cov['cargo_key_expected']:,}")

    st.markdown("---")

    tab_v, tab_cov, tab_anom, tab_runs = st.tabs(
        ["✅ Validator 활동", "📦 커버리지 매트릭스",
         "🚨 Anomaly Alerts", "⚙️ Ingestion 이력"])

    # ----- Tab 1: Validator activity -----
    with tab_v:
        st.subheader("Validator 보정 분포")
        # Fleet
        if vs.get("fleet"):
            fdf = pd.DataFrame(
                [{"field": k, "건수": v} for k, v in vs["fleet"].items()]
            ).sort_values("건수", ascending=False)
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown("##### 🚢 Fleet (vessels_validation_log)")
                theme.dataframe(fdf)
            with c2:
                fig = px.bar(fdf.sort_values("건수"), x="건수", y="field",
                             orientation="h", color="건수",
                             color_continuous_scale=theme.SCALES["blue"])
                fig.update_layout(height=240, margin=dict(t=10, b=10),
                                  yaxis_title="", coloraxis_showscale=False)
                st.plotly_chart(fig, width="stretch")
        else:
            st.info("Fleet validator 로그 없음")

        # Cargo
        if vs.get("cargo"):
            cdf = pd.DataFrame(
                [{"field": k, "건수": v} for k, v in vs["cargo"].items()]
            ).sort_values("건수", ascending=False)
            cdf["field_short"] = cdf["field"].str.replace(
                "('", "", regex=False).str.replace("')", "", regex=False) \
                                              .str.replace("', '", ".", regex=False)
            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown("##### 🌊 Cargo (cargo_validation_log)")
                st.dataframe(cdf[["field_short", "건수"]],
                             width="stretch", hide_index=True)
            with c2:
                fig = px.bar(cdf.sort_values("건수"),
                             x="건수", y="field_short", orientation="h",
                             color="건수", color_continuous_scale=theme.SCALES["green"])
                fig.update_layout(height=320, margin=dict(t=10, b=10),
                                  yaxis_title="", coloraxis_showscale=False)
                st.plotly_chart(fig, width="stretch")
        else:
            st.info("Cargo validator 로그 없음")

        st.markdown("---")
        st.subheader("최근 보정 샘플")
        side = st.radio("대상 테이블", ["Fleet", "Cargo"], horizontal=True,
                        key="dq_recent_side")
        limit = st.slider("최대 행 수", 50, 1000, 200, 50, key="dq_recent_limit")
        target = "vessels" if side == "Fleet" else "cargo"
        rec = _validator_recent(target, snapshot, limit)
        if rec.empty:
            st.info(f"{side} 보정 로그가 비어있습니다 (현 스냅샷)")
        else:
            # Compute magnitude shift to surface the noisiest fixes
            rec = rec.copy()
            rec["magnitude_x"] = (rec["original_value"]
                                   / rec["corrected_value"].replace(0, pd.NA)).round(0)
            theme.dataframe(rec)
            _csv_button(rec,
                        f"validator_recent_{side.lower()}_{snapshot}.csv",
                        label="📥 보정 샘플 CSV", key="dq_dl_recent")

    # ----- Tab 2: Coverage matrix -----
    with tab_cov:
        st.subheader("Fleet search-code 커버리지")
        from backend.config import SEARCH_CODES
        cov_df = pd.DataFrame({"code": SEARCH_CODES})
        cov_df["적재"] = cov_df["code"].isin(
            set(SEARCH_CODES) - set(cov["fleet_codes_missing"]))
        # Per-code count
        with engine.connect() as conn:
            counts = pd.read_sql(text(
                "SELECT search_code AS code, COUNT(*) AS 척수 "
                "FROM vessels_snapshot WHERE snapshot_month = :m "
                "GROUP BY search_code"
            ), conn, params={"m": snapshot})
        cov_df = cov_df.merge(counts, on="code", how="left").fillna({"척수": 0})
        cov_df["척수"] = cov_df["척수"].astype(int)
        present_n = int(cov_df["적재"].sum())
        st.caption(
            f"{present_n}/{len(SEARCH_CODES)} 코드 적재됨. "
            "0척 코드가 있다면 해당 카테고리 스크레이프가 실패했거나 결과가 없는 카테고리."
        )
        st.dataframe(cov_df.sort_values("척수", ascending=False),
                     width="stretch", hide_index=True)

        st.markdown("---")
        st.subheader("Cargo (port × period × kind) 매트릭스")
        cs = _cargo_summary(snapshot)
        if cs.empty:
            st.info("LK3 데이터 없음")
        else:
            existing = set(zip(cs["kode_pelabuhan"], cs["period"], cs["kind"]))
            ports_df = _ports()
            periods = sorted(cs["period"].unique())
            ports_list = ports_df["kode_pelabuhan"].tolist()
            ideal = len(ports_list) * len(periods) * 2
            present = len(existing)
            cov_pct = present / ideal * 100 if ideal else 0
            cN = st.columns(4)
            kpi(cN[0], "이론 키", fmt.fmt_int(ideal),
                help=f"{len(ports_list)} 항구 × {len(periods)} 기간 × 2 kind")
            kpi(cN[1], "보유 키", fmt.fmt_int(present))
            kpi(cN[2], "커버율", fmt.fmt_pct(cov_pct))
            kpi(cN[3], "결측 키", fmt.fmt_int(ideal - present))

            # Top-15 ports with most missing periods
            st.markdown("##### 결측 가장 많은 항구 Top 15")
            missing_rows = []
            for p in ports_list:
                miss = sum(1 for per in periods for k in ("dn", "ln")
                           if (p, per, k) not in existing)
                if miss > 0:
                    missing_rows.append({"port": p, "missing_keys": miss})
            mdf = pd.DataFrame(missing_rows).sort_values(
                "missing_keys", ascending=False).head(15)
            mdf = mdf.merge(ports_df, left_on="port",
                              right_on="kode_pelabuhan", how="left")
            st.dataframe(
                mdf[["port", "nama_pelabuhan", "missing_keys"]],
                width="stretch", hide_index=True,
            )
            _csv_button(
                mdf[["port", "nama_pelabuhan", "missing_keys"]],
                f"missing_cargo_keys_top_{snapshot}.csv",
                label="📥 결측 항구 CSV", key="dq_dl_missing",
            )

        st.markdown("---")
        st.subheader("Cargo 기간별 행 수")
        if cov["cargo_periods"]:
            pdf = pd.DataFrame(cov["cargo_periods"])
            pdf["period"] = (pdf["year"].astype(str) + "-" +
                              pdf["month"].astype(int).map("{:02d}".format))
            fig = px.bar(pdf, x="period", y="rows",
                         color="rows", color_continuous_scale=theme.SCALES["blue"])
            fig.update_layout(height=320, margin=dict(t=10, b=10),
                              coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")
            st.caption(
                "스크레이프 시점의 부분 월(가장 최근 month)은 자연스럽게 작음. "
                "중간 월에 급락이 있으면 해당 기간 inaportnet 측 데이터 누락 가능성."
            )

    # ----- Tab 3: Anomaly Alerts (iteration #15) -----
    with tab_anom:
        st.subheader("🚨 극단적 보정 (Validator 통과)")
        st.caption(
            "Validator가 잡아낸 가장 큰 자리수 typo. "
            "magnitude_x = 원본 / 보정 비율. 1000 이상 = 원본이 정상값의 1000배 이상이었다는 뜻 — "
            "upstream 입력 시스템 점검 후보."
        )
        thr = st.select_slider(
            "Magnitude threshold (원본/보정 비율)",
            options=[100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000],
            value=1_000, key="dq_anom_thr",
            format_func=lambda v: f"{v:,}× 이상",
        )
        ext = _validator_extreme(snapshot, float(thr), 500)
        if ext.empty:
            st.success(f"✅ {thr:,}× 이상 극단 보정 없음")
        else:
            n_total = len(ext)
            n_cargo = int((ext["source"] == "cargo").sum())
            n_fleet = int((ext["source"] == "vessels").sum())
            cols = st.columns(4)
            kpi(cols[0], "총 극단 보정", fmt.fmt_int(n_total))
            kpi(cols[1], "Cargo 측", fmt.fmt_int(n_cargo))
            kpi(cols[2], "Fleet 측", fmt.fmt_int(n_fleet))
            kpi(cols[3], "최대 magnitude",
                fmt.fmt_compact(ext["magnitude_x"].abs().max(), 0) + "×",
                help="원본 / 보정 비율의 최대치 — 가장 spectacular한 typo")

            # Distribution by field
            by_field = (ext.groupby(["source", "field"])
                            .size().reset_index(name="건수")
                            .sort_values("건수", ascending=False))
            st.markdown("##### 필드별 극단 보정 건수")
            theme.dataframe(by_field)

            st.markdown("##### Top 50 극단 보정 (magnitude 큰 순)")
            disp = ext.head(50).copy()
            disp["original_value"] = disp["original_value"].apply(
                lambda v: f"{v:,.4g}" if pd.notna(v) else "-")
            disp["corrected_value"] = disp["corrected_value"].apply(
                lambda v: f"{v:,.4g}" if pd.notna(v) else "-")
            theme.dataframe(disp)
            _csv_button(ext, f"validator_extreme_{snapshot}.csv",
                        key="dq_anom_dl_ext")

        st.markdown("---")
        st.subheader("⚠️ 잔여 비정상 (Validator 통과 후에도 비정상)")
        st.caption(
            "Validator가 보존적 알고리즘으로 fix를 못한 행. 사람이 수기로 검토하거나 "
            "다음 iteration에서 validator 룰 보강 대상."
        )
        residual = _residual_fleet_anomalies(snapshot)
        if residual.empty:
            st.success("✅ Fleet 측 잔여 비정상 없음")
        else:
            cols = st.columns(4)
            kpi(cols[0], "잔여 행 수", fmt.fmt_int(len(residual)))
            big_loa = int(((residual["panjang"] > 500) |
                            (residual["length_of_all"] > 500)).sum())
            kpi(cols[1], "panjang/loa > 500m", fmt.fmt_int(big_loa))
            wider = int(((residual["lebar"].fillna(0) > 0)
                         & (residual["panjang"].fillna(0) > 0)
                         & (residual["lebar"] > residual["panjang"])).sum())
            kpi(cols[2], "lebar > panjang", fmt.fmt_int(wider),
                help="폭 > 길이 — 물리적 불가능 케이스")
            big_lebar = int((residual["lebar"] > 80).sum())
            kpi(cols[3], "lebar > 80m", fmt.fmt_int(big_lebar))

            theme.dataframe(residual)
            _csv_button(residual, f"residual_fleet_anomalies_{snapshot}.csv",
                        key="dq_anom_dl_res")

    # ----- Tab 4: Ingestion run history -----
    with tab_runs:
        runs = _ingestion_runs()
        if runs.empty:
            st.info("Ingestion run 기록 없음")
        else:
            # Status pill column
            def _emoji(s):
                return {"success": "✅", "partial": "⚠️", "failed": "❌",
                        "running": "⏳"}.get(str(s).lower(), str(s))
            disp = runs.copy()
            disp["status"] = disp["status"].map(_emoji)
            theme.dataframe(disp)
            _csv_button(runs, "ingestion_runs.csv",
                        label="📥 Ingestion runs CSV", key="dq_dl_runs")

            st.caption("선택한 run의 notes 보기")
            run_id = st.number_input(
                "run id", min_value=int(runs["id"].min()),
                max_value=int(runs["id"].max()),
                value=int(runs["id"].iloc[0]), step=1,
                key="dq_run_id",
            )
            notes = q.ingestion_run_notes(int(run_id))
            if notes:
                st.json(notes)


def page_ingestion():
    st.title("⚙️ Ingestion runs")
    runs = _ingestion_runs()
    if runs.empty:
        st.info("기록 없음")
        return
    theme.dataframe(runs)
    st.caption("선택한 run의 notes 보기")
    run_id = st.number_input("run id", min_value=int(runs["id"].min()),
                              max_value=int(runs["id"].max()),
                              value=int(runs["id"].iloc[0]), step=1)
    notes = q.ingestion_run_notes(int(run_id))
    if notes:
        st.json(notes)


PAGES = {
    "📊 Overview": page_overview,
    "🚢 Fleet": page_fleet,
    "🛢️ Tanker": page_tanker,
    "🇮🇩 Pertamina": page_pertamina,
    "📦 Cargo": page_cargo,
    "🔄 Changes": page_changes,
    "🔍 데이터 품질": page_data_quality,
    "⚙️ Ingestion": page_ingestion,
}
PAGES[page]()
