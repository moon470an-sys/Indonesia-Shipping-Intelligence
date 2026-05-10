// Indonesia Shipping Intelligence — static dashboard
// Loads precomputed JSON in docs/data/, renders Plotly charts, supports
// client-side search/filter/sort. No server side.

const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString());
const fmt1 = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 }));
const fmt0 = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }));

// PR-9: Unified scaled-unit formatters. Picks B / M / K / raw based on
// magnitude so labels stay readable across 5 orders of magnitude.
//   fmtTon(3_094_000_000) -> "3.09B"   (with optional unit suffix)
//   fmtTon(2_415, 0)      -> "2,415"
//   fmtCount(2_415)       -> "2,415"
//   fmtPct(8.94)          -> "+8.9%"   sign + 1 decimal
function fmtTon(v, opts = {}) {
  if (v == null) return "—";
  const n = Number(v);
  if (!isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(opts.b ?? 2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(opts.m ?? 1)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(opts.k ?? 1)}K`;
  return n.toLocaleString(undefined, { maximumFractionDigits: opts.r ?? 0 });
}
const fmtCount = (v) => v == null ? "—" : Number(v).toLocaleString();

// PR-17: tiny inline SVG sparkline for card trends. Returns a string.
// values: array of numbers; opts: { width, height, color, fillOpacity }
function sparkline(values, opts = {}) {
  const width = opts.width ?? 90;
  const height = opts.height ?? 24;
  const color = opts.color ?? "#1A3A6B";
  const fillO = opts.fillOpacity ?? 0.15;
  if (!values || values.length < 2) {
    return `<svg width="${width}" height="${height}" aria-hidden="true"></svg>`;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = (max - min) || 1;
  const stepX = width / (values.length - 1);
  // Pad y so the line never sits flush against the edges.
  const pad = 2;
  const innerH = height - pad * 2;
  const pts = values.map((v, i) => [i * stepX, pad + innerH - ((v - min) / span) * innerH]);
  const linePath = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(2)} ${p[1].toFixed(2)}`).join(" ");
  const fillPath = `${linePath} L${pts[pts.length - 1][0].toFixed(2)} ${height} L${pts[0][0].toFixed(2)} ${height} Z`;
  const lastX = pts[pts.length - 1][0].toFixed(2);
  const lastY = pts[pts.length - 1][1].toFixed(2);
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" aria-hidden="true">
    <path d="${fillPath}" fill="${color}" fill-opacity="${fillO}" />
    <path d="${linePath}" fill="none" stroke="${color}" stroke-width="1.4" stroke-linejoin="round" />
    <circle cx="${lastX}" cy="${lastY}" r="2" fill="${color}" />
  </svg>`;
}

// PR-12: render an IDX-listed ticker as a small chip link to the
// IDX listed-companies search page. Plain text fallback when ticker is null.
function idxLink(ticker, opts = {}) {
  if (!ticker) return "—";
  const url = `https://www.idx.co.id/en/listed-companies/company-profiles?keyword=${encodeURIComponent(ticker)}`;
  const cls = opts.chip
    ? "inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-blue-100 text-blue-800 hover:bg-blue-200"
    : "text-blue-600 hover:underline font-mono";
  return `<a href="${url}" target="_blank" rel="noopener" class="${cls}" title="IDX 공시 검색: ${ticker}">${ticker}</a>`;
}
function fmtPct(v, opts = {}) {
  if (v == null) return "—";
  const n = Number(v);
  if (!isFinite(n)) return "—";
  const sign = (opts.sign && n > 0) ? "+" : "";
  return `${sign}${n.toFixed(opts.d ?? 1)}%`;
}

const state = {
  meta: null,
  financials: null,
  loaded: new Set(),
};

async function loadJson(name) {
  const r = await fetch(`./data/${name}`);
  if (!r.ok) throw new Error(`fetch ${name} failed ${r.status}`);
  return await r.json();
}

// ---------- PR-B: derived/* loader + source label + global footer ----------
async function loadDerived(name) {
  const r = await fetch(`./derived/${name}`);
  if (!r.ok) throw new Error(`fetch derived/${name} failed ${r.status}`);
  return await r.json();
}

// addSourceLabel(elOrId, source): append a small "Source: ..." caption to a
// chart/table container. Used by PR-C/D/E and the auto-scanner below.
function addSourceLabel(elOrId, source) {
  const el = typeof elOrId === "string" ? document.getElementById(elOrId) : elOrId;
  if (!el || !source) return;
  if (el.querySelector(":scope > .source-label")) return;
  const tag = document.createElement("small");
  tag.className = "source-label";
  tag.textContent = `Source: ${source}`;
  el.appendChild(tag);
}

// Walk every container with [data-source] and inject the label once.
// Containers in HTML annotate themselves with data-source="..."; this
// function is called after each tab render (and once at boot).
function setupSourceLabels(root = document) {
  root.querySelectorAll("[data-source]").forEach(el => {
    addSourceLabel(el, el.getAttribute("data-source"));
  });
}

// Read derived/meta.json and populate both:
//   - the global disclaimer footer (full freshness line)
//   - the header pill (compact "LK3 YYYY-MM" badge)
// Degrades silently if the derived/ payload is missing.
async function loadGlobalFooter() {
  const footerEl = document.getElementById("footer-freshness");
  const headerEl = document.getElementById("header-freshness-text");
  try {
    const m = await loadDerived("meta.json");
    const lk3 = m.latest_lk3_month || "—";
    const vsl = m.latest_vessel_snapshot_month || "—";
    const built = (m.build_at || "").replace("T", " ").replace(/Z$/, " UTC");
    if (footerEl) {
      footerEl.textContent =
        `LK3 latest: ${lk3} · vessel snapshot: ${vsl} · build: ${built}`;
    }
    if (headerEl) headerEl.textContent = `LK3 ${lk3}`;
  } catch (e) {
    if (footerEl) footerEl.textContent = "Freshness data unavailable";
    if (headerEl) headerEl.textContent = "freshness —";
  }
}

// ---------- PR-6: glossary tooltip system ----------
// Map of glossary terms -> definitions. Surfaced as ⓘ badges next to
// the term wherever it appears in card labels, chart titles, etc.
// Replaces the deleted About tab's static glossary.
const GLOSSARY = {
  "Bongkar": "Bongkar (B / dn) — 양하 (discharge): 항구 도착 시 내려진 화물.",
  "Muat":    "Muat (M / ln) — 선적 (load): 항구 출발 시 적재된 화물.",
  "GT":      "Gross Tonnage — 선박 부피 측정 단위(IMO 기준). 적재 능력의 대략적 지표.",
  "DWT":     "Dead Weight Tonnage — 선박이 적재 가능한 화물·연료·청수 등의 총 중량(ton).",
  "HHI":     "Herfindahl-Hirschman Index — 운영사별 점유율 제곱합 × 10,000. 1,500 미만=분산 / 1,500-2,500=중간 / 2,500+=집중 (KPPU 기준).",
  "CAGR":    "Compound Annual Growth Rate — (last_12m / prev_12m)^(1/2) - 1. 두 윈도우가 모두 12개월일 때만 산출.",
  "subclass":"Tanker Subclass — Crude Oil / Product / Chemical / LPG / LNG / FAME-Vegetable Oil 6종. JenisDetailKet 라벨에 키워드 룰 적용.",
  "ln":      "ln — international (국제) 트래픽. LK3 신고 분류.",
  "dn":      "dn — domestic (국내) 트래픽. LK3 신고 분류.",
  "ROA":     "Return on Assets — 순이익 ÷ 총자산. 자산 효율성 지표.",
  "OD":      "Origin → Destination — 항로 페어. tanker_flow_map.lanes 기준 24M 누계.",
  "YoY":     "Year-over-Year — 직전 12개월 합계 대비 변동률.",
};

// PR-7: tiny helpers for consistent empty + error UI across widgets.
function emptyState(message, icon = "📭") {
  return `<div class="state-empty"><div class="state-icon">${icon}</div><div>${message}</div></div>`;
}
function errorState(message, icon = "⚠️") {
  return `<div class="state-error"><div class="state-icon">${icon}</div><div>${message}</div></div>`;
}

