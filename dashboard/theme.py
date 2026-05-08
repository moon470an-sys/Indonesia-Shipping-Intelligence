"""Design system for the Streamlit dashboard.

Single source of truth for typography, color, and Plotly template. Importing
this module registers the "sti" Plotly template and exposes :func:`apply` to
inject the matching CSS into the Streamlit page. Call :func:`apply` once near
the top of ``app.py``; everything else flows from the constants below.
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---- Typography ---------------------------------------------------------
FONT_STACK = (
    '"Pretendard Variable", "Pretendard", "Noto Sans KR", '
    '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif'
)

# ---- Semantic palette ---------------------------------------------------
# Color-blind aware (Okabe-Ito inspired) primary colorway. Used when a chart
# does not pass an explicit color map.
COLORWAY = [
    "#0ea5e9",  # sky        — neutral / default series
    "#f59e0b",  # amber      — secondary / LPG
    "#16a34a",  # green      — positive / new / heavy-util
    "#dc2626",  # red        — negative / idle / risk
    "#7c3aed",  # violet     — chemical
    "#0891b2",  # cyan       — LNG
    "#ea580c",  # orange
    "#1e40af",  # deep blue  — product
    "#be123c",  # rose
    "#6b7280",  # gray       — UNKNOWN / fallback
]

# Status colors used across status chips and conditional formatting.
SEMANTIC = {
    "positive":  "#16a34a",
    "warning":   "#f59e0b",
    "negative":  "#dc2626",
    "neutral":   "#475569",
    "muted":     "#94a3b8",
    "info":      "#0ea5e9",
    "accent":    "#7c3aed",
}

# Text color hierarchy.
INK = {
    "title":    "#0f172a",
    "body":     "#1f2937",
    "muted":    "#475569",
    "subtle":   "#64748b",
    "border":   "#e2e8f0",
    "grid":     "#eef2f7",
    "panel":    "#f8fafc",
}

# Single-hue continuous scales — replaces ad-hoc `Blues`/`Greens` calls. The
# light end is near-white so axis labels stay readable. Use these via
# ``color_continuous_scale=theme.SCALES["blue"]``.
SCALES = {
    "blue":   ["#eff6ff", "#bfdbfe", "#60a5fa", "#1e40af"],
    "green":  ["#ecfdf5", "#a7f3d0", "#34d399", "#047857"],
    "amber":  ["#fff7ed", "#fed7aa", "#f59e0b", "#b45309"],
    "red":    ["#fef2f2", "#fecaca", "#f87171", "#b91c1c"],
    "teal":   ["#f0fdfa", "#99f6e4", "#2dd4bf", "#0f766e"],
    "violet": ["#f5f3ff", "#ddd6fe", "#a78bfa", "#5b21b6"],
    # Diverging — for YoY / delta / signed metrics.
    "diverging":   ["#b91c1c", "#fef2f2", "#f8fafc", "#ecfdf5", "#047857"],
    # Reversed (red = good — e.g. low utilization is bad → high red).
    "diverging_r": ["#047857", "#ecfdf5", "#f8fafc", "#fef2f2", "#b91c1c"],
}

# Standard chart heights — pick one of these instead of arbitrary numbers.
HEIGHT = {
    "spark":  140,
    "small":  260,
    "med":    340,
    "large":  440,
    "tall":   540,
}


def _build_template() -> go.layout.Template:
    """Plotly layout template — Pretendard, soft grids, tight margins."""
    axis = dict(
        gridcolor=INK["grid"],
        linecolor=INK["border"],
        zerolinecolor=INK["border"],
        ticks="outside",
        tickcolor=INK["border"],
        tickfont=dict(family=FONT_STACK, size=11, color=INK["muted"]),
        title=dict(font=dict(family=FONT_STACK, size=12, color=INK["body"])),
        automargin=True,
    )
    return go.layout.Template(layout=dict(
        font=dict(family=FONT_STACK, size=12, color=INK["body"]),
        title=dict(font=dict(family=FONT_STACK, size=14,
                             color=INK["title"]), x=0.0, xanchor="left"),
        paper_bgcolor="white",
        plot_bgcolor="white",
        colorway=COLORWAY,
        xaxis=axis, yaxis=axis,
        legend=dict(font=dict(family=FONT_STACK, size=11, color=INK["body"]),
                    bgcolor="rgba(255,255,255,0.6)",
                    bordercolor=INK["border"], borderwidth=0),
        margin=dict(t=36, l=12, r=12, b=12),
        hoverlabel=dict(font=dict(family=FONT_STACK, size=12),
                        bgcolor="white", bordercolor=INK["border"]),
        separators=", ",
    ))


pio.templates["sti"] = _build_template()
pio.templates.default = "plotly_white+sti"


# ---- CSS ---------------------------------------------------------------
_CSS = f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.css');

html, body, [class*="css"], .stApp, .stMarkdown, .stMetric,
.stDataFrame, .stTable, .stTabs, .stRadio, .stSelectbox, .stTextInput,
.stExpander, .stButton, .stDownloadButton, .stSlider, .stMultiSelect {{
  font-family: {FONT_STACK} !important;
  font-feature-settings: 'tnum', 'ss01', 'ss02';
}}

/* Page width + padding — tighter on top so KPIs are above the fold. */
.main .block-container {{
  padding-top: 1.4rem; padding-bottom: 2.2rem; max-width: 1440px;
}}

/* Heading hierarchy — distinct from Streamlit defaults. */
h1, h1 span {{ font-size: 1.75rem !important; font-weight: 700;
              letter-spacing: -0.02em; color: {INK["title"]}; }}
h2, h2 span {{ font-size: 1.35rem !important; font-weight: 700;
              letter-spacing: -0.01em; color: {INK["title"]};
              margin-top: 1.1rem !important; }}
h3, h3 span {{ font-size: 1.10rem !important; font-weight: 600;
              color: {INK["title"]}; margin-top: 0.9rem !important; }}
h4, h4 span, h5, h5 span {{ font-size: 0.96rem !important; font-weight: 600;
              color: {INK["body"]}; margin-top: 0.8rem !important;
              margin-bottom: 0.3rem !important; }}

/* KPI metric tiles — bigger numbers, tabular nums, soft card. */
[data-testid="stMetric"] {{
  background: {INK["panel"]};
  border: 1px solid {INK["border"]};
  border-radius: 10px;
  padding: 0.6rem 0.85rem;
}}
[data-testid="stMetricValue"] {{
  font-size: 1.55rem !important; font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: {INK["title"]};
}}
[data-testid="stMetricLabel"] {{
  font-size: 0.78rem !important; color: {INK["muted"]};
  font-weight: 500; letter-spacing: 0.01em;
}}
[data-testid="stMetricDelta"] {{
  font-size: 0.82rem !important; font-variant-numeric: tabular-nums;
  font-weight: 600;
}}

/* DataFrames — tabular nums, smaller font, less heavy header. */
[data-testid="stDataFrame"] * {{ font-variant-numeric: tabular-nums; }}
[data-testid="stDataFrame"] {{ font-size: 0.85rem; }}

/* Captions softer + smaller. */
[data-testid="stCaptionContainer"], .stCaption, small {{
  color: {INK["subtle"]}; font-size: 0.78rem;
}}

/* Sidebar — light panel, tighter radio. */
section[data-testid="stSidebar"] {{ background: {INK["panel"]}; }}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {{
  font-size: 1rem !important; margin-top: 0.5rem !important;
}}
section[data-testid="stSidebar"] .stRadio label {{
  font-size: 0.92rem; padding: 0.18rem 0;
}}

/* Tabs — chip-style. */
.stTabs [data-baseweb="tab-list"] {{ gap: 0.25rem; border-bottom: 1px solid {INK["border"]}; }}
.stTabs [data-baseweb="tab"] {{
  padding: 0.5rem 0.9rem; font-size: 0.92rem; font-weight: 500;
  color: {INK["muted"]};
}}
.stTabs [aria-selected="true"] {{
  color: {INK["title"]} !important;
  background: white;
  border-bottom: 2px solid {SEMANTIC["info"]} !important;
  font-weight: 600;
}}

/* Expander — soft border, bolder header. */
.streamlit-expanderHeader, [data-testid="stExpander"] summary {{
  font-weight: 600; font-size: 0.95rem; color: {INK["body"]};
}}
[data-testid="stExpander"] {{ border-color: {INK["border"]} !important; }}

/* Buttons — flatter, consistent radius. */
.stButton button, .stDownloadButton button {{
  border-radius: 8px; font-weight: 500; font-size: 0.88rem;
  border: 1px solid {INK["border"]};
}}
.stButton button:hover, .stDownloadButton button:hover {{
  border-color: {SEMANTIC["info"]};
}}

/* Section divider softer. */
hr {{ border-color: {INK["border"]} !important; margin: 1rem 0 !important; }}

/* Code blocks — share-URL display. */
pre, code {{
  font-family: "JetBrains Mono", "SF Mono", "Cascadia Mono", Consolas,
                "Roboto Mono", monospace !important;
  font-size: 0.82rem;
}}

/* Plotly chart container — remove tiny spurious gap. */
[data-testid="stPlotlyChart"] {{ margin-top: 0.1rem; }}

/* Hero KPI strip: when a row of metrics follows a .hero-strip marker,
   give it a subtle gradient background and accent border so it reads as
   the page's primary signal block. */
.hero-strip {{
  background: linear-gradient(135deg, #f1f5f9 0%, #ffffff 100%);
  border-left: 4px solid {SEMANTIC["info"]};
  padding: 0.65rem 0.9rem 0.45rem;
  border-radius: 0 8px 8px 0;
  margin-bottom: 0.4rem;
}}
.hero-strip h3 {{
  margin: 0 0 0.15rem !important;
  color: {INK["title"]};
  font-size: 1.05rem !important; font-weight: 700;
  letter-spacing: -0.01em;
}}
.hero-strip p {{
  margin: 0; color: {INK["muted"]}; font-size: 0.82rem; line-height: 1.4;
}}
.hero-strip + div [data-testid="stMetric"] {{
  background: #fafbfc;
  border-color: {INK["border"]};
}}

/* Status pill — for inline labels like "Idle (12척)". */
.pill {{
  display: inline-block; padding: 0.12rem 0.55rem; margin-right: 0.3rem;
  font-size: 0.78rem; font-weight: 600; border-radius: 999px;
  font-variant-numeric: tabular-nums;
}}
.pill.positive {{ background: #ecfdf5; color: {SEMANTIC["positive"]}; }}
.pill.warning  {{ background: #fff7ed; color: {SEMANTIC["warning"]}; }}
.pill.negative {{ background: #fef2f2; color: {SEMANTIC["negative"]}; }}
.pill.info     {{ background: #eff6ff; color: {SEMANTIC["info"]}; }}
.pill.neutral  {{ background: #f1f5f9; color: {INK["muted"]}; }}
</style>
"""


