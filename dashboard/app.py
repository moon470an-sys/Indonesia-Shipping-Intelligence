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
import streamlit as st

from dashboard import queries as q

st.set_page_config(
    page_title="Indonesia Shipping BI",
    page_icon=":ship:",
    layout="wide",
    initial_sidebar_state="expanded",
)


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


# ------------------------- sidebar -------------------------
st.sidebar.markdown("### :ship: Indonesia Shipping BI")
v_months = _vessel_months()
c_months = _cargo_months()
all_snaps = sorted(set(v_months) | set(c_months), reverse=True)
if not all_snaps:
    st.sidebar.error("DB가 비어있습니다. 먼저 `python -m backend.main monthly --auto` 실행")
    st.stop()

snapshot = st.sidebar.selectbox("Snapshot month", all_snaps, index=0)

ch_months = _change_months()
change_month = st.sidebar.selectbox(
    "Change month", ch_months or [snapshot],
    index=0 if ch_months else 0,
    help="변경 탐지 결과를 볼 기준 달",
)

page = st.sidebar.radio(
    "페이지",
    ["📊 Overview", "🚢 Fleet", "📦 Cargo", "🔄 Changes", "⚙️ Ingestion"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.caption(f"DB: `data/shipping_bi.db`")
st.sidebar.caption(f"Vessel snapshots: {len(v_months)}")
st.sidebar.caption(f"Cargo snapshots: {len(c_months)}")


# ------------------------- helpers -------------------------
def kpi(col, label, value, delta=None, fmt="{:,}"):
    if isinstance(value, (int, float)):
        v = fmt.format(value) if isinstance(value, (int, float)) else str(value)
    else:
        v = str(value)
    col.metric(label, v, delta=delta)


# ------------------------- pages -------------------------

def page_overview():
    st.title("📊 Overview")
    st.caption(f"Snapshot: **{snapshot}** · Change month: **{change_month}**")

    v = _vessel_overview(snapshot)
    c = _cargo_overview(snapshot)
    k = _change_kpis(change_month)

    st.subheader("적재 현황")
    cols = st.columns(4)
    kpi(cols[0], "선박 등록", v["total"])
    kpi(cols[1], "검색 코드", f"{v['codes']}/56")
    kpi(cols[2], "항구", c["ports"])
    kpi(cols[3], "물동량 행", c["rows"])

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
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top 항구")
    pt = _port_traffic(snapshot, 20)
    if not pt.empty:
        fig = px.bar(pt, x="kode_pelabuhan", y="rows_total",
                     hover_data=["nama_pelabuhan", "rows_dn", "rows_ln", "months_covered"],
                     labels={"kode_pelabuhan": "항구 코드", "rows_total": "총 LK3 행 수"})
        fig.update_layout(height=380, margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)


def page_fleet():
    st.title("🚢 Fleet")
    st.caption(f"Snapshot: **{snapshot}**")

    v = _vessel_overview(snapshot)
    cols = st.columns(4)
    kpi(cols[0], "선박 등록", v["total"])
    kpi(cols[1], "검색 코드", f"{v['codes']}/56")
    kpi(cols[2], "평균 GT", f"{v['avg_gt']:,.0f}")
    kpi(cols[3], "최대 GT", f"{v['max_gt']:,.0f}")

    tab_dist, tab_owner, tab_search = st.tabs(["선종/연식 분포", "선사 Top", "선박 검색"])

    with tab_dist:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**선종 Top 30**")
            vt = _vessel_types(snapshot, 30)
            if vt.empty:
                st.info("선종 데이터 없음")
            else:
                fig = px.bar(vt.sort_values("count"), x="count", y="type",
                             orientation="h", height=560,
                             labels={"count": "척수", "type": "선종"})
                fig.update_layout(margin=dict(t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.markdown("**연식 분포**")
            va = _vessel_age(snapshot)
            if va.empty:
                st.info("연식 데이터 없음")
            else:
                fig = px.bar(va, x="tahun", y="count", height=300,
                             labels={"tahun": "연식", "count": "척수"})
                fig.update_layout(margin=dict(t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            st.markdown("**GT 분포 (log scale)**")
            gd = _gt_dist(snapshot)
            if gd.empty:
                st.info("GT 데이터 없음")
            else:
                fig = px.histogram(gd, x="gt", nbins=60, log_x=True, height=240)
                fig.update_layout(margin=dict(t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)

    with tab_owner:
        top = st.slider("Top N", 5, 100, 30, 5, key="owner_top")
        ow = _vessel_owners(snapshot, top)
        if ow.empty:
            st.info("선사 데이터 없음")
        else:
            st.dataframe(ow, use_container_width=True, hide_index=True)

    with tab_search:
        col1, col2, col3 = st.columns([3, 1, 2])
        search = col1.text_input("검색 (선명/콜사인/선사/IMO)")
        codes = ["(전체)"] + _vessel_codes(snapshot)
        sc = col2.selectbox("Code", codes)
        sc = "" if sc == "(전체)" else sc
        types_df = _vessel_types(snapshot, 200)
        types = ["(전체)"] + types_df["type"].dropna().tolist()
        jk = col3.selectbox("선종", types)
        jk = "" if jk == "(전체)" else jk
        df = q.vessels(snapshot, search=search, search_code=sc, jenis_kapal=jk, limit=2000)
        st.caption(f"{len(df):,} rows (limit 2000)")
        st.dataframe(df, use_container_width=True, hide_index=True)


def page_cargo():
    st.title("📦 Cargo (LK3)")
    st.caption(f"Snapshot: **{snapshot}**")

    c = _cargo_overview(snapshot)
    cols = st.columns(4)
    kpi(cols[0], "물동량 행", c["rows"])
    kpi(cols[1], "항구", c["ports"])
    kpi(cols[2], "(port,year,month,kind) 키", c["keys"])
    kpi(cols[3], "이론 키", 267 * 24 * 2)

    tab_top, tab_heat, tab_gaps = st.tabs(["Top 항구", "히트맵", "결측 점검"])

    with tab_top:
        top = st.slider("Top N 항구", 5, 100, 25, 5, key="cargo_top")
        pt = _port_traffic(snapshot, top)
        if pt.empty:
            st.info("LK3 데이터 없음")
        else:
            st.dataframe(pt, use_container_width=True, hide_index=True)
            fig = px.bar(pt, x="kode_pelabuhan", y=["rows_dn", "rows_ln"],
                         barmode="stack", height=380,
                         labels={"value": "행 수", "kode_pelabuhan": "항구"})
            fig.update_layout(margin=dict(t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

    with tab_heat:
        st.markdown("**(port × period) 행 수 히트맵** — 짙을수록 데이터 많음")
        cs = _cargo_summary(snapshot)
        if cs.empty:
            st.info("LK3 데이터 없음")
        else:
            kind = st.radio("kind", ["dn", "ln"], horizontal=True)
            sub = cs[cs["kind"] == kind]
            pivot = sub.pivot_table(index="kode_pelabuhan", columns="period",
                                     values="rows", aggfunc="sum", fill_value=0)
            pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).head(40).index]
            fig = px.imshow(pivot, aspect="auto", height=620,
                            color_continuous_scale="Blues",
                            labels=dict(x="기간", y="항구", color="행"))
            fig.update_layout(margin=dict(t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

    with tab_gaps:
        st.markdown("**결측 (port × period × kind) 키 점검**")
        cs = _cargo_summary(snapshot)
        if cs.empty:
            st.info("LK3 데이터 없음")
        else:
            existing = set(zip(cs["kode_pelabuhan"], cs["period"], cs["kind"]))
            ports_df = _ports()
            periods = sorted(cs["period"].unique())
            ports_list = ports_df["kode_pelabuhan"].tolist()
            missing_rows = []
            for p in ports_list:
                for per in periods:
                    for k in ("dn", "ln"):
                        if (p, per, k) not in existing:
                            missing_rows.append({"port": p, "period": per, "kind": k})
            mdf = pd.DataFrame(missing_rows)
            st.caption(f"누락 키: {len(mdf):,} (port {len(ports_list)} × period {len(periods)} × kind 2 - 보유 {len(existing):,})")
            if not mdf.empty:
                st.dataframe(mdf.head(2000), use_container_width=True, hide_index=True)


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
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_c:
        col1, col2, col3 = st.columns([1, 1, 2])
        ct = col1.selectbox("type", ["ALL", "ADDED", "REMOVED", "REVISED"], key="cct")
        kind = col2.selectbox("kind", ["ALL", "dn", "ln"], key="ckd")
        ports_df = _ports()
        port_options = ["ALL"] + ports_df["kode_pelabuhan"].tolist()
        p = col3.selectbox("port", port_options, key="cprt")
        df = q.cargo_changes(change_month, change_type=ct, port=p, kind=kind, limit=5000)
        st.caption(f"{len(df):,} rows (limit 5000)")
        st.dataframe(df, use_container_width=True, hide_index=True)


def page_ingestion():
    st.title("⚙️ Ingestion runs")
    runs = _ingestion_runs()
    if runs.empty:
        st.info("기록 없음")
        return
    st.dataframe(runs, use_container_width=True, hide_index=True)
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
    "📦 Cargo": page_cargo,
    "🔄 Changes": page_changes,
    "⚙️ Ingestion": page_ingestion,
}
PAGES[page]()