// Returns the markup for a small ⓘ badge. Used inline in template strings.
function infoBadge(term) {
  const def = GLOSSARY[term];
  if (!def) return "";
  // Escape double quotes for the data-info attribute.
  const safe = def.replace(/"/g, "&quot;");
  return `<span class="term-info" data-info="${safe}" tabindex="0" aria-label="${term} 정의">ⓘ</span>`;
}

// Sweep a container after render and append a ⓘ badge after the first
// occurrence of each glossary term inside heading / label elements.
// Idempotent: re-running on the same DOM is safe because we skip any
// element that already contains a .term-info child.
function decorateGlossary(root = document) {
  if (!root) return;
  const selectors = ["h2", "h3", "h4", "dt", ".kpi-label", ".gloss-target"];
  const allTerms = Object.keys(GLOSSARY);
  for (const sel of selectors) {
    root.querySelectorAll(sel).forEach(el => {
      if (el.querySelector(":scope > .term-info") || el.dataset.glossDone === "1") return;
      let html = el.innerHTML;
      let touched = false;
      for (const term of allTerms) {
        // Match on a word-ish boundary that works for Korean+ASCII mixed strings.
        // Avoid mid-word matches like "GTSI" containing "GT".
        const re = new RegExp(`(^|[\\s\\(\\)\\/·\\.,])(${term})(?=[\\s\\(\\)\\/·\\.,:]|$)`);
        if (re.test(html)) {
          html = html.replace(re, (_m, pre, t) => `${pre}${t}${infoBadge(t)}`);
          touched = true;
        }
      }
      if (touched) {
        el.innerHTML = html;
        el.dataset.glossDone = "1";
      }
    });
  }
}

// ---------- KPIs ----------
function kpiCard(label, value, sub) {
  const div = document.createElement("div");
  div.className = "kpi-card";
  div.innerHTML = `<div class="kpi-label">${label}</div>
    <div class="kpi-value">${value}</div>
    ${sub ? `<div class="kpi-sub">${sub}</div>` : ""}`;
  return div;
}

function renderKpis(elId, items) {
  const el = document.getElementById(elId);
  el.innerHTML = "";
  for (const it of items) el.appendChild(kpiCard(it.label, it.value, it.sub));
}

// ---------- Overview ----------
function pctSign(p) {
  if (p == null) return "—";
  const s = p > 0 ? "+" : "";
  return `${s}${p.toFixed(1)}%`;
}

// ---------- PR-C: Market Overview (derived/subclass_facts + owner_profile) ----------
const SUBCLASS_PALETTE = {
  "Crude Oil": "#92400e",
  "Product": "#0284c7",
  "Chemical": "#059669",
  "LPG": "#d97706",
  "LNG": "#7c3aed",
  "FAME / Vegetable Oil": "#65a30d",
  "UNKNOWN": "#94a3b8",
};

// ---------- PR-D: Tanker Sector ----------
const TANKER_SUBCLASS_FILTER_OPTIONS = [
  { key: "ALL",                   label: "ALL" },
  { key: "Crude Oil",             label: "Crude" },
  { key: "Product",               label: "Product" },
  { key: "Chemical",              label: "Chemical" },
  { key: "LPG",                   label: "LPG" },
  { key: "LNG",                   label: "LNG" },
  { key: "FAME / Vegetable Oil",  label: "FAME" },
];

// Map a route's bucket array to a coarse subclass for filter matching.
// Bucket labels in tanker_flow_map.lanes mix English (Crude/LPG/LNG/FAME/Naphtha)
// with Korean ("BBM-가솔린", "BBM-디젤", "기타", "기타 식용유"). This table
// is best-effort — the goal is filter responsiveness, not perfect taxonomy.
const BUCKET_TO_SUBCLASS = {
  "Crude":          "Crude Oil",
  "LPG":            "LPG",
  "LNG":            "LNG",
  "FAME":           "FAME / Vegetable Oil",
  "기타 식용유":    "FAME / Vegetable Oil",
  "Chemical":       "Chemical",
  "Naphtha":        "Product",
};

function bucketsToSubclasses(buckets) {
  const out = new Set();
  for (const b of (buckets || [])) {
    if (BUCKET_TO_SUBCLASS[b]) out.add(BUCKET_TO_SUBCLASS[b]);
    else if (typeof b === "string" && b.startsWith("BBM")) out.add("Product");
  }
  return out;
}

// Renewal v2 state — selected subclass card filters all 5 widgets in this tab.
const tsState = {
  filter: "ALL",
  subclassFacts: null,
  tankerSubclass: null,
  tankerTop: null,
  monthlyMode: "abs",   // abs | yoy
};

async function renderTankerSector() {
  const cardHost = document.getElementById("ts-cards");
  const regHost = document.getElementById("ts-regulatory");
  if (!cardHost) return;

  try {
    [tsState.subclassFacts, tsState.tankerSubclass, tsState.tankerTop] = await Promise.all([
      loadDerived("subclass_facts.json"),
      loadDerived("tanker_subclass.json"),
      loadDerived("tanker_top.json"),
    ]);
  } catch (e) {
    cardHost.innerHTML = `<div class="col-span-full">${errorState(
      `Tanker Sector derived JSON 로드 실패: ${e.message}. <code>python scripts/build_derived.py</code>를 실행하세요.`
    )}</div>`;
    return;
  }

  // Regulatory notes (one-time fetch + inject)
  if (regHost) {
    try {
      const r = await fetch("./derived/regulatory_notes.html");
      regHost.innerHTML = r.ok
        ? await r.text()
        : `<p class="text-xs text-slate-500">regulatory_notes.html 로드 실패 (${r.status}).</p>`;
    } catch (e) {
      regHost.innerHTML = `<p class="text-xs text-slate-500">regulatory_notes 로드 오류: ${e.message}</p>`;
    }
  }

  // Monthly toggle wiring (one-time)
  const toggleHost = document.getElementById("ts-monthly-mode");
  if (toggleHost && !toggleHost.dataset.wired) {
    toggleHost.dataset.wired = "1";
    toggleHost.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      tsState.monthlyMode = btn.dataset.key;
      toggleHost.querySelectorAll("button").forEach(b => {
        if (b.dataset.key === tsState.monthlyMode) {
          b.classList.add("bg-slate-800", "text-white");
          b.classList.remove("bg-white", "hover:bg-slate-100");
        } else {
          b.classList.remove("bg-slate-800", "text-white");
          b.classList.add("bg-white", "hover:bg-slate-100");
        }
      });
      drawTankerMonthly();
    });
  }

  drawTankerCards();
  drawTankerScatter();
  drawTankerMonthly();
  drawTankerCommodityBars();
  drawTankerOperatorBars();
  drawTankerOperatorDonut();
}