def apply() -> None:
    """Inject the design CSS. Idempotent — safe to call inside Streamlit
    reruns. Plotly template is registered at module import; this only handles
    the page-level CSS."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ---- Plotly chart helpers ----------------------------------------------

def donut_center(fig: go.Figure, big: str, small: str | None = None) -> go.Figure:
    """Add a center label to a donut (px.pie with hole>0).

    ``big`` is the headline number (e.g. "1,234" or "$2.4B"); ``small`` is
    an optional sub-label (e.g. "총 화물량"). Mutates and returns the figure.
    """
    sub = (f"<br><span style='font-size:11px;color:{INK['muted']};"
           f"font-weight:500'>{small}</span>") if small else ""
    fig.add_annotation(
        text=f"<b>{big}</b>{sub}",
        x=0.5, y=0.5, showarrow=False,
        font=dict(family=FONT_STACK, size=20, color=INK["title"]),
        align="center",
    )
    return fig


def style_bar(fig: go.Figure, *, hide_colorbar: bool = True) -> go.Figure:
    """Common bar-chart polish: thin bar gap, optional hide redundant
    colorbar (when color = the same metric as bar length)."""
    fig.update_layout(bargap=0.18)
    if hide_colorbar:
        fig.update_layout(coloraxis_showscale=False)
    return fig


def hero_strip(title: str, subtitle: str = "") -> None:
    """Render a hero KPI section header — accent left border + soft
    gradient background. Use right before a row of ``st.columns`` containing
    the page's primary KPIs."""
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="hero-strip"><h3>{title}</h3>{sub}</div>',
        unsafe_allow_html=True,
    )


