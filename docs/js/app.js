// Indonesia Shipping Intelligence — static dashboard
// Loads precomputed JSON in docs/data/, renders Plotly charts, supports
// client-side search/filter/sort. No server side.

const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString());
const fmt1 = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 }));
const fmt0 = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }));

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

// Read derived/meta.json and write the freshness line into the global
// disclaimer footer. Degrades silently if the derived/ payload is missing.
async function loadGlobalFooter() {
  const target = document.getElementById("footer-freshness");
  if (!target) return;
  try {
    const m = await loadDerived("meta.json");
    const lk3 = m.latest_lk3_month || "—";
    const vsl = m.latest_vessel_snapshot_month || "—";
    const built = (m.build_at || "").replace("T", " ").replace(/Z$/, " UTC");
    target.textContent =
      `LK3 latest: ${lk3} · vessel snapshot: ${vsl} · build: ${built}`;
  } catch (e) {
    target.textContent = "Freshness data unavailable (docs/derived/meta.json not built yet)";
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

const tsState = {
  filter: "ALL",
  subclassFacts: null,
  routeFacts: null,
};

async function renderTankerSector() {
  const filterHost = document.getElementById("ts-subclass-filter");
  const cardHost = document.getElementById("ts-subclass-cards");
  const captionEl = document.getElementById("ts-route-caption");
  const regHost = document.getElementById("ts-regulatory");

  if (!filterHost || !cardHost) return;

  // Load derived inputs
  try {
    [tsState.subclassFacts, tsState.routeFacts] = await Promise.all([
      loadDerived("subclass_facts.json"),
      loadDerived("route_facts.json"),
    ]);
  } catch (e) {
    cardHost.innerHTML = `<div class="bg-yellow-50 text-yellow-900 text-sm p-3 rounded col-span-full">
      Tanker Sector: derived JSON 로드 실패 (${e.message}). <code>python scripts/build_derived.py</code>를 실행하세요.</div>`;
    return;
  }

  // Render subclass filter pills
  filterHost.innerHTML = "";
  TANKER_SUBCLASS_FILTER_OPTIONS.forEach(opt => {
    const btn = document.createElement("button");
    btn.dataset.key = opt.key;
    btn.className = "ts-pill px-2.5 py-1 rounded border border-slate-200 hover:bg-slate-100";
    btn.textContent = opt.label;
    btn.addEventListener("click", () => {
      tsState.filter = opt.key;
      renderTankerSectorBody();
    });
    filterHost.appendChild(btn);
  });

  // Regulatory notes (one-time fetch + inject)
  if (regHost) {
    try {
      const r = await fetch("./derived/regulatory_notes.html");
      if (r.ok) regHost.innerHTML = await r.text();
      else regHost.innerHTML =
        `<p class="text-xs text-slate-500">regulatory_notes.html 로드 실패 (${r.status}). build script 재실행 필요.</p>`;
    } catch (e) {
      regHost.innerHTML =
        `<p class="text-xs text-slate-500">regulatory_notes 로드 오류: ${e.message}</p>`;
    }
  }

  renderTankerSectorBody();
}

function renderTankerSectorBody() {
  const cardHost = document.getElementById("ts-subclass-cards");
  const summaryEl = document.getElementById("ts-filter-summary");
  const captionEl = document.getElementById("ts-route-caption");
  const routeCountEl = document.getElementById("ts-route-count");
  if (!cardHost || !tsState.subclassFacts) return;

  const filter = tsState.filter;
  // Active state for filter pills
  document.querySelectorAll("#ts-subclass-filter .ts-pill").forEach(b => {
    if (b.dataset.key === filter) {
      b.classList.add("bg-slate-800", "text-white", "border-slate-800");
      b.classList.remove("hover:bg-slate-100");
    } else {
      b.classList.remove("bg-slate-800", "text-white", "border-slate-800");
      b.classList.add("hover:bg-slate-100");
    }
  });

  // ---- subclass cards ----
  let rows = (tsState.subclassFacts.subclasses || []).filter(r => r.subclass !== "UNKNOWN");
  if (filter !== "ALL") rows = rows.filter(r => r.subclass === filter);

  cardHost.innerHTML = rows.map(r => {
    const cagrTxt = r.cagr_24m_pct == null
      ? `<span class="text-slate-400">— (Insufficient data)</span>`
      : `<span class="${r.cagr_24m_pct >= 0 ? "text-blue-700" : "text-red-700"} font-semibold">${r.cagr_24m_pct >= 0 ? "+" : ""}${r.cagr_24m_pct.toFixed(2)}%</span>`;
    const callsPerVessel = (r.vessel_count && r.vessel_count > 0)
      ? (r.calls_last_12m / r.vessel_count).toFixed(1)
      : "—";
    const ageTxt = r.avg_age_gt_weighted == null ? "—" : `${r.avg_age_gt_weighted.toFixed(1)}년`;
    const hhiTxt = r.hhi == null ? "—" : Math.round(r.hhi).toLocaleString();
    const color = SUBCLASS_PALETTE[r.subclass] || "#64748b";
    return `<div class="bg-white rounded-xl shadow p-4 border-l-4" style="border-color:${color}">
      <div class="flex items-baseline justify-between mb-2">
        <h3 class="font-semibold">${r.subclass}</h3>
        <span class="text-xs text-slate-400">${(r.vessel_count || 0).toLocaleString()} vessels</span>
      </div>
      <dl class="text-sm space-y-1">
        <div class="flex justify-between"><dt class="text-slate-500">24M ton CAGR</dt><dd>${cagrTxt}</dd></div>
        <div class="flex justify-between"><dt class="text-slate-500">12M 척당 평균 calls</dt><dd>${callsPerVessel}</dd></div>
        <div class="flex justify-between"><dt class="text-slate-500">GT 가중 평균 선령</dt><dd>${ageTxt}</dd></div>
        <div class="flex justify-between"><dt class="text-slate-500">운영사 수 / HHI</dt><dd>${r.operator_count} · ${hhiTxt}</dd></div>
      </dl>
      <p class="text-[10.5px] text-slate-400 mt-3 italic">
        모든 수치는 공개 데이터 집계 결과이며, 시장 전망이나 투자 판단을 의미하지 않습니다.
      </p>
    </div>`;
  }).join("");

  if (summaryEl) {
    summaryEl.textContent = filter === "ALL"
      ? `${rows.length}개 subclass · 모두 표시`
      : `${filter} 단일 subclass`;
  }

  // ---- route scatter ----
  let routes = (tsState.routeFacts.routes || []).slice();
  if (filter !== "ALL") {
    routes = routes.filter(r => bucketsToSubclasses(r.buckets).has(filter));
  }
  if (routeCountEl) {
    routeCountEl.textContent = `${routes.length} routes shown`;
  }
  if (captionEl) {
    captionEl.textContent = filter === "ALL"
      ? "x = 24M ton 변화율 (per-month OD aggregation 미구현 → 0 anchored), y = 활동 선박 수, 크기 = 24M ton. 해석은 사용자의 분석 목적에 따라 달라집니다."
      : `x = 24M ton 변화율 (insufficient data), y = 활동 선박 수, 크기 = 24M ton. ${filter} 관련 항로만 표시 (bucket 라벨 기반 매칭).`;
  }

  if (routes.length === 0) {
    Plotly.purge("ts-route-scatter");
    document.getElementById("ts-route-scatter").innerHTML =
      `<div class="text-sm text-slate-500 text-center py-12">선택한 subclass에 매칭되는 항로가 없습니다.</div>`;
    return;
  }

  const sizeMax = Math.max(...routes.map(r => r.ton_24m || 0), 1);
  const trace = {
    x: routes.map(_ => 0),       // change_pct unavailable in v0
    y: routes.map(r => r.vessels_seen || 0),
    text: routes.map(r => `${r.origin} → ${r.destination}`),
    mode: "markers",
    type: "scatter",
    marker: {
      size: routes.map(r => Math.max(8, 60 * (r.ton_24m || 0) / sizeMax)),
      color: routes.map(r => {
        const subs = bucketsToSubclasses(r.buckets);
        if (subs.has("Crude Oil")) return SUBCLASS_PALETTE["Crude Oil"];
        if (subs.has("LPG"))       return SUBCLASS_PALETTE["LPG"];
        if (subs.has("LNG"))       return SUBCLASS_PALETTE["LNG"];
        if (subs.has("FAME / Vegetable Oil")) return SUBCLASS_PALETTE["FAME / Vegetable Oil"];
        if (subs.has("Chemical"))  return SUBCLASS_PALETTE["Chemical"];
        if (subs.has("Product"))   return SUBCLASS_PALETTE["Product"];
        return "#94a3b8";
      }),
      opacity: 0.8,
      line: { color: "#1e293b", width: 0.5 },
    },
    customdata: routes.map(r => [r.ton_24m, (r.buckets || []).slice(0, 4).join(", ")]),
    hovertemplate:
      "<b>%{text}</b><br>" +
      "Vessels seen: %{y}<br>" +
      "24M ton: %{customdata[0]:,.0f}<br>" +
      "Buckets: %{customdata[1]}<extra></extra>",
  };
  Plotly.newPlot("ts-route-scatter", [trace], {
    margin: { t: 10, l: 50, r: 20, b: 50 },
    xaxis: {
      title: "24M ton change % (insufficient data — needs per-month OD aggregation)",
      zeroline: true,
      zerolinecolor: "#cbd5e1",
      range: [-1, 1],
    },
    yaxis: { title: "활동 선박 수 (24M)" },
    showlegend: false,
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

  // Disclaimer banner
  const meta = f.metadata || {};
  const allPlaceholder = f.companies.every(c => c.data_quality === "estimated_placeholder");
  if (meta.source || allPlaceholder) {
    const banner = document.getElementById("fn-banner");
    const bannerTxt = document.getElementById("fn-banner-text");
    banner.classList.remove("hidden");
    bannerTxt.textContent =
      ` ${meta.source || ""} (last updated ${meta.last_updated || "—"})`
      + (allPlaceholder ? " — 모든 수치는 placeholder로, 외부 사용 전 IDX 사업보고서로 검증 필요." : "");
  }

  // First-time setup: populate year dropdown + bind listeners
  if (!fnState.initialized) {
    fnState.initialized = true;
    const years = Array.from(new Set(f.rows.map(r => r.year))).sort();
    const yrSel = document.getElementById("fn-year");
    yrSel.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join("");
    yrSel.value = years[years.length - 1];
    fnState.year = yrSel.value;
    yrSel.addEventListener("change", (e) => { fnState.year = e.target.value; renderFinancials(); });
    document.getElementById("fn-sortby").addEventListener("change", (e) => {
      fnState.sortBy = e.target.value; renderFinancials();
    });
  }

  const yr = fnState.year;
  const sortBy = fnState.sortBy;
  const yrRows = f.rows.filter(r => r.year === yr);

  // KPI strip — industry totals for the selected year
  const sumOf = (k) => yrRows.reduce((s, r) => s + (r[k] || 0), 0);
  const totRev = sumOf("revenue");
  const totNi = sumOf("net_income");
  const totFleetGt = sumOf("fleet_gt");
  const margin = totRev ? (totNi / totRev * 100) : null;
  renderKpis("kpi-financials", [
    { label: `합산 매출 (${yr})`, value: fmt0(totRev), sub: "IDR billion" },
    { label: "합산 순이익", value: fmt0(totNi),
      sub: margin == null ? "—" : `평균 마진 ${margin.toFixed(1)}%` },
    { label: "합산 선대 GT", value: fmt0(totFleetGt), sub: "kGT (1,000 GT)" },
    { label: "수록 기업 수", value: fmt(yrRows.length),
      sub: f.companies.length === yrRows.length
            ? `전체 ${f.companies.length}개사` : `${f.companies.length}개사 중` },
  ]);

  // Revenue trend — multi-line, all companies, all years
  const tickerColors = {};
  const palette = ["#1e3a8a", "#0d9488", "#d97706", "#6d28d9", "#dc2626",
                   "#0ea5e9", "#16a34a", "#db2777", "#475569"];
  f.companies.forEach((c, i) => { tickerColors[c.ticker] = palette[i % palette.length]; });
  const allYears = Array.from(new Set(f.rows.map(r => r.year))).sort();
  const revTraces = f.companies.map(c => {
    const byYear = {};
    for (const r of f.rows) {
      if (r.ticker === c.ticker) byYear[r.year] = r.revenue;
    }
    return {
      x: allYears, y: allYears.map(y => byYear[y] ?? null),
      name: c.ticker, type: "scatter", mode: "lines+markers",
      line: { color: tickerColors[c.ticker] },
      hovertemplate: `<b>${c.ticker}</b><br>${c.name_short}<br>%{x}: %{y:,} bn IDR<extra></extra>`,
    };
  });
  Plotly.newPlot("chart-fn-revenue", revTraces,
    { margin: { t: 10, l: 60, r: 10, b: 50 }, yaxis: { title: "Revenue (IDR bn)" },
      legend: { orientation: "h", y: -0.18 } },
    { displayModeBar: false, responsive: true });

  // Margin vs leverage scatter for selected year
  Plotly.newPlot("chart-fn-scatter", [{
    x: yrRows.map(r => r.net_margin),
    y: yrRows.map(r => r.debt_to_assets),
    text: yrRows.map(r => r.ticker),
    mode: "markers+text", textposition: "top center",
    marker: {
      size: yrRows.map(r => Math.max(8, Math.sqrt((r.revenue || 0) / 30))),
      color: yrRows.map(r => tickerColors[r.ticker] || "#475569"),
      opacity: 0.75, line: { color: "#0f172a", width: 1 },
    },
    hovertemplate: "<b>%{text}</b><br>net margin %{x:.1f}%<br>debt/assets %{y:.1f}%<extra></extra>",
  }], {
    margin: { t: 10, l: 60, r: 10, b: 50 },
    xaxis: { title: "Net margin (%)", zeroline: true },
    yaxis: { title: "Debt / Assets (%)", zeroline: false },
  }, { displayModeBar: false, responsive: true });

  // Comparison table
  document.getElementById("fn-table-year").textContent = `(${yr} 기준)`;
  const sorted = yrRows.slice().sort((a, b) => {
    const x = a[sortBy], y = b[sortBy];
    if (x == null) return 1; if (y == null) return -1;
    return y - x;  // desc by default for all numeric metrics
  });
  // Map ticker → company name + focus
  const byTicker = {};
  for (const c of f.companies) byTicker[c.ticker] = c;
  const num0 = (v) => v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  const num1 = (v) => v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
  const pct1 = (v) => v == null ? "—" : `${Number(v).toFixed(1)}%`;
  const niCell = (v) => {
    if (v == null) return `<td class="px-2 py-1 text-right">—</td>`;
    const cls = v < 0 ? "text-red-600 font-semibold" : "";
    return `<td class="px-2 py-1 text-right ${cls}">${num0(v)}</td>`;
  };
  document.querySelector("#fn-tbl tbody").innerHTML = sorted.map(r => {
    const c = byTicker[r.ticker] || {};
    return `<tr>
      <td class="px-2 py-1 font-mono">${r.ticker}</td>
      <td class="px-2 py-1">${c.name_short || ""}</td>
      <td class="px-2 py-1 text-slate-500">${(c.sector_focus || []).join(" · ")}</td>
      <td class="px-2 py-1 text-right">${num0(r.revenue)}</td>
      ${niCell(r.net_income)}
      <td class="px-2 py-1 text-right">${pct1(r.net_margin)}</td>
      <td class="px-2 py-1 text-right">${num0(r.total_assets)}</td>
      <td class="px-2 py-1 text-right">${pct1(r.debt_to_assets)}</td>
      <td class="px-2 py-1 text-right">${pct1(r.roa)}</td>
      <td class="px-2 py-1 text-right">${num0(r.capex)}</td>
      <td class="px-2 py-1 text-right">${num0(r.fleet_gt)}</td>
      <td class="px-2 py-1 text-right">${num0(r.fleet_count)}</td>
    </tr>`;
  }).join("");
}

// ---------- Tabs ----------
function showTab(name) {
  document.querySelectorAll(".tab").forEach(t => {
    if (t.dataset.tab === name) { t.classList.add("active"); t.classList.remove("hover:bg-slate-700"); }
    else { t.classList.remove("active"); t.classList.add("hover:bg-slate-700"); }
  });
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
  const panel = document.getElementById(`tab-${name}`);
  if (panel) panel.classList.remove("hidden");
  ensureLoaded(name);
  // PR-B: re-scan source labels since lazy-loaded tabs may add new
  // [data-source] containers on activation.
  if (panel) setupSourceLabels(panel);
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
  showTab("overview");
  loadGlobalFooter();
  setupSourceLabels();
}


// ---------- PR-2: Home animated flow map (d3 + topojson) ----------
// World atlas TopoJSON (countries-110m). Loaded once and cached.
const TOPO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";
const ID_INDONESIA = 360;  // ISO 3166-1 numeric

const homeState = {
  mapData: null,
  topology: null,
  filterCategory: "all",   // all | tanker | bulk (bulk shows note)
  filterPeriod: "24m",     // 24m | 12m (12m shows note)
  filterTraffic: "dn_ln",  // dn_ln | ln (ln shows note)
};

async function renderHome() {
  setupSourceLabels(document.getElementById("tab-overview"));

  // Load both the derived flow data and the world topology in parallel.
  let topo;
  try {
    [homeState.mapData, topo] = await Promise.all([
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

  bindMapControls();
  drawHomeMap();
  fillForeignSidebar();
  fillMapInsights();
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
    routeLayer.append("path")
      .attr("id", pathId)
      .attr("d", d)
      .attr("fill", "none")
      .attr("stroke", color)
      .attr("stroke-width", Math.max(1, 4 * r.ton_24m / tonMax))
      .attr("stroke-opacity", 0.55)
      .append("title")
      .text(`${r.origin} → ${r.destination}\n${(r.ton_24m / 1e6).toFixed(2)}M tons · ${r.vessels}척\n${r.category || "—"}`);

    // Animated particle along the path (SVG animateMotion).
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
    .text(d => `${d.name}\n24M ton: ${(d.ton_24m / 1e6).toFixed(2)}M`);

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

  // ---- Legend ----
  const legend = document.getElementById("home-map-legend");
  if (legend) {
    legend.innerHTML =
      `<div class="font-semibold mb-1">화물 카테고리</div>` +
      (homeState.mapData.categories || []).map(c =>
        `<div class="flex items-center gap-1.5"><span class="inline-block w-2.5 h-2.5 rounded-sm" style="background:${c.color}"></span><span class="text-slate-700">${c.name}</span></div>`
      ).join("");
  }
}

function fillForeignSidebar() {
  const data = homeState.mapData?.foreign_ports || {};
  const tonEl = document.getElementById("map-intl-ton");
  const noteEl = document.getElementById("map-intl-note");
  if (tonEl) {
    tonEl.textContent = data.totals_intl_ton != null
      ? `${(data.totals_intl_ton / 1e6).toFixed(1)}M tons`
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
    ? items.map(t => `<li>• ${t}</li>`).join("")
    : `<li class="text-slate-400">데이터 없음</li>`;
}

async function renderCargoFleet() {
  // Treemap + class donut + age bars land in PR-4.
  setupSourceLabels(document.getElementById("tab-cargo-fleet"));
}

boot().catch(e => {
  console.error(e);
  document.body.insertAdjacentHTML("afterbegin",
    `<div class="bg-red-100 text-red-800 p-4">데이터 로드 실패: ${e.message}</div>`);
});