function drawTankerCards() {
  const host = document.getElementById("ts-cards");
  const activeEl = document.getElementById("ts-active-filter");
  if (!host) return;
  const cards = tsState.tankerSubclass?.cards || [];
  // Build sparkline series lookup from monthly data
  const monthlyBySub = {};
  for (const s of (tsState.tankerSubclass?.monthly?.series || [])) {
    monthlyBySub[s.subclass] = s.ton_by_period || [];
  }
  host.innerHTML = cards.map(c => {
    const color = SUBCLASS_PALETTE[c.subclass] || "#64748b";
    const tonStr = fmtTon(c.ton_last_12m);
    const yoy = c.yoy_pct;
    const trend = yoy == null
      ? `<span class="text-slate-400 text-sm">YoY —</span>`
      : `<span class="${yoy >= 0 ? "kpi-trend-up" : "kpi-trend-down"} text-base font-semibold">${yoy >= 0 ? "↑" : "↓"} ${Math.abs(yoy).toFixed(1)}%</span>`;
    const ageTxt = c.avg_age_gt_weighted == null ? "—" : `${c.avg_age_gt_weighted.toFixed(1)}년`;
    const hhiTxt = c.hhi == null ? "—" : Math.round(c.hhi).toLocaleString();
    const isActive = tsState.filter !== "ALL" && tsState.filter === c.subclass;
    const ringCls = isActive ? "ring-2 ring-slate-800" : "";
    // PR-10: top route + top operator surfaces
    const routeStr = c.top_route
      ? `${c.top_route.origin} → ${c.top_route.destination}`
      : '<span class="text-slate-400">—</span>';
    const routeMeta = c.top_route
      ? `<span class="text-slate-400 text-[10px]">${fmtTon(c.top_route.ton)} · ${c.top_route.vessels}척</span>`
      : "";
    const opStr = c.top_operator
      ? `${c.top_operator.owner.length > 24 ? c.top_operator.owner.slice(0, 22) + "…" : c.top_operator.owner}`
      : '<span class="text-slate-400">—</span>';
    const opMeta = c.top_operator
      ? `<span class="text-slate-400 text-[10px]">${c.top_operator.count_in_subclass}척</span>`
      : "";
    return `<div class="card-interactive bg-white rounded-xl shadow p-4 border-l-4 cursor-pointer ${ringCls}"
                 style="border-color:${color}" data-subclass="${c.subclass}"
                 role="button" tabindex="0" aria-pressed="${isActive}"
                 aria-label="${c.subclass} 필터 토글">
      <div class="flex items-baseline justify-between mb-2">
        <h4 class="font-semibold text-slate-700">${c.subclass}</h4>
        <span class="text-[10.5px] text-slate-400">${(c.vessel_count || 0).toLocaleString()}척</span>
      </div>
      <div class="flex items-end justify-between gap-2 mb-2">
        <div class="flex items-baseline gap-2">
          <span class="text-2xl font-bold text-slate-900">${tonStr}</span>
          <span class="text-xs text-slate-500">tons (12M)</span>
        </div>
        <div title="24M monthly ton trend">${sparkline(monthlyBySub[c.subclass] || [], { color, width: 80, height: 24 })}</div>
      </div>
      <div class="mb-3">${trend}</div>
      <dl class="text-xs space-y-1.5 text-slate-600 mb-3">
        <div class="flex justify-between"><dt>평균 선령 (GT 가중)</dt><dd class="font-mono">${ageTxt}</dd></div>
        <div class="flex justify-between"><dt>운영사 수</dt><dd class="font-mono">${c.operator_count ?? "—"}</dd></div>
        <div class="flex justify-between"><dt>HHI</dt><dd class="font-mono">${hhiTxt}</dd></div>
      </dl>
      <div class="border-t border-slate-100 pt-2.5 space-y-1.5 text-[11px] text-slate-600">
        <div>
          <div class="text-slate-400 text-[10px] uppercase tracking-wide mb-0.5">최대 항로</div>
          <div class="flex items-baseline justify-between gap-2">
            <span class="truncate">${routeStr}</span>${routeMeta}
          </div>
        </div>
        <div>
          <div class="text-slate-400 text-[10px] uppercase tracking-wide mb-0.5">최대 운영사</div>
          <div class="flex items-baseline justify-between gap-2">
            <span class="truncate">${opStr}</span>${opMeta}
          </div>
        </div>
      </div>
    </div>`;
  }).join("");

  // Click / Enter / Space → toggle filter
  const applyFilter = (s) => {
    tsState.filter = (tsState.filter === s) ? "ALL" : s;
    drawTankerCards();
    drawTankerScatter();
    drawTankerMonthly();
    drawTankerCommodityBars();
  };
  host.querySelectorAll("[data-subclass]").forEach(el => {
    el.addEventListener("click", () => applyFilter(el.dataset.subclass));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        applyFilter(el.dataset.subclass);
      }
    });
  });

  // PR-8: prominent active-filter pill with explicit Clear button.
  if (activeEl) {
    if (tsState.filter === "ALL") {
      activeEl.textContent = "전체 subclass — 카드를 클릭하여 필터링";
      activeEl.className = "text-xs text-slate-500";
    } else {
      activeEl.innerHTML = `<span class="active-filter-pill">필터: ${tsState.filter}<button type="button" id="ts-filter-clear" aria-label="필터 해제">×</button></span>`;
      activeEl.className = "";
      const clr = document.getElementById("ts-filter-clear");
      if (clr) clr.addEventListener("click", () => applyFilter(tsState.filter));
    }
  }
}

function drawTankerScatter() {
  const subs = (tsState.subclassFacts?.subclasses || []).filter(r => r.subclass !== "UNKNOWN");
  if (!subs.length) return;
  const sizeMax = Math.max(...subs.map(r => r.ton_last_12m || 0), 1);
  const filter = tsState.filter;
  const opacities = subs.map(r => (filter === "ALL" || filter === r.subclass) ? 0.85 : 0.2);
  const trace = {
    x: subs.map(r => r.cagr_24m_pct ?? 0),
    y: subs.map(r => r.avg_age_gt_weighted ?? 0),
    text: subs.map(r => r.subclass),
    mode: "markers+text",
    type: "scatter",
    textposition: "top center",
    textfont: { size: 11 },
    marker: {
      size: subs.map(r => Math.max(14, 80 * (r.ton_last_12m || 0) / sizeMax)),
      color: subs.map(r => SUBCLASS_PALETTE[r.subclass] || "#64748b"),
      line: { color: "#1e293b", width: 1 },
      opacity: opacities,
    },
    hovertemplate:
      "<b>%{text}</b><br>" +
      "CAGR (24M): %{x:.2f}%<br>" +
      "Avg age: %{y:.1f} yr<br>" +
      "12M ton: %{customdata:,.0f}<extra></extra>",
    customdata: subs.map(r => r.ton_last_12m),
  };
  const cagrAvail = subs.some(r => r.cagr_24m_pct != null);
  Plotly.newPlot("ts-scatter", [trace], {
    margin: { t: 10, l: 50, r: 20, b: 50 },
    xaxis: {
      title: cagrAvail ? "24M CAGR (%)" : "24M CAGR (insufficient data — needs 2 full years)",
      zeroline: true,
      zerolinecolor: "#cbd5e1",
    },
    yaxis: { title: "GT 가중 평균 선령 (years)" },
    showlegend: false,
  }, { displayModeBar: false, responsive: true });
}

function drawTankerMonthly() {
  const data = tsState.tankerSubclass?.monthly;
  if (!data) return;
  const periods = data.periods || [];
  const filter = tsState.filter;
  const traces = (data.series || []).map(s => {
    let y = s.ton_by_period.slice();
    if (tsState.monthlyMode === "yoy") {
      y = y.map((v, i) => (i < 12 || !y[i - 12]) ? null : ((v - y[i - 12]) / y[i - 12]) * 100);
    }
    const dim = (filter !== "ALL" && filter !== s.subclass);
    return {
      x: periods,
      y,
      name: s.subclass,
      type: "scatter",
      mode: "lines",
      stackgroup: tsState.monthlyMode === "abs" ? "one" : null,
      line: { color: SUBCLASS_PALETTE[s.subclass] || "#64748b", width: tsState.monthlyMode === "abs" ? 0.5 : 2 },
      fillcolor: SUBCLASS_PALETTE[s.subclass] || "#64748b",
      opacity: dim ? 0.25 : 1,
      hovertemplate: tsState.monthlyMode === "abs"
        ? `<b>%{x}</b><br>${s.subclass}: %{y:,.0f} tons<extra></extra>`
        : `<b>%{x}</b><br>${s.subclass}: %{y:.1f}%<extra></extra>`,
    };
  });
  Plotly.newPlot("ts-monthly", traces, {
    margin: { t: 10, l: 60, r: 20, b: 50 },
    xaxis: { tickangle: -40 },
    yaxis: {
      title: tsState.monthlyMode === "abs" ? "ton" : "YoY %",
      zeroline: tsState.monthlyMode === "yoy",
    },
    legend: { orientation: "h", y: -0.2 },
    hovermode: "x unified",
  }, { displayModeBar: false, responsive: true });
}