def pill(text: str, kind: str = "neutral") -> str:
    """Return an inline status pill HTML — use inside ``st.markdown(...,
    unsafe_allow_html=True)``. ``kind``: positive/warning/negative/info/neutral."""
    return f'<span class="pill {kind}">{text}</span>'


# ---- Table column_config helpers ---------------------------------------

def _column_format(name: str) -> str | None:
    """Heuristic: pick a NumberColumn format from a column name. Returns
    None for non-numeric / unrecognized columns (then default rendering)."""
    n = str(name).lower()
    # Percent / share / ratio
    if "_%" in n or n.endswith("%") or "share" in n or "pct" in n or "비율" in name:
        return "%.1f%%"
    # USD / dollar
    if "usd" in n or n.startswith("$") or "달러" in name:
        if "_m" in n or "_b" in n or "백만" in name:
            return "$%,.1f M"
        return "$%,.0f"
    # GT / 총_GT
    if n == "gt" or "_gt" in n or n.endswith("gt") or "총_gt" in n:
        return "%,.0f GT"
    # Tons (raw or magnitude)
    if n.endswith("_m") or n.endswith("_b") or "백만" in name:
        return "%,.2f"
    if n == "ton" or "톤" in name or "_ton" in n or n.endswith("ton"):
        return "%,.0f"
    # Counts
    if n in ("n", "count", "척수", "건수", "n_rows", "rows", "rows_total"):
        return "%,.0f"
    # Year — no thousand separator
    if "year" in n or n in ("tahun", "tahun_num", "건조연도", "snapshot_year"):
        return "%d"
    # Length / dimension (m)
    if n in ("loa", "panjang", "lebar", "dalam", "draft"):
        return "%.1f"
    # Generic numeric — fall through to None (Streamlit decides)
    return None


def df_config(df, *, overrides: dict | None = None) -> dict:
    """Build a ``column_config`` dict for ``st.dataframe(df, column_config=...)``.

    Uses :func:`_column_format` heuristics on each numeric column. Pass
    ``overrides`` for explicit per-column overrides — they win over heuristics.
    Non-numeric columns are left untouched."""
    import pandas as pd
    cfg: dict = {}
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        fmt = _column_format(col)
        if fmt:
            cfg[col] = st.column_config.NumberColumn(format=fmt)
    if overrides:
        cfg.update(overrides)
    return cfg


def dataframe(df, *, key: str | None = None, height: int | None = None,
              overrides: dict | None = None) -> None:
    """``st.dataframe`` wrapper that auto-applies :func:`df_config`.

    Drop-in replacement for ``st.dataframe(df, width="stretch", hide_index=True)``
    that gives every numeric column right-aligned, comma-separated formatting.
    Use ``overrides`` to set explicit ``st.column_config.*`` entries for
    columns that need progress bars, links, or unusual units."""
    st.dataframe(
        df, width="stretch", hide_index=True, height=height, key=key,
        column_config=df_config(df, overrides=overrides),
    )