function drawTankerCommodityBars() {
  const list = (tsState.tankerTop?.top_commodities || []).slice();
  if (!list.length) return;
  // Reverse so largest sits at top in horizontal bar
  list.reverse();
  const filter = tsState.filter;
  const trace = {
    x: list.map(c => c.ton_total),
    y: list.map(c => c.name),
    type: "bar",
    orientation: "h",
    marker: {
      color: list.map(c => SUBCLASS_PALETTE[c.subclass] || "#64748b"),
      opacity: list.map(c => (filter === "ALL" || filter === c.subclass) ? 0.9 : 0.25),
    },
    hovertemplate: "<b>%{y}</b><br>%{x:,.0f} tons<extra></extra>",
    text: list.map(c => fmtTon(c.ton_total)),
    textposition: "outside",
    cliponaxis: false,
  };
  Plotly.newPlot("ts-commodity-bars", [trace], {
    margin: { t: 10, l: 130, r: 60, b: 40 },
    xaxis: { title: "ton (12M)" },
  }, { displayModeBar: false, responsive: true });
}

function drawTankerOperatorBars() {
  const list = (tsState.tankerTop?.top_operators || []).slice();
  if (!list.length) return;
  list.reverse();   // bar chart paints bottom-up
  const trace = {
    x: list.map(o => o.sum_gt),
    y: list.map(o => o.owner.length > 28 ? o.owner.slice(0, 26) + "…" : o.owner),
    type: "bar",
    orientation: "h",
    marker: { color: list.map(o => o.ticker ? "#1A3A6B" : "#94a3b8") },
    customdata: list.map(o => [o.tankers, o.ticker || "private", JSON.stringify(o.subclass_mix || {})]),
    hovertemplate:
      "<b>%{y}</b><br>" +
      "Sum GT: %{x:,.0f}<br>" +
      "Tankers: %{customdata[0]}<br>" +
      "Listed: %{customdata[1]}<extra></extra>",
    text: list.map(o => o.ticker ? o.ticker : ""),
    textposition: "outside",
    textfont: { size: 10, color: "#1A3A6B" },
    cliponaxis: false,
  };
  Plotly.newPlot("ts-operator-bars", [trace], {
    margin: { t: 10, l: 220, r: 60, b: 40 },
    xaxis: { title: "Sum GT" },
  }, { displayModeBar: false, responsive: true });

  // PR-12: click on a listed-operator bar opens the IDX search page
  // for that ticker. Non-listed operators are no-op.
  const opBarsEl = document.getElementById("ts-operator-bars");
  if (opBarsEl && opBarsEl.on) {
    opBarsEl.on("plotly_click", (ev) => {
      const cd = ev.points?.[0]?.customdata;
      if (!cd) return;
      const ticker = cd[1];
      if (!ticker || ticker === "private") return;
      const url = `https://www.idx.co.id/en/listed-companies/company-profiles?keyword=${encodeURIComponent(ticker)}`;
      window.open(url, "_blank", "noopener");
    });
    // visual hint: change cursor when hovering a listed-operator bar
    opBarsEl.on("plotly_hover", (ev) => {
      const cd = ev.points?.[0]?.customdata;
      const isListed = cd && cd[1] && cd[1] !== "private";
      opBarsEl.style.cursor = isListed ? "pointer" : "default";
    });
    opBarsEl.on("plotly_unhover", () => { opBarsEl.style.cursor = "default"; });
  }
}

function drawTankerOperatorDonut() {
  const top5gt = tsState.tankerTop?.operator_top5_gt || 0;
  const totalGt = tsState.tankerTop?.operator_total_gt || 0;
  const otherGt = Math.max(0, totalGt - top5gt);
  const trace = {
    values: [top5gt, otherGt],
    labels: ["Top 5", "그 외"],
    type: "pie",
    hole: 0.55,
    marker: { colors: ["#1A3A6B", "#cbd5e1"] },
    textinfo: "label+percent",
    hovertemplate: "<b>%{label}</b><br>%{value:,.0f} GT (%{percent})<extra></extra>",
  };
  Plotly.newPlot("ts-operator-donut", [trace], {
    margin: { t: 10, l: 10, r: 10, b: 30 },
    showlegend: false,
    annotations: [{
      text: `Total<br>${fmtTon(totalGt)} GT`,
      x: 0.5, y: 0.5, showarrow: false, font: { size: 12, color: "#475569" },
    }],
  }, { displayModeBar: false, responsive: true });
}

// ---------- Financials ----------
const fnState = { year: null, sortBy: "revenue", initialized: false };

function renderFinancials() {
  const f = state.financials;
  const container = document.getElementById("kpi-financials");
  if (!f || !f.companies || !f.companies.length) {
    container.innerHTML = `<div class="col-span-full text-center text-slate-400 py-12">
      재무 데이터를 로드하지 못했습니다 (companies_financials.json 미존재).
    </div>`;
    return;
  }

  // PR-7: fn-banner element removed; the global footer + Listed Operators
  // tab description already carry the IDX source attribution.

  // First-time setup: year dropdown + sortable column header bindings.
  if (!fnState.initialized) {
    fnState.initialized = true;
    fnState.sortDir = -1;  // default desc on first sort
    const years = Array.from(new Set(f.rows.map(r => r.year))).sort();
    const yrSel = document.getElementById("fn-year");
    yrSel.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join("");
    yrSel.value = years[years.length - 1];
    fnState.year = yrSel.value;
    yrSel.addEventListener("change", (e) => { fnState.year = e.target.value; renderFinancials(); });
    // PR-14: clickable / keyboard-activated column headers
    document.querySelectorAll("#fn-tbl th[data-sort]").forEach(th => {
      th.setAttribute("tabindex", "0");
      th.setAttribute("role", "columnheader");
      th.setAttribute("aria-sort", "none");
      const handler = () => {
        const key = th.dataset.sort;
        if (fnState.sortBy === key) {
          fnState.sortDir = -(fnState.sortDir);
        } else {
          fnState.sortBy = key;
          fnState.sortDir = th.dataset.numeric ? -1 : 1;  // numeric default desc, text default asc
        }
        renderFinancials();
      };
      th.addEventListener("click", handler);
      th.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handler(); }
      });
    });
  }

  const yr = fnState.year;
  const sortBy = fnState.sortBy;
  const sortDir = fnState.sortDir || -1;
  const yrRows = f.rows.filter(r => r.year === yr);

  // KPI strip — industry totals for the selected year
  const sumOf = (k) => yrRows.reduce((s, r) => s + (r[k] || 0), 0);
  const totRev = sumOf("revenue");
  const totNi = sumOf("net_income");
  const totFleetGt = sumOf("fleet_gt");
  const margin = totRev ? (totNi / totRev * 100) : null;
  // Renewal v2 §7.1: 4 KPI hero
  const avgDebt = yrRows.length
    ? yrRows.reduce((s, r) => s + (r.debt_to_assets || 0), 0) / yrRows.length
    : null;
  renderKpis("kpi-financials", [
    { label: `합산 매출 (${yr})`, value: fmt0(totRev), sub: "IDR billion" },
    { label: "평균 순이익률",
      value: margin == null ? "—" : `${margin.toFixed(1)}%`,
      sub: `${yrRows.length}개사 가중 평균` },
    { label: "평균 부채비율",
      value: avgDebt == null ? "—" : `${avgDebt.toFixed(1)}%`,
      sub: "Debt / Assets" },
    { label: "합산 선대 GT", value: fmt0(totFleetGt), sub: "kGT (1,000 GT)" },
  ]);

  // Renewal v2 §7.2: scatter — x=매출 log, y=순이익률, size=선대 GT
  Plotly.newPlot("chart-fn-scatter", [{
    x: yrRows.map(r => r.revenue),
    y: yrRows.map(r => r.net_margin),
    text: yrRows.map(r => r.ticker),
    mode: "markers+text",
    textposition: "top center",
    marker: {
      size: yrRows.map(r => Math.max(10, Math.sqrt((r.fleet_gt || 0) / 5))),
      color: "#1A3A6B",
      opacity: 0.75,
      line: { color: "#0f172a", width: 1 },
    },
    hovertemplate: "<b>%{text}</b><br>매출 %{x:,} bn IDR<br>순이익률 %{y:.1f}%<extra></extra>",
  }], {
    margin: { t: 10, l: 60, r: 10, b: 50 },
    xaxis: { title: "매출 (IDR bn, log)", type: "log", zeroline: false },
    yaxis: { title: "순이익률 (%)", zeroline: true, zerolinecolor: "#cbd5e1" },
  }, { displayModeBar: false, responsive: true });

  // Comparison table — PR-14: bidirectional sort with header indicators
  const yearTxt = document.getElementById("fn-table-year");
  if (yearTxt) yearTxt.textContent = `(${yr} 기준)`;
  // Resolve cell value: ticker / name come from the company catalog, others from rows
  const byTicker = {};
  for (const c of f.companies) byTicker[c.ticker] = c;
  const cellVal = (r, key) => {
    if (key === "ticker") return r.ticker || "";
    if (key === "name") return (byTicker[r.ticker] || {}).name_short || "";
    return r[key];
  };
  const sorted = yrRows.slice().sort((a, b) => {
    const x = cellVal(a, sortBy), y = cellVal(b, sortBy);
    if (x == null && y == null) return 0;
    if (x == null) return 1; if (y == null) return -1;
    if (typeof x === "string" || typeof y === "string") {
      return String(x).localeCompare(String(y)) * sortDir;
    }
    return (x > y ? 1 : (x < y ? -1 : 0)) * -sortDir;
  });
  // Update sort indicators on each header
  document.querySelectorAll("#fn-tbl th[data-sort]").forEach(th => {
    th.classList.remove("sort-asc", "sort-desc");
    th.setAttribute("aria-sort", "none");
    if (th.dataset.sort === sortBy) {
      const cls = sortDir === 1 ? "sort-asc" : "sort-desc";
      th.classList.add(cls);
      th.setAttribute("aria-sort", sortDir === 1 ? "ascending" : "descending");
    }
  });

  const num0 = (v) => v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  const pct1 = (v) => v == null ? "—" : `${Number(v).toFixed(1)}%`;
  document.querySelector("#fn-tbl tbody").innerHTML = sorted.map(r => {
    const c = byTicker[r.ticker] || {};
    return `<tr>
      <td class="px-2 py-1 font-mono">${idxLink(r.ticker)}</td>
      <td class="px-2 py-1">${c.name_short || ""}</td>
      <td class="px-2 py-1 text-right">${num0(r.revenue)}</td>
      <td class="px-2 py-1 text-right">${pct1(r.net_margin)}</td>
      <td class="px-2 py-1 text-right">${pct1(r.roa)}</td>
      <td class="px-2 py-1 text-right">${pct1(r.debt_to_assets)}</td>
      <td class="px-2 py-1 text-right">${num0(r.fleet_gt)}</td>
    </tr>`;
  }).join("");
}

// ---------- Tabs ----------
// PR-13: tab name -> document.title suffix
const TAB_TITLES = {
  "overview":      "Home",
  "tanker-sector": "Tanker Sector",
  "cargo-fleet":   "Cargo & Fleet",
  "financials":    "Listed Operators",
};

async function showTab(name) {
  document.querySelectorAll(".tab").forEach(t => {
    const isActive = t.dataset.tab === name;
    t.setAttribute("aria-selected", isActive ? "true" : "false");
    if (isActive) { t.classList.add("active"); t.classList.remove("hover:bg-slate-700"); }
    else { t.classList.remove("active"); t.classList.add("hover:bg-slate-700"); }
  });
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
  const panel = document.getElementById(`tab-${name}`);
  if (panel) panel.classList.remove("hidden");
  // PR-13: dynamic title so browser tabs / bookmarks reflect the active tab
  const tabLabel = TAB_TITLES[name] || "Home";
  document.title = `${tabLabel} · Indonesia Shipping Intelligence`;
  await ensureLoaded(name);
  // PR-B: re-scan source labels since lazy-loaded tabs may add new
  // [data-source] containers on activation.
  // PR-6: also decorate any glossary terms surfaced after the lazy load.
  if (panel) {
    setupSourceLabels(panel);
    decorateGlossary(panel);
  }
}

// PR-13: Arrow-key navigation across the nav tablist (WAI-ARIA pattern)
function bindTabKeyboardNav() {
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  tabs.forEach((tab, i) => {
    tab.addEventListener("keydown", (e) => {
      let next = null;
      if (e.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
      else if (e.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
      else if (e.key === "Home") next = tabs[0];
      else if (e.key === "End") next = tabs[tabs.length - 1];
      if (next) {
        e.preventDefault();
        next.focus();
        showTab(next.dataset.tab);
      }
    });
  });
}

async function ensureLoaded(tab) {
  try {
    if (tab === "tanker-sector" && !state.loaded.has("tanker-sector")) {
      await renderTankerSector();
      state.loaded.add("tanker-sector");
    }
    if (tab === "cargo-fleet" && !state.loaded.has("cargo-fleet")) {
      await renderCargoFleet();
      state.loaded.add("cargo-fleet");
    }
    if (tab === "financials" && !state.loaded.has("financials")) {
      if (!state.financials) {
        try { state.financials = await loadJson("companies_financials.json"); }
        catch (e) { state.financials = null; }
      }
      renderFinancials();
      state.loaded.add("financials");
    }
    // Home (overview) renders eagerly in boot(), no lazy load.
  } catch (e) {
    console.error(e);
  }
}

// ---------- Boot ----------
async function boot() {
  // Renewal v2: light-weight boot. Home, Cargo & Fleet, Tanker Sector and
  // Listed Operators all render lazily from docs/derived/* on demand.
  // legacy docs/data/{meta,overview,kpi_summary,...}.json reads removed.
  try { state.meta = await loadDerived("meta.json"); } catch (e) { state.meta = null; }
  await renderHome();
  document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));
  bindTabKeyboardNav();
  showTab("overview");
  loadGlobalFooter();
  setupSourceLabels();
  decorateGlossary(document);
}


// ---------- PR-2: Home animated flow map (d3 + topojson) ----------
// World atlas TopoJSON (countries-110m). Loaded once and cached.
const TOPO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";
const ID_INDONESIA = 360;  // ISO 3166-1 numeric

const homeState = {
  mapData: null,
  topology: null,
  filterCategory: "all",      // all | tanker | bulk (bulk shows note)
  filterPeriod: "24m",        // 24m | 12m (12m shows note)
  filterTraffic: "dn_ln",     // dn_ln | ln (ln shows note)
  highlightCategory: null,    // null | category-name (PR-11: legend click)
};

async function renderHome() {
  setupSourceLabels(document.getElementById("tab-overview"));

  // Parallel: KPI hero, timeseries, map data, world topology.
  let topo, kpis, ts;
  try {
    [kpis, ts, homeState.mapData, topo] = await Promise.all([
      loadDerived("home_kpi.json"),
      loadDerived("timeseries.json"),
      loadDerived("map_flow.json"),
      fetch(TOPO_URL).then(r => {
        if (!r.ok) throw new Error(`world-atlas ${r.status}`);
        return r.json();
      }),
    ]);
    homeState.topology = topo;
  } catch (e) {
    const status = document.getElementById("home-map-status");
    if (status) status.textContent = `Map data load failed: ${e.message}`;
    return;
  }

  renderHomeKpi(kpis);
  renderHomeTimeseries(ts);
  bindMapControls();
  drawHomeMap();
  fillSectorStrip(kpis?.sector_breakdown || []);
  fillForeignSidebar();
  fillMapInsights();
}

// PR-16: 5-row sector breakdown bars in the map sidebar.
// CSS-only horizontal bars sized by pct_ton — no Plotly overhead.
function fillSectorStrip(rows) {
  const host = document.getElementById("map-sector-strip");
  if (!host) return;
  if (!rows.length) {
    host.innerHTML = `<li class="text-slate-400 text-xs">데이터 없음</li>`;
    return;
  }
  const max = Math.max(...rows.map(r => r.pct_ton || 0), 1);
  host.innerHTML = rows.map(r => {
    const w = Math.max(2, (r.pct_ton / max) * 100);
    return `<li>
      <div class="flex items-baseline justify-between text-[11px] mb-0.5">
        <span class="text-slate-700 truncate" style="max-width:60%">${r.sector}</span>
        <span class="font-mono text-slate-500">${(r.pct_ton || 0).toFixed(1)}%</span>
      </div>
      <div class="h-1.5 bg-slate-200 rounded overflow-hidden">
        <div style="width:${w}%; background:${r.color}; height:100%"></div>
      </div>
    </li>`;
  }).join("");
}

// ---------- PR-3: Home KPI 4 (large numerics) ----------
function renderHomeKpi(payload) {
  const host = document.getElementById("home-kpi");
  if (!host || !payload) return;
  const trend = (yoy) => {
    if (yoy == null) return `<span class="text-slate-400 text-sm">YoY —</span>`;
    const cls = yoy >= 0 ? "kpi-trend-up" : "kpi-trend-down";
    const arrow = yoy >= 0 ? "↑" : "↓";
    return `<span class="${cls} text-sm font-semibold">${arrow} ${Math.abs(yoy).toFixed(1)}%</span>`;
  };
  const cards = payload.kpis.map(k => {
    if (k.id === "total_12m_ton") {
      return `<div class="kpi-card-large">
        <div class="kpi-label">12M 총 물동량</div>
        <div>
          <div class="kpi-value-large">${fmtTon(k.value_ton)}<span class="text-base text-slate-400 ml-1">tons</span></div>
          <div class="kpi-sub-large">${trend(k.yoy_pct)} <span class="text-slate-400">· ${k.window?.[0] || ""} → ${k.window?.[1] || ""}</span></div>
        </div>
      </div>`;
    }
    if (k.id === "tanker_12m_ton") {
      return `<div class="kpi-card-large">
        <div class="kpi-label">12M 탱커 물동량</div>
        <div>
          <div class="kpi-value-large">${fmtTon(k.value_ton)}<span class="text-base text-slate-400 ml-1">tons</span></div>
          <div class="kpi-sub-large">${trend(k.yoy_pct)} <span class="text-slate-400">· ${k.window?.[0] || ""} → ${k.window?.[1] || ""}</span></div>
        </div>
      </div>`;
    }
    if (k.id === "tanker_fleet") {
      const age = k.avg_age_gt_weighted == null ? "—" : `${k.avg_age_gt_weighted.toFixed(1)}년`;
      return `<div class="kpi-card-large">
        <div class="kpi-label">탱커 등록 척수</div>
        <div>
          <div class="kpi-value-large">${fmt(k.value_count || 0)}<span class="text-base text-slate-400 ml-1">척</span></div>
          <div class="kpi-sub-large"><span class="text-slate-600">평균 선령</span> ${age} <span class="text-slate-400">(GT 가중)</span></div>
        </div>
      </div>`;
    }
    if (k.id === "data_freshness") {
      const partial = k.partial_dropped ? "(partial month dropped)" : "";
      return `<div class="kpi-card-large">
        <div class="kpi-label">데이터 기준일</div>
        <div>
          <div class="kpi-value-large" style="font-size:clamp(22px,3vw,32px)">${k.value_text || "—"}</div>
          <div class="kpi-sub-large">vessel snapshot ${k.vessel_snapshot || "—"} <span class="text-slate-400">${partial}</span></div>
        </div>
      </div>`;
    }
    return "";
  }).join("");
  host.innerHTML = cards;
}

// ---------- PR-3: Home 24M sector stacked area ----------
const homeTsState = { mode: "abs", payload: null };
function renderHomeTimeseries(payload) {
  homeTsState.payload = payload;
  // Mode toggle wiring (one-time)
  const toggleHost = document.getElementById("home-ts-toggle");
  if (toggleHost && !toggleHost.dataset.wired) {
    toggleHost.innerHTML = `
      <button data-mode="abs" class="px-2 py-1 rounded border border-slate-200 bg-slate-800 text-white">절대값</button>
      <button data-mode="yoy" class="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-100">YoY %</button>`;
    toggleHost.dataset.wired = "1";
    toggleHost.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      homeTsState.mode = btn.dataset.mode;
      toggleHost.querySelectorAll("button").forEach(b => {
        if (b.dataset.mode === homeTsState.mode) {
          b.classList.add("bg-slate-800", "text-white");
          b.classList.remove("bg-white", "hover:bg-slate-100");
        } else {
          b.classList.remove("bg-slate-800", "text-white");
          b.classList.add("bg-white", "hover:bg-slate-100");
        }
      });
      drawHomeTimeseries();
    });
  }
  drawHomeTimeseries();
}

function drawHomeTimeseries() {
  const payload = homeTsState.payload;
  if (!payload) return;
  const periods = payload.periods || [];
  const traces = [];
  for (const s of (payload.series || [])) {
    let y = s.ton_by_period.slice();
    let name = s.sector;
    if (homeTsState.mode === "yoy") {
      // YoY for each period i = (y[i] - y[i-12]) / y[i-12] * 100
      y = y.map((v, i) => {
        if (i < 12 || !y[i - 12]) return null;
        return ((v - y[i - 12]) / y[i - 12]) * 100;
      });
    }
    traces.push({
      x: periods,
      y,
      name,
      type: "scatter",
      mode: "lines",
      stackgroup: homeTsState.mode === "abs" ? "one" : null,
      line: { color: s.color, width: homeTsState.mode === "abs" ? 0.5 : 2 },
      fillcolor: s.color,
      hovertemplate: homeTsState.mode === "abs"
        ? `<b>%{x}</b><br>${name}: %{y:,.0f} tons<extra></extra>`
        : `<b>%{x}</b><br>${name}: %{y:.1f}%<extra></extra>`,
    });
  }
  Plotly.newPlot("home-timeseries", traces, {
    margin: { t: 10, l: 60, r: 20, b: 50 },
    xaxis: { tickangle: -40 },
    yaxis: {
      title: homeTsState.mode === "abs" ? "ton" : "YoY %",
      zeroline: homeTsState.mode === "yoy",
    },
    legend: { orientation: "h", y: -0.2 },
    hovermode: "x unified",
  }, { displayModeBar: false, responsive: true });
}

function bindMapControls() {
  const groups = [
    { id: "map-control-cat",    state: "filterCategory" },
    { id: "map-control-period", state: "filterPeriod" },
    { id: "map-control-traffic",state: "filterTraffic" },
  ];
  for (const g of groups) {
    const host = document.getElementById(g.id);
    if (!host) continue;
    host.querySelectorAll("button").forEach(btn => {
      btn.addEventListener("click", () => {
        homeState[g.state] = btn.dataset.key;
        host.querySelectorAll("button").forEach(b => {
          if (b.dataset.key === btn.dataset.key) {
            b.classList.add("bg-slate-800", "text-white");
            b.classList.remove("bg-white", "hover:bg-slate-100");
          } else {
            b.classList.remove("bg-slate-800", "text-white");
            b.classList.add("bg-white", "hover:bg-slate-100");
          }
        });
        drawHomeMap();
      });
    });
  }
}

function drawHomeMap() {
  const svg = d3.select("#home-map-svg");
  if (!svg.node() || !homeState.mapData || !homeState.topology) return;
  svg.selectAll("*").remove();

  const W = 900, H = 500;
  // Mercator projection centered on Indonesia (lng ~118, lat ~-2). Manual scale
  // works better than fitSize across the islands chain.
  const projection = d3.geoMercator()
    .center([118, -2.5])
    .scale(950)
    .translate([W / 2, H / 2]);
  const path = d3.geoPath(projection);

  // ---- Layer 1: grayscale base map (Indonesia + neighbors faintly) ----
  const topo = homeState.topology;
  const land = topojson.feature(topo, topo.objects.countries);
  const allCountries = svg.append("g").attr("class", "map-base");
  allCountries.selectAll("path")
    .data(land.features)
    .enter().append("path")
    .attr("d", path)
    .attr("fill", d => d.id == ID_INDONESIA ? "#e2e8f0" : "#f8fafc")
    .attr("stroke", "#cbd5e1")
    .attr("stroke-width", 0.5);

  // ---- Filter routes per controls. v0: bulk + 12m + ln show informative
  // status messages but render the available 24m+all+dn_ln data as fallback. ----
  const status = document.getElementById("home-map-status");
  const notes = [];
  if (homeState.filterCategory === "bulk") {
    notes.push("드라이벌크 OD 분리 미구현 — 탱커 데이터 표시 중");
  }
  if (homeState.filterPeriod === "12m") {
    notes.push("12M OD 미산출 — 24M 누계 표시 중");
  }
  if (homeState.filterTraffic === "ln") {
    notes.push("국제 OD 미분리 — 전체(국내+국제) 표시 중");
  }
  status.textContent = notes.join(" · ") || "24M 누계 · 모든 카테고리 · Top 30 routes";

  let routes = (homeState.mapData.routes_top30 || []).slice();
  // Category color map
  const categoryColors = {};
  for (const c of (homeState.mapData.categories || [])) categoryColors[c.name] = c.color;

  // ---- Layer 2: route paths + animated particles ----
  const routeLayer = svg.append("g").attr("class", "map-routes");
  const tonMax = Math.max(...routes.map(r => r.ton_24m), 1);
  const hi = homeState.highlightCategory;
  routes.forEach((r, i) => {
    const start = projection([r.lon_o, r.lat_o]);
    const end = projection([r.lon_d, r.lat_d]);
    if (!start || !end) return;
    // Quadratic bezier control point: midpoint lifted perpendicular to the segment.
    const mx = (start[0] + end[0]) / 2;
    const my = (start[1] + end[1]) / 2;
    const dx = end[0] - start[0], dy = end[1] - start[1];
    const norm = Math.sqrt(dx * dx + dy * dy) || 1;
    const lift = Math.min(60, norm * 0.3);
    const cx = mx - (dy / norm) * lift;
    const cy = my + (dx / norm) * lift;
    const d = `M ${start[0]} ${start[1]} Q ${cx} ${cy} ${end[0]} ${end[1]}`;
    const color = categoryColors[r.category] || "#6b7280";
    const pathId = `route-path-${i}`;
    const dimmed = hi && r.category !== hi;
    const baseStroke = Math.max(1, 4 * r.ton_24m / tonMax);
    const path = routeLayer.append("path")
      .attr("id", pathId)
      .attr("d", d)
      .attr("fill", "none")
      .attr("stroke", color)
      .attr("stroke-width", baseStroke)
      .attr("stroke-opacity", dimmed ? 0.08 : 0.55)
      .style("cursor", "help")
      .style("transition", "stroke-width 140ms ease, stroke-opacity 140ms ease");
    path.append("title")
      .text(`${r.origin} → ${r.destination}\n${fmtTon(r.ton_24m)} tons · ${r.vessels}척\n${r.category || "—"}`);

    // Hover : bump stroke width + pop opacity even if dimmed
    path.on("mouseenter", function() {
      d3.select(this)
        .attr("stroke-width", baseStroke * 2.2)
        .attr("stroke-opacity", 0.95);
    });
    path.on("mouseleave", function() {
      d3.select(this)
        .attr("stroke-width", baseStroke)
        .attr("stroke-opacity", dimmed ? 0.08 : 0.55);
    });

    // Animated particle along the path (SVG animateMotion). Suppress when
    // the route is dimmed by the legend filter — keeps motion focused.
    if (!dimmed) {
      const dur = 2.5 + Math.random() * 4;
      const particle = routeLayer.append("circle")
        .attr("r", Math.max(2.2, 2.2 * r.ton_24m / tonMax + 1.5))
        .attr("fill", color)
        .attr("opacity", 0.85);
      const motion = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
      motion.setAttribute("dur", `${dur}s`);
      motion.setAttribute("repeatCount", "indefinite");
      motion.setAttribute("rotate", "auto");
      const mpath = document.createElementNS("http://www.w3.org/2000/svg", "mpath");
      mpath.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", `#${pathId}`);
      motion.appendChild(mpath);
      particle.node().appendChild(motion);
    }
  });

  // ---- Layer 3: ports ----
  const ports = (homeState.mapData.ports || []).slice();
  const portTonMax = Math.max(...ports.map(p => p.ton_24m), 1);
  const portLayer = svg.append("g").attr("class", "map-ports");
  portLayer.selectAll("circle")
    .data(ports)
    .enter().append("circle")
    .attr("cx", d => projection([d.lon, d.lat])?.[0])
    .attr("cy", d => projection([d.lon, d.lat])?.[1])
    .attr("r", d => Math.max(2.5, 16 * Math.sqrt(d.ton_24m / portTonMax)))
    .attr("fill", "#1A3A6B")
    .attr("fill-opacity", 0.7)
    .attr("stroke", "#fff")
    .attr("stroke-width", 0.8)
    .append("title")
    .text(d => `${d.name}\n24M ton: ${fmtTon(d.ton_24m)}`);

  // ---- Layer 4: top-5 port labels ----
  const top5 = ports.slice(0, 5);
  const labelLayer = svg.append("g").attr("class", "map-labels");
  labelLayer.selectAll("text")
    .data(top5)
    .enter().append("text")
    .attr("x", d => (projection([d.lon, d.lat])?.[0] || 0) + 8)
    .attr("y", d => (projection([d.lon, d.lat])?.[1] || 0) + 4)
    .attr("font-size", "11px")
    .attr("font-weight", "600")
    .attr("fill", "#1e293b")
    .attr("paint-order", "stroke")
    .attr("stroke", "white")
    .attr("stroke-width", 3)
    .text(d => d.name);

  // ---- Legend (PR-11: clickable to filter routes by category) ----
  const legend = document.getElementById("home-map-legend");
  if (legend) {
    const cats = homeState.mapData.categories || [];
    legend.innerHTML =
      `<div class="font-semibold mb-1 flex items-center justify-between gap-2">
         <span>화물 카테고리</span>
         ${homeState.highlightCategory
           ? `<button id="map-legend-clear" class="text-[10px] text-blue-600 hover:underline" type="button">전체</button>`
           : ""}
       </div>` +
      cats.map(c => {
        const active = homeState.highlightCategory === c.name;
        const dimmed = homeState.highlightCategory && !active;
        return `<button type="button" data-cat="${c.name}"
                       class="map-legend-item flex items-center gap-1.5 w-full text-left py-0.5 px-1 rounded hover:bg-slate-100"
                       style="opacity:${dimmed ? 0.4 : 1}">
                  <span class="inline-block w-2.5 h-2.5 rounded-sm" style="background:${c.color}"></span>
                  <span class="text-slate-700 ${active ? "font-semibold" : ""}">${c.name}</span>
                </button>`;
      }).join("");
    legend.querySelectorAll("[data-cat]").forEach(btn => {
      btn.addEventListener("click", () => {
        const cat = btn.dataset.cat;
        homeState.highlightCategory = (homeState.highlightCategory === cat) ? null : cat;
        drawHomeMap();
      });
    });
    const clr = document.getElementById("map-legend-clear");
    if (clr) clr.addEventListener("click", () => {
      homeState.highlightCategory = null;
      drawHomeMap();
    });
  }
}

function fillForeignSidebar() {
  const data = homeState.mapData?.foreign_ports || {};
  const tonEl = document.getElementById("map-intl-ton");
  const noteEl = document.getElementById("map-intl-note");
  if (tonEl) {
    tonEl.textContent = data.totals_intl_ton != null
      ? `${fmtTon(data.totals_intl_ton)} tons`
      : "—";
  }
  if (noteEl) {
    noteEl.textContent = data.note ||
      "tanker_flow_map.totals.intl_ton 기준 누계";
  }
}

function fillMapInsights() {
  const host = document.getElementById("map-insights");
  if (!host) return;
  const items = homeState.mapData?.insights || [];
  host.innerHTML = items.length
    ? items.map((t, i) => `
        <li class="flex gap-2 items-start">
          <span class="text-slate-400 font-mono text-[10px] mt-0.5 min-w-[14px]">${i + 1}.</span>
          <span>${t}</span>
        </li>`).join("")
    : `<li class="text-slate-400">데이터 없음</li>`;
}

// ---------- PR-4: Cargo & Fleet (treemap + commodity bars + class donut + age bars) ----------
async function renderCargoFleet() {
  setupSourceLabels(document.getElementById("tab-cargo-fleet"));
  let payload;
  try { payload = await loadDerived("cargo_fleet.json"); }
  catch (e) {
    const host = document.getElementById("cf-treemap");
    if (host) host.innerHTML = errorState(`cargo_fleet.json 로드 실패: ${e.message}`);
    return;
  }
  drawCargoTreemap(payload.treemap_categories || []);
  drawCargoCommodityBars(payload.top_commodities || []);
  drawFleetClassDonut(payload.class_counts || []);
  drawFleetAgeBars(payload.age_bins?.bins || []);
  fillCargoFleetCaptions(payload);
}

// PR-15: per-chart 1-line auto facts beneath each Cargo & Fleet widget.
function fillCargoFleetCaptions(payload) {
  // 1) Treemap — top-3 categories' share of treemap total
  const cats = (payload.treemap_categories || []).slice().sort((a, b) => b.ton_total - a.ton_total);
  const totCats = cats.reduce((s, r) => s + (r.ton_total || 0), 0);
  const top3 = cats.slice(0, 3).reduce((s, r) => s + r.ton_total, 0);
  const cap1 = document.getElementById("cf-treemap-caption");
  if (cap1) {
    cap1.textContent = totCats > 0
      ? `상위 3개 카테고리(${cats.slice(0, 3).map(c => c.category).join(" · ")})가 전체 ${cats.length}개의 ${(top3 / totCats * 100).toFixed(1)}%를 차지합니다.`
      : "데이터 없음";
  }

  // 2) Commodities — top single commodity share of top-10 sum
  const coms = (payload.top_commodities || []).slice();
  const totC = coms.reduce((s, r) => s + (r.ton_total || 0), 0);
  const cap2 = document.getElementById("cf-commodity-caption");
  if (cap2 && coms[0]) {
    cap2.textContent = totC > 0
      ? `${coms[0].name} 단일 품목이 Top 10 누적 ton의 ${(coms[0].ton_total / totC * 100).toFixed(1)}%를 차지합니다.`
      : "데이터 없음";
  }

  // 3) Class donut — share of largest class
  const classes = (payload.class_counts || []).slice().sort((a, b) => b.count - a.count);
  const totCls = classes.reduce((s, r) => s + (r.count || 0), 0);
  const cap3 = document.getElementById("cf-class-caption");
  if (cap3 && classes[0]) {
    cap3.textContent = totCls > 0
      ? `${classes[0]["class"]}이(가) 등록 선박 ${fmtCount(totCls)}척 중 ${(classes[0].count / totCls * 100).toFixed(1)}%로 가장 큰 비중입니다.`
      : "데이터 없음";
  }

  // 4) Age bars — % of fleet that is 25+ years old (older=true bins)
  const bins = (payload.age_bins?.bins || []);
  const totAge = bins.reduce((s, b) => s + (b.count || 0), 0);
  const olderCount = bins.filter(b => b.older).reduce((s, b) => s + (b.count || 0), 0);
  const cap4 = document.getElementById("cf-age-caption");
  if (cap4) {
    cap4.textContent = totAge > 0
      ? `등록 선박의 ${(olderCount / totAge * 100).toFixed(1)}%가 25년 이상 (${fmtCount(olderCount)}척 / ${fmtCount(totAge)}척).`
      : "데이터 없음";
  }
}

function drawCargoTreemap(rows) {
  if (!rows.length) return;
  // Plotly treemap: parents="" creates a single-level treemap.
  const labels = rows.map(r => r.category);
  const values = rows.map(r => r.ton_total);
  const palette = ["#1A3A6B", "#0284c7", "#059669", "#d97706", "#7c3aed",
                   "#92400e", "#65a30d", "#475569", "#dc2626", "#0891b2",
                   "#9333ea", "#be185d", "#84cc16", "#ea580c", "#0ea5e9"];
  Plotly.newPlot("cf-treemap", [{
    type: "treemap",
    labels,
    parents: rows.map(_ => ""),
    values,
    marker: { colors: palette.slice(0, rows.length), line: { width: 1, color: "#fff" } },
    textinfo: "label+value+percent root",
    texttemplate: "<b>%{label}</b><br>%{value:,.0f} ton<br>%{percentRoot:.1%}",
    hovertemplate: "<b>%{label}</b><br>%{value:,.0f} tons<extra></extra>",
  }], {
    margin: { t: 10, l: 10, r: 10, b: 10 },
  }, { displayModeBar: false, responsive: true });
}

function drawCargoCommodityBars(rows) {
  if (!rows.length) return;
  const list = rows.slice().reverse();   // top item at top of chart
  const tonMax = Math.max(...list.map(r => r.ton_total), 1);
  Plotly.newPlot("cf-commodity-bar", [{
    x: list.map(r => r.ton_total),
    y: list.map(r => r.name),
    type: "bar",
    orientation: "h",
    marker: {
      color: list.map((_, i) => i === list.length - 1 ? "#1A3A6B" : "#56C0E0"),
      line: { color: "#1e293b", width: 0.5 },
    },
    text: list.map(r => fmtTon(r.ton_total)),
    textposition: "outside",
    cliponaxis: false,
    hovertemplate: "<b>%{y}</b><br>%{x:,.0f} tons<extra></extra>",
  }], {
    margin: { t: 10, l: 130, r: 70, b: 40 },
    xaxis: { title: "ton (24M)" },
  }, { displayModeBar: false, responsive: true });
}

function drawFleetClassDonut(rows) {
  if (!rows.length) return;
  const palette = {
    "Container":     "#0284c7",
    "Bulk Carrier":  "#7c3aed",
    "Tanker":        "#1A3A6B",
    "General Cargo": "#0891b2",
    "Other Cargo":   "#65a30d",
    "Other":         "#94a3b8",
  };
  Plotly.newPlot("cf-class-donut", [{
    values: rows.map(r => r.count),
    labels: rows.map(r => r.class),
    type: "pie",
    hole: 0.55,
    marker: { colors: rows.map(r => palette[r.class] || "#94a3b8") },
    textinfo: "label+percent",
    hovertemplate: "<b>%{label}</b><br>%{value:,} 척 (%{percent})<extra></extra>",
  }], {
    margin: { t: 10, l: 20, r: 20, b: 30 },
    legend: { orientation: "v", y: 0.5, x: 1.05 },
  }, { displayModeBar: false, responsive: true });
}

function drawFleetAgeBars(bins) {
  if (!bins.length) return;
  Plotly.newPlot("cf-age-bars", [{
    x: bins.map(b => b.label),
    y: bins.map(b => b.count),
    type: "bar",
    marker: {
      color: bins.map(b => b.older ? "#dc2626" : "#1A3A6B"),
      opacity: 0.85,
    },
    text: bins.map(b => b.count.toLocaleString()),
    textposition: "outside",
    hovertemplate: "<b>%{x}</b><br>%{y:,} 척<extra></extra>",
    cliponaxis: false,
  }], {
    margin: { t: 30, l: 60, r: 20, b: 50 },
    xaxis: { title: "선령" },
    yaxis: { title: "선박 수" },
    annotations: [{
      x: 0.5, y: 1.08, xref: "paper", yref: "paper",
      text: "<span style='color:#dc2626'>■</span> 25년 이상 (강조)",
      showarrow: false, font: { size: 11, color: "#475569" },
    }],
  }, { displayModeBar: false, responsive: true });
}

boot().catch(e => {
  console.error(e);
  document.body.insertAdjacentHTML("afterbegin",
    `<div class="m-4">${errorState(`초기 데이터 로드 실패: ${e.message}`)}</div>`);
});
