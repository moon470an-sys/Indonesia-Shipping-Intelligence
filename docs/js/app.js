// Indonesia Shipping Intelligence — static dashboard
// Loads precomputed JSON in docs/data/, renders Plotly charts, supports
// client-side search/filter/sort. No server side.

const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString());
const fmt1 = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 }));
const fmt0 = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }));

const state = {
  meta: null,
  overview: null,
  fleet: null,
  vessels: null,
  cargo: null,
  changes: null,
  kpi: null,
  taxonomy: null,
  sectorMonthly: null,
  financials: null,
  loaded: new Set(),
  vesselsRows: [],
  vesselsSort: { col: 6, dir: -1 },
  vcSort: { col: 0, dir: 1 },
  ccSort: { col: 9, dir: -1 },
};

async function loadJson(name) {
  const r = await fetch(`./data/${name}`);
  if (!r.ok) throw new Error(`fetch ${name} failed ${r.status}`);
  return await r.json();
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

function renderHeroKpis() {
  const k = state.kpi;
  if (!k) return;
  const baseline = k.is_baseline;
  const vc = k.vessel_changes || {};
  const items = [
    { label: "총 선박 등록", value: fmt(k.fleet_total),
      sub: baseline ? "(baseline 스냅샷)"
                    : `이번 달 +${fmt(vc.added || 0)} / -${fmt(vc.removed || 0)} / ${fmt(vc.modified_cells || 0)} 변경` },
    { label: `최근 ton (${k.latest_period || '—'})`, value: fmt0(k.latest_ton),
      sub: k.latest_period_is_partial_data_dropped ? "* 직전 월의 부분 데이터 제외" : "ton 합계" },
    { label: "MoM (전월 대비)", value: pctSign(k.mom_pct),
      sub: "Bongkar + Muat" },
    { label: "YoY (전년 동월 대비)", value: pctSign(k.yoy_pct), sub: "Bongkar + Muat" },
  ];
  renderKpis("kpi-hero", items);

  // Sector donut (latest period). Default: by calls.
  const sel = document.getElementById("overview-sector-metric");
  const drawSector = () => {
    const metric = sel.value || "pct_calls";
    const ts = (k.top_sectors || []).slice().sort((a, b) => (b[metric] - a[metric]));
    Plotly.newPlot("chart-overview-sector", [{
      labels: ts.map(t => t.sector), values: ts.map(t => t[metric]),
      type: "pie", hole: 0.5,
      marker: { colors: ts.map(t => SECTOR_PALETTE[t.sector] || "#6b7280") },
      textinfo: "label+percent", textposition: "outside",
      hovertemplate: metric === "pct_calls"
        ? "%{label}<br>%{value:.2f}%<br>calls %{customdata:,}<extra></extra>"
        : "%{label}<br>%{value:.2f}%<br>ton %{customdata:,}<extra></extra>",
      customdata: ts.map(t => metric === "pct_calls" ? t.calls : t.ton),
    }], { margin: { t: 10, l: 10, r: 10, b: 10 }, showlegend: false },
    { displayModeBar: false, responsive: true });
  };
  if (sel && !sel.dataset.bound) {
    sel.dataset.bound = "1";
    sel.addEventListener("change", drawSector);
  }
  drawSector();

  // Monthly ton trend (single series; per-sector breakdown is in Trends tab)
  const ms = k.monthly_series || [];
  Plotly.newPlot("chart-overview-monthly-ton", [{
    x: ms.map(r => r.period), y: ms.map(r => r.ton),
    type: "scatter", mode: "lines+markers", fill: "tozeroy",
    line: { color: "#1e3a8a" }, marker: { size: 5 },
    hovertemplate: "%{x}<br>%{y:,.0f} ton<extra></extra>",
  }], { margin: { t: 10, l: 60, r: 10, b: 40 }, xaxis: { tickangle: -40 }, yaxis: { title: "ton" } },
  { displayModeBar: false, responsive: true });
}

function renderOverview() {
  const o = state.overview;
  const k = state.changes;
  document.getElementById("meta-line").textContent =
    `snapshot ${o.snapshot_month} · change month ${k ? k.change_month : "(없음)"} · ${state.meta.vessel_months.length} snapshots`;
  document.getElementById("generated-at").textContent = state.meta.generated_at || "—";
  document.getElementById("about-meta").textContent =
    `Snapshots: ${state.meta.vessel_months.length} (vessel) / ${state.meta.cargo_months.length} (cargo) — generated ${state.meta.generated_at}`;

  renderHeroKpis();

  renderKpis("kpi-overview", [
    { label: "선박 등록", value: fmt(o.vessel_total), sub: `${o.vessel_codes}/56 코드` },
    { label: "항구", value: fmt(o.cargo_ports), sub: `등록된 ${o.ports_total}개` },
    { label: "물동량 행", value: fmt(o.cargo_rows), sub: `${o.cargo_keys}/${o.cargo_keys_theoretical} 키` },
    { label: "총 GT", value: fmt0(o.vessel_sum_gt), sub: `평균 ${fmt0(o.vessel_avg_gt)} · 최대 ${fmt0(o.vessel_max_gt)}` },
  ]);

  if (k) {
    const v = k.vessel_kpi || {};
    const c = k.cargo_kpi || {};
    renderKpis("kpi-changes", [
      { label: "선박 ADDED", value: fmt(v.ADDED || 0) },
      { label: "선박 REMOVED", value: fmt(v.REMOVED || 0) },
      { label: "선박 MODIFIED 셀", value: fmt(v.MODIFIED || 0) },
      { label: "Cargo ADDED 키", value: fmt(c.ADDED || 0) },
      { label: "Cargo REMOVED 키", value: fmt(c.REMOVED || 0) },
      { label: "Cargo REVISED 셀", value: fmt(c.REVISED || 0) },
    ]);
  }

  // monthly traffic
  const mt = o.monthly_traffic;
  const periods = Array.from(new Set(mt.map(r => r.period))).sort();
  const dn = periods.map(p => (mt.find(r => r.period === p && r.kind === "dn") || {}).rows || 0);
  const ln = periods.map(p => (mt.find(r => r.period === p && r.kind === "ln") || {}).rows || 0);
  Plotly.newPlot("chart-monthly", [
    { x: periods, y: dn, type: "bar", name: "dn (국내)", marker: { color: "#0ea5e9" } },
    { x: periods, y: ln, type: "bar", name: "ln (국제)", marker: { color: "#f97316" } },
  ], { barmode: "group", margin: { t: 10, l: 50, r: 10, b: 60 }, xaxis: { tickangle: -40 } },
  { displayModeBar: false, responsive: true });

  // top ports
  const tp = o.top_ports.slice(0, 20);
  Plotly.newPlot("chart-top-ports", [
    { x: tp.map(p => p.port), y: tp.map(p => p.dn), name: "dn", type: "bar", marker: { color: "#0ea5e9" } },
    { x: tp.map(p => p.port), y: tp.map(p => p.ln), name: "ln", type: "bar", marker: { color: "#f97316" } },
  ], { barmode: "stack", margin: { t: 10, l: 50, r: 10, b: 80 }, xaxis: { tickangle: -40 } },
  { displayModeBar: false, responsive: true });
}

// ---------- Fleet ----------
// Column indexes mirror docs/data/vessels_search.json schema:
//   0 key  1 code  2 name  3 call_sign  4 type  5 owner  6 gt  7 year  8 imo
//   9 engine  10 engine_type  11 flag  12 loa  13 width  14 depth
//   15 sector  16 vessel_class
const FCOL = { KEY: 0, CODE: 1, NAME: 2, CALL: 3, TYPE: 4, OWNER: 5, GT: 6,
               YEAR: 7, IMO: 8, ENGINE: 9, ETYPE: 10, FLAG: 11,
               LOA: 12, WIDTH: 13, DEPTH: 14, SECTOR: 15, CLASS: 16 };

// Stable sector palette mirrors backend.taxonomy.SECTOR_PALETTE so charts
// stay color-consistent across tabs.
const SECTOR_PALETTE = {
  PASSENGER: "#0d9488",
  CARGO: "#1e3a8a",
  FISHING: "#d97706",
  OFFSHORE_SUPPORT: "#475569",
  NON_COMMERCIAL: "#6b7280",
  UNMAPPED: "#dc2626",
};

const fleetState = {
  bounds: null,        // {yr:[lo,hi], gt, loa, w, d}
  filtered: [],        // current filtered rows
  initialized: false,
};

function rangeOf(rows, idx, isInt) {
  let lo = Infinity, hi = -Infinity;
  for (const r of rows) {
    const v = r[idx];
    if (v == null || v === "" || v < 0) continue;
    const n = Number(v);
    if (!isFinite(n)) continue;
    if (n < lo) lo = n;
    if (n > hi) hi = n;
  }
  if (lo === Infinity) { lo = 0; hi = 0; }
  return isInt ? [Math.floor(lo), Math.ceil(hi)] : [Math.floor(lo * 10) / 10, Math.ceil(hi * 10) / 10];
}

function setBounds() {
  const rows = state.vesselsRows;
  const yrs = rows.map(r => parseInt(r[FCOL.YEAR], 10)).filter(n => !isNaN(n) && n > 1700 && n < 2100);
  fleetState.bounds = {
    yr: yrs.length ? [Math.min(...yrs), Math.max(...yrs)] : [1900, 2030],
    gt: rangeOf(rows, FCOL.GT, true),
    loa: rangeOf(rows, FCOL.LOA, false),
    w: rangeOf(rows, FCOL.WIDTH, false),
    d: rangeOf(rows, FCOL.DEPTH, false),
  };
  const b = fleetState.bounds;
  // populate inputs with defaults
  setRange("ft-yr", b.yr); setRange("ft-gt", b.gt);
  setRange("ft-loa", b.loa); setRange("ft-w", b.w); setRange("ft-d", b.d);
  // vessel type multiselect
  const typeCounts = {};
  for (const r of rows) {
    const t = r[FCOL.TYPE]; if (!t) continue;
    typeCounts[t] = (typeCounts[t] || 0) + 1;
  }
  const sel = document.getElementById("ft-types");
  sel.innerHTML = "";
  Object.entries(typeCounts).sort((a, b) => b[1] - a[1]).forEach(([t, n]) => {
    const opt = document.createElement("option");
    opt.value = t; opt.textContent = `${t} (${n.toLocaleString()})`;
    sel.appendChild(opt);
  });

  // sector multiselect
  const sectorCounts = {};
  for (const r of rows) {
    const s = r[FCOL.SECTOR]; if (!s) continue;
    sectorCounts[s] = (sectorCounts[s] || 0) + 1;
  }
  const sselFleet = document.getElementById("ft-sectors");
  sselFleet.innerHTML = "";
  Object.entries(sectorCounts).sort((a, b) => b[1] - a[1]).forEach(([s, n]) => {
    const opt = document.createElement("option");
    opt.value = s; opt.textContent = `${s} (${n.toLocaleString()})`;
    sselFleet.appendChild(opt);
  });

  // vessel_class multiselect
  const classCounts = {};
  for (const r of rows) {
    const c = r[FCOL.CLASS]; if (!c) continue;
    classCounts[c] = (classCounts[c] || 0) + 1;
  }
  const cselFleet = document.getElementById("ft-classes");
  cselFleet.innerHTML = "";
  Object.entries(classCounts).sort((a, b) => b[1] - a[1]).forEach(([c, n]) => {
    const opt = document.createElement("option");
    opt.value = c; opt.textContent = `${c} (${n.toLocaleString()})`;
    cselFleet.appendChild(opt);
  });
}

function setRange(prefix, [lo, hi]) {
  document.getElementById(`${prefix}-lo`).value = lo;
  document.getElementById(`${prefix}-hi`).value = hi;
  document.getElementById(`${prefix}-lo`).placeholder = lo;
  document.getElementById(`${prefix}-hi`).placeholder = hi;
}

function readRange(prefix, fallback) {
  const lo = parseFloat(document.getElementById(`${prefix}-lo`).value);
  const hi = parseFloat(document.getElementById(`${prefix}-hi`).value);
  return [isNaN(lo) ? fallback[0] : lo, isNaN(hi) ? fallback[1] : hi];
}

function applyFleetFilters() {
  const b = fleetState.bounds;
  const types = Array.from(document.getElementById("ft-types").selectedOptions).map(o => o.value);
  const sectors = Array.from(document.getElementById("ft-sectors").selectedOptions).map(o => o.value);
  const classes = Array.from(document.getElementById("ft-classes").selectedOptions).map(o => o.value);
  const exclude = document.getElementById("ft-exclude").checked;
  const name = (document.getElementById("ft-name").value || "").toLowerCase().trim();
  const yr = readRange("ft-yr", b.yr);
  const gt = readRange("ft-gt", b.gt);
  const loa = readRange("ft-loa", b.loa);
  const w = readRange("ft-w", b.w);
  const d = readRange("ft-d", b.d);

  const inRange = (v, [lo, hi]) => v == null || v === "" || (Number(v) >= lo && Number(v) <= hi);
  const yrInRange = (v) => {
    const n = parseInt(v, 10); return isNaN(n) || (n >= yr[0] && n <= yr[1]);
  };
  const typeSet = new Set(types);
  const sectorSet = new Set(sectors);
  const classSet = new Set(classes);
  const matchType = types.length === 0 ? () => true
    : (exclude ? r => !typeSet.has(r[FCOL.TYPE]) : r => typeSet.has(r[FCOL.TYPE]));
  // Sector/class follow exclude mode too — keeps the filter UX consistent.
  const matchSector = sectors.length === 0 ? () => true
    : (exclude ? r => !sectorSet.has(r[FCOL.SECTOR]) : r => sectorSet.has(r[FCOL.SECTOR]));
  const matchClass = classes.length === 0 ? () => true
    : (exclude ? r => !classSet.has(r[FCOL.CLASS]) : r => classSet.has(r[FCOL.CLASS]));
  const matchName = name === "" ? () => true : r =>
    (r[FCOL.NAME] || "").toLowerCase().includes(name)
    || (r[FCOL.CALL] || "").toLowerCase().includes(name)
    || (r[FCOL.OWNER] || "").toLowerCase().includes(name)
    || (r[FCOL.IMO]  || "").toLowerCase().includes(name);

  const out = [];
  for (const r of state.vesselsRows) {
    if (!matchType(r)) continue;
    if (!matchSector(r)) continue;
    if (!matchClass(r)) continue;
    if (!yrInRange(r[FCOL.YEAR])) continue;
    if (!inRange(r[FCOL.GT], gt)) continue;
    if (!inRange(r[FCOL.LOA], loa)) continue;
    if (!inRange(r[FCOL.WIDTH], w)) continue;
    if (!inRange(r[FCOL.DEPTH], d)) continue;
    if (!matchName(r)) continue;
    out.push(r);
  }
  fleetState.filtered = out;

  // active filter count
  const active = [
    types.length > 0,
    sectors.length > 0,
    classes.length > 0,
    name !== "",
    yr[0] !== b.yr[0] || yr[1] !== b.yr[1],
    gt[0] !== b.gt[0] || gt[1] !== b.gt[1],
    loa[0] !== b.loa[0] || loa[1] !== b.loa[1],
    w[0] !== b.w[0] || w[1] !== b.w[1],
    d[0] !== b.d[0] || d[1] !== b.d[1],
  ].filter(Boolean).length;
  document.getElementById("fleet-filter-summary").textContent = `필터 ${active}`;
  document.getElementById("ft-yr-val").textContent = `${yr[0]}–${yr[1]}`;
  document.getElementById("ft-gt-val").textContent = `${fmt0(gt[0])}–${fmt0(gt[1])}`;
  document.getElementById("ft-loa-val").textContent = `${fmt1(loa[0])}–${fmt1(loa[1])}`;
  document.getElementById("ft-w-val").textContent = `${fmt1(w[0])}–${fmt1(w[1])}`;
  document.getElementById("ft-d-val").textContent = `${fmt1(d[0])}–${fmt1(d[1])}`;
}

function avgPos(rows, idx) {
  let sum = 0, n = 0;
  for (const r of rows) {
    const v = r[idx];
    if (v == null || v === "") continue;
    const x = Number(v);
    if (!isFinite(x) || x <= 0) continue;
    sum += x; n++;
  }
  return n ? sum / n : 0;
}

function topN(rows, idx, n) {
  const counts = {};
  for (const r of rows) {
    const v = r[idx]; if (!v) continue;
    counts[v] = (counts[v] || 0) + 1;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, n);
}

function renderFleet() {
  const rows = fleetState.filtered;
  const total = state.vesselsRows.length;

  // KPIs
  const types = new Set();
  const sectors = new Set();
  let yrSum = 0, yrN = 0;
  for (const r of rows) {
    if (r[FCOL.TYPE]) types.add(r[FCOL.TYPE]);
    if (r[FCOL.SECTOR]) sectors.add(r[FCOL.SECTOR]);
    const y = parseInt(r[FCOL.YEAR], 10);
    if (!isNaN(y) && y > 1700 && y < 2100) { yrSum += y; yrN++; }
  }
  renderKpis("kpi-fleet", [
    { label: "선박 수", value: fmt(rows.length), sub: `전체 ${fmt(total)}` },
    { label: "Sector / Class", value: `${sectors.size} / ${types.size}`,
      sub: `raw types: ${types.size}` },
    { label: "GT 평균 (>0)", value: fmt0(avgPos(rows, FCOL.GT)),
      sub: `LOA ${fmt1(avgPos(rows, FCOL.LOA))}m · W ${fmt1(avgPos(rows, FCOL.WIDTH))}m · D ${fmt1(avgPos(rows, FCOL.DEPTH))}m` },
    { label: "평균 건조연도", value: yrN ? (yrSum / yrN).toFixed(0) : "—" },
  ]);

  // By Sector — donut, palette-keyed
  const sectorCounts = topN(rows, FCOL.SECTOR, 10);
  Plotly.newPlot("chart-by-sector", [{
    labels: sectorCounts.map(s => s[0]), values: sectorCounts.map(s => s[1]),
    type: "pie", hole: 0.45,
    marker: { colors: sectorCounts.map(s => SECTOR_PALETTE[s[0]] || "#6b7280") },
    textinfo: "label+percent", textposition: "outside",
    hovertemplate: "%{label}<br>%{value:,} (%{percent})<extra></extra>",
  }], { margin: { t: 10, l: 10, r: 10, b: 10 }, showlegend: false },
  { displayModeBar: false, responsive: true });

  // By Vessel Class — horizontal bar, sorted desc, color follows sector
  const classBySector = {};
  for (const r of rows) {
    const c = r[FCOL.CLASS]; if (!c) continue;
    const s = r[FCOL.SECTOR] || "UNMAPPED";
    if (!classBySector[c]) classBySector[c] = { count: 0, sector: s };
    classBySector[c].count++;
  }
  const classRows = Object.entries(classBySector)
    .sort((a, b) => b[1].count - a[1].count)
    .map(([c, v]) => ({ class: c, count: v.count, sector: v.sector }));
  Plotly.newPlot("chart-by-class", [{
    y: classRows.map(c => c.class).reverse(),
    x: classRows.map(c => c.count).reverse(),
    type: "bar", orientation: "h",
    marker: { color: classRows.map(c => SECTOR_PALETTE[c.sector] || "#6b7280").reverse() },
    hovertemplate: "%{y}<br>%{x:,} 척<extra></extra>",
  }], { margin: { t: 10, l: 150, r: 10, b: 30 } },
  { displayModeBar: false, responsive: true });

  // Build year trend
  const yrCounts = {};
  for (const r of rows) {
    const y = parseInt(r[FCOL.YEAR], 10);
    if (isNaN(y) || y < 1700 || y > 2100) continue;
    yrCounts[y] = (yrCounts[y] || 0) + 1;
  }
  const yrKeys = Object.keys(yrCounts).map(Number).sort((a, b) => a - b);
  Plotly.newPlot("chart-build-trend", [{
    x: yrKeys, y: yrKeys.map(y => yrCounts[y]),
    type: "scatter", mode: "lines+markers", fill: "tozeroy",
    line: { color: "#1f77b4" }, marker: { size: 4 },
  }], { margin: { t: 10, l: 40, r: 10, b: 30 }, xaxis: { title: "건조 연도" }, yaxis: { title: "척수" } },
  { displayModeBar: false, responsive: true });

  // Vessel Type TOP 15
  const t15 = topN(rows, FCOL.TYPE, 15).reverse();
  Plotly.newPlot("chart-types", [{
    x: t15.map(t => t[1]), y: t15.map(t => t[0]),
    type: "bar", orientation: "h",
    marker: { color: t15.map(t => t[1]), colorscale: "Blues" },
  }], { margin: { t: 10, l: 200, r: 10, b: 30 } }, { displayModeBar: false, responsive: true });

  // GT histogram (log-bins)
  const bins = [0, 100, 500, 1000, 5000, 10000, 50000, 100000, 1_000_000];
  const labels = bins.slice(0, -1).map((b, i) => `${b.toLocaleString()}–${bins[i+1].toLocaleString()}`);
  const counts = new Array(bins.length - 1).fill(0);
  for (const r of rows) {
    const g = Number(r[FCOL.GT]); if (!(g > 0)) continue;
    for (let i = 0; i < bins.length - 1; i++) {
      if (g >= bins[i] && g < bins[i+1]) { counts[i]++; break; }
    }
  }
  Plotly.newPlot("chart-gt", [{
    x: labels, y: counts, type: "bar",
    marker: { color: "#6c5ce7" },
  }], { margin: { t: 10, l: 40, r: 10, b: 80 }, xaxis: { tickangle: -30 } },
  { displayModeBar: false, responsive: true });

  renderVesselsTable();
}

function renderVesselsTable() {
  const tbody = document.querySelector("#vessels-tbl tbody");
  const rows = fleetState.filtered;
  const { col, dir } = state.vesselsSort;
  const sorted = rows.slice().sort((a, b) => {
    const x = a[col], y = b[col];
    if (x == null || x === "") return 1;
    if (y == null || y === "") return -1;
    if (typeof x === "number" && typeof y === "number") return (x - y) * dir;
    return String(x).localeCompare(String(y)) * dir;
  });
  document.getElementById("vessels-count").textContent =
    `${rows.length.toLocaleString()} / ${state.vesselsRows.length.toLocaleString()} 행 · 표시 ${Math.min(rows.length, 2000).toLocaleString()}`;

  const td = (v, right) => `<td class="px-2 py-1${right ? " text-right" : ""}">${v == null || v === "" ? "" : v}</td>`;
  const num = (v) => v == null || v === "" ? "" : Number(v).toLocaleString();
  const num1 = (v) => v == null || v === "" ? "" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
  const sectorBadge = (s) => {
    if (!s) return "";
    const c = SECTOR_PALETTE[s] || "#6b7280";
    return `<span class="inline-block px-1.5 rounded text-white" style="background:${c}">${s}</span>`;
  };
  tbody.innerHTML = sorted.slice(0, 2000).map(r => `<tr>
    ${td(r[FCOL.CODE])}${td(r[FCOL.NAME])}${td(r[FCOL.CALL])}
    ${td(sectorBadge(r[FCOL.SECTOR]))}${td(r[FCOL.CLASS])}
    ${td(r[FCOL.TYPE])}${td(r[FCOL.OWNER])}${td(r[FCOL.FLAG])}
    ${td(num(r[FCOL.GT]), true)}${td(num1(r[FCOL.LOA]), true)}${td(num1(r[FCOL.WIDTH]), true)}${td(num1(r[FCOL.DEPTH]), true)}
    ${td(r[FCOL.YEAR])}${td(r[FCOL.IMO])}
  </tr>`).join("");
}

function bindFleetControls() {
  if (fleetState.initialized) return;
  fleetState.initialized = true;

  const refresh = () => { applyFleetFilters(); renderFleet(); };
  ["ft-types", "ft-sectors", "ft-classes", "ft-exclude", "ft-name",
   "ft-yr-lo", "ft-yr-hi", "ft-gt-lo", "ft-gt-hi",
   "ft-loa-lo", "ft-loa-hi", "ft-w-lo", "ft-w-hi", "ft-d-lo", "ft-d-hi",
  ].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener("change", refresh);
    if (el.tagName === "INPUT" && (el.type === "text" || el.type === "number")) {
      el.addEventListener("input", refresh);
    }
  });
  document.getElementById("fleet-reset").addEventListener("click", () => {
    ["ft-types", "ft-sectors", "ft-classes"].forEach(id => {
      const el = document.getElementById(id);
      el.selectedIndex = -1;
      Array.from(el.options).forEach(o => o.selected = false);
    });
    document.getElementById("ft-exclude").checked = false;
    document.getElementById("ft-name").value = "";
    setRange("ft-yr", fleetState.bounds.yr);
    setRange("ft-gt", fleetState.bounds.gt);
    setRange("ft-loa", fleetState.bounds.loa);
    setRange("ft-w", fleetState.bounds.w);
    setRange("ft-d", fleetState.bounds.d);
    refresh();
  });
  document.querySelectorAll("#vessels-tbl thead th").forEach(th => {
    th.addEventListener("click", () => {
      const k = parseInt(th.dataset.k, 10);
      state.vesselsSort.dir = (state.vesselsSort.col === k) ? -state.vesselsSort.dir : 1;
      state.vesselsSort.col = k;
      renderVesselsTable();
    });
  });
}

// ---------- Cargo ----------
// Per-kind helpers. Payload schema_version 2 stores _dn/_ln splits on every
// row, so the client can recompute aggregates when the user changes the
// kind filter (all = dn+ln, dn = 국내 only, ln = 국제 only).
const cgState = {
  kind: "all",       // all | dn | ln
  flow: "both",      // both | bongkar | muat
  portSort: { col: "ton_total", dir: -1 },
  komSort: { col: "ton", dir: -1 },
  initialized: false,
};

function pickK(row, base, kind) {
  // Sum dn+ln for "all"; else pick the requested kind. Returns 0 for missing.
  if (kind === "all") return (row[`${base}_dn`] || 0) + (row[`${base}_ln`] || 0);
  return row[`${base}_${kind}`] || 0;
}

function jenisRow(j, kind, flow) {
  const b = pickK(j, "ton_bongkar", kind);
  const m = pickK(j, "ton_muat", kind);
  return {
    jenis: j.jenis,
    ton_bongkar: b,
    ton_muat: m,
    ton_total: (flow === "both") ? (b + m) : (flow === "bongkar" ? b : m),
    calls: pickK(j, "calls", kind),
  };
}

function portRow(p, kind, flow) {
  const b = pickK(p, "ton_bongkar", kind);
  const m = pickK(p, "ton_muat", kind);
  return {
    port: p.port,
    name: p.name || "",
    ton_bongkar: b,
    ton_muat: m,
    ton_total: (flow === "both") ? (b + m) : (flow === "bongkar" ? b : m),
    calls: pickK(p, "calls", kind),
  };
}

function komRow(k, kind) {
  const ton = (kind === "all") ? (k.ton_dn + k.ton_ln) : (kind === "dn" ? k.ton_dn : k.ton_ln);
  return { komoditi: k.komoditi, ton };
}

function monthlyRow(m, kind, flow) {
  const b = pickK(m, "ton_bongkar", kind);
  const mu = pickK(m, "ton_muat", kind);
  return {
    period: m.period,
    ton_bongkar: b,
    ton_muat: mu,
    ton_total: b + mu,
    calls: pickK(m, "calls", kind),
  };
}

function matrixForKind(mat, kind) {
  // Sum element-wise for "all", else pick the requested kind.
  if (!mat || !mat.ton_dn || !mat.ton_ln) return [];
  if (kind === "dn") return mat.ton_dn;
  if (kind === "ln") return mat.ton_ln;
  return mat.ton_dn.map((row, i) => row.map((v, j) => (v || 0) + (mat.ton_ln[i][j] || 0)));
}

function renderCargo() {
  // First-time setup: bind filter controls and table sort handlers.
  if (!cgState.initialized) {
    cgState.initialized = true;
    document.getElementById("cg-kind").addEventListener("change", (e) => {
      cgState.kind = e.target.value; renderCargo();
    });
    document.getElementById("cg-flow").addEventListener("change", (e) => {
      cgState.flow = e.target.value; renderCargo();
    });
    document.getElementById("cg-port-q").addEventListener("input", renderPortTable);
    document.getElementById("cg-kom-q").addEventListener("input", renderKomTable);
    document.querySelectorAll("#cg-port-tbl thead th").forEach(th => {
      th.addEventListener("click", () => {
        const k = th.dataset.k;
        cgState.portSort.dir = (cgState.portSort.col === k) ? -cgState.portSort.dir : -1;
        cgState.portSort.col = k;
        renderPortTable();
      });
    });
    document.querySelectorAll("#cg-kom-tbl thead th").forEach(th => {
      th.addEventListener("click", () => {
        const k = th.dataset.k;
        cgState.komSort.dir = (cgState.komSort.col === k) ? -cgState.komSort.dir : -1;
        cgState.komSort.col = k;
        renderKomTable();
      });
    });
    document.getElementById("cargo-kind").addEventListener("change", renderHeatmap);
  }

  const c = state.cargo;
  const o = state.overview;
  const t = c.totals || {};
  const kind = cgState.kind;
  const flow = cgState.flow;

  // Filter summary
  const kindLabel = { all: "전체", dn: "국내(dn)", ln: "국제(ln)" }[kind];
  const flowLabel = { both: "Bongkar+Muat", bongkar: "Bongkar", muat: "Muat" }[flow];
  document.getElementById("cg-filter-summary").textContent = `${kindLabel} · ${flowLabel}`;

  // KPIs (recomputed from totals/per-kind splits)
  const totBongkar = (kind === "all") ? (t.ton_bongkar_dn + t.ton_bongkar_ln)
                   : (kind === "dn" ? t.ton_bongkar_dn : t.ton_bongkar_ln);
  const totMuat = (kind === "all") ? (t.ton_muat_dn + t.ton_muat_ln)
                : (kind === "dn" ? t.ton_muat_dn : t.ton_muat_ln);
  const totCalls = (kind === "all") ? (t.calls_dn + t.calls_ln)
                 : (kind === "dn" ? t.calls_dn : t.calls_ln);
  const ratio = (totBongkar + totMuat) > 0
    ? (totBongkar / (totBongkar + totMuat) * 100).toFixed(1) : "—";
  renderKpis("kpi-cargo", [
    { label: "LK3 행수 (vessel calls)", value: fmt(totCalls),
      sub: `${fmt(t.ports || o.cargo_ports)} 항구` },
    { label: "Bongkar 총톤수 (하역)", value: fmt0(totBongkar), sub: `${ratio}% of total` },
    { label: "Muat 총톤수 (선적)", value: fmt0(totMuat), sub: `${(100 - parseFloat(ratio)).toFixed(1)}% of total` },
    { label: "(port,year,month,kind) 키 커버리지",
      value: `${(o.cargo_keys / o.cargo_keys_theoretical * 100).toFixed(1)}%`,
      sub: `${fmt(o.cargo_keys)} / ${fmt(o.cargo_keys_theoretical)}` },
  ]);

  // 1) Cargo type (jenis) — re-rank per filter
  const jenis = (c.jenis_top || []).map(j => jenisRow(j, kind, flow))
    .sort((a, b) => b.ton_total - a.ton_total).slice(0, 15);
  const jenisR = jenis.slice().reverse();
  const jenisTraces = [];
  if (flow !== "muat") jenisTraces.push({
    y: jenisR.map(j => j.jenis), x: jenisR.map(j => j.ton_bongkar),
    name: "Bongkar (하역)", type: "bar", orientation: "h",
    marker: { color: "#0ea5e9" },
  });
  if (flow !== "bongkar") jenisTraces.push({
    y: jenisR.map(j => j.jenis), x: jenisR.map(j => j.ton_muat),
    name: "Muat (선적)", type: "bar", orientation: "h",
    marker: { color: "#f97316" },
  });
  Plotly.newPlot("chart-cargo-jenis", jenisTraces,
    { barmode: "stack", margin: { t: 10, l: 200, r: 10, b: 30 },
      xaxis: { title: "ton" }, legend: { orientation: "h", y: -0.1 } },
    { displayModeBar: false, responsive: true });

  // 2) Komoditi TOP 20 — re-rank per kind (flow not applicable; komoditi has no bongkar/muat split)
  const komAll = (c.komoditi_top || []).map(k => komRow(k, kind))
    .sort((a, b) => b.ton - a.ton);
  const k20 = komAll.slice(0, 20).reverse();
  Plotly.newPlot("chart-cargo-komoditi", [{
    y: k20.map(k => k.komoditi), x: k20.map(k => k.ton),
    type: "bar", orientation: "h",
    marker: { color: k20.map(k => k.ton), colorscale: "Viridis" },
    hovertemplate: "%{y}<br>%{x:,.0f} ton<extra></extra>",
  }], { margin: { t: 10, l: 240, r: 10, b: 30 }, xaxis: { title: "ton" } },
  { displayModeBar: false, responsive: true });

  // 3) Top ports — re-rank per filter
  const portsAll = (c.port_top || []).map(p => portRow(p, kind, flow))
    .sort((a, b) => b.ton_total - a.ton_total);
  const p20 = portsAll.slice(0, 20);
  const labels = p20.map(p => p.name ? `${p.port} ${p.name.slice(0, 14)}` : p.port);
  const portTraces = [];
  if (flow !== "muat") portTraces.push({
    x: labels, y: p20.map(p => p.ton_bongkar), name: "Bongkar", type: "bar",
    marker: { color: "#0ea5e9" },
  });
  if (flow !== "bongkar") portTraces.push({
    x: labels, y: p20.map(p => p.ton_muat), name: "Muat", type: "bar",
    marker: { color: "#f97316" },
  });
  Plotly.newPlot("chart-cargo-ports", portTraces,
    { barmode: "stack", margin: { t: 10, l: 60, r: 10, b: 110 },
      xaxis: { tickangle: -50, automargin: true }, yaxis: { title: "ton" },
      legend: { orientation: "h", y: -0.25 } },
    { displayModeBar: false, responsive: true });

  // 4) Monthly trend
  const mt = (c.monthly_ton || []).map(m => monthlyRow(m, kind, flow));
  const monthlyTraces = [];
  if (flow !== "muat") monthlyTraces.push({
    x: mt.map(m => m.period), y: mt.map(m => m.ton_bongkar),
    name: "Bongkar", type: "scatter", mode: "lines+markers",
    line: { color: "#0ea5e9" },
  });
  if (flow !== "bongkar") monthlyTraces.push({
    x: mt.map(m => m.period), y: mt.map(m => m.ton_muat),
    name: "Muat", type: "scatter", mode: "lines+markers",
    line: { color: "#f97316" },
  });
  Plotly.newPlot("chart-cargo-monthly", monthlyTraces,
    { margin: { t: 10, l: 60, r: 10, b: 60 },
      xaxis: { tickangle: -40 }, yaxis: { title: "ton" },
      legend: { orientation: "h", y: -0.2 } },
    { displayModeBar: false, responsive: true });

  // 5) Port × jenis heatmap
  const mat = c.port_jenis_matrix || {};
  const z = matrixForKind(mat, kind);
  const portLabels = (mat.ports || []).map((p, i) =>
    mat.port_names && mat.port_names[i] ? `${p} ${mat.port_names[i].slice(0, 16)}` : p);
  Plotly.newPlot("chart-cargo-matrix", [{
    z, x: mat.jenis || [], y: portLabels, type: "heatmap",
    colorscale: "Blues", hoverongaps: false,
    hovertemplate: "%{y}<br>%{x}<br>%{z:,.0f} ton<extra></extra>",
  }], { margin: { t: 10, l: 220, r: 10, b: 110 }, xaxis: { tickangle: -30 } },
  { displayModeBar: false, responsive: true });

  // Cache filtered base lists for tables, then render
  cgState.portsAll = portsAll;
  cgState.komAll = komAll;
  renderPortTable();
  renderKomTable();

  renderHeatmap();
  renderCargoGaps();

  // By Vessel Sector / Class / Tanker subclass — lit by cargo_sector_monthly.json
  renderCargoSectorViews();
}

function _filterRowsByKind(rows, kind) {
  return kind === "all" ? rows : rows.filter(r => r.kind === kind);
}

function renderCargoSectorViews() {
  const sm = state.sectorMonthly;
  if (!sm) return;
  const kind = cgState.kind;
  const flow = cgState.flow;

  const tonOf = (r) => flow === "both" ? r.ton_total
                    : (flow === "bongkar" ? r.ton_bongkar : r.ton_muat);

  // 1) By Vessel Sector — donut over selected kind+flow
  const sectorTotals = {};
  for (const r of _filterRowsByKind(sm.rows, kind)) {
    sectorTotals[r.sector] = (sectorTotals[r.sector] || 0) + tonOf(r);
  }
  const sectorList = Object.entries(sectorTotals).sort((a, b) => b[1] - a[1]);
  Plotly.newPlot("chart-cargo-by-sector", [{
    labels: sectorList.map(s => s[0]), values: sectorList.map(s => s[1]),
    type: "pie", hole: 0.45,
    marker: { colors: sectorList.map(s => SECTOR_PALETTE[s[0]] || "#6b7280") },
    textinfo: "label+percent", textposition: "outside",
    hovertemplate: "%{label}<br>%{value:,.0f} ton (%{percent})<extra></extra>",
  }], { margin: { t: 10, l: 10, r: 10, b: 10 }, showlegend: false },
  { displayModeBar: false, responsive: true });

  // 2) By Vessel Class — bar (Cargo sector only, since other sectors don't haul much ton)
  const classTotals = {};
  for (const r of _filterRowsByKind(sm.rows, kind)) {
    if (r.sector !== "CARGO") continue;
    classTotals[r.vessel_class] = (classTotals[r.vessel_class] || 0) + tonOf(r);
  }
  const classList = Object.entries(classTotals).sort((a, b) => b[1] - a[1]);
  Plotly.newPlot("chart-cargo-by-class", [{
    y: classList.map(c => c[0]).reverse(),
    x: classList.map(c => c[1]).reverse(),
    type: "bar", orientation: "h",
    marker: { color: "#1e3a8a" },
    hovertemplate: "%{y}<br>%{x:,.0f} ton<extra></extra>",
  }], { margin: { t: 10, l: 130, r: 10, b: 30 } },
  { displayModeBar: false, responsive: true });

  // 3) Tanker subclass breakdown
  const tankerTotals = {};
  const tRows = _filterRowsByKind(sm.tanker_subclass_rows || [], kind);
  for (const r of tRows) {
    tankerTotals[r.subclass] = (tankerTotals[r.subclass] || 0) + tonOf(r);
  }
  const tList = Object.entries(tankerTotals).sort((a, b) => b[1] - a[1]);
  Plotly.newPlot("chart-cargo-tanker", [{
    x: tList.map(t => t[0]), y: tList.map(t => t[1]),
    type: "bar",
    marker: { color: "#7c3aed" },
    hovertemplate: "%{x}<br>%{y:,.0f} ton<extra></extra>",
  }], { margin: { t: 10, l: 60, r: 10, b: 50 }, yaxis: { title: "ton" } },
  { displayModeBar: false, responsive: true });
}

// ---------- Trends tab ----------
const trState = { kind: "all", mode: "abs", initialized: false };

function renderTrends() {
  const sm = state.sectorMonthly;
  if (!sm) return;

  if (!trState.initialized) {
    trState.initialized = true;
    document.getElementById("tr-kind").addEventListener("change", (e) => {
      trState.kind = e.target.value; renderTrends();
    });
    document.getElementById("tr-mode").addEventListener("change", (e) => {
      trState.mode = e.target.value; renderTrends();
    });
  }

  const kind = trState.kind;
  const mode = trState.mode;
  const rows = _filterRowsByKind(sm.rows, kind);
  const periods = Array.from(new Set(rows.map(r => r.period))).sort();

  // 1) Sector stacked area, optionally MoM%
  const sectorList = Array.from(new Set(rows.map(r => r.sector)));
  const sectorSeries = {};
  for (const s of sectorList) {
    sectorSeries[s] = periods.map(p => {
      let sum = 0;
      for (const r of rows) {
        if (r.sector === s && r.period === p) sum += r.ton_total;
      }
      return sum;
    });
  }
  let traces;
  if (mode === "mom") {
    traces = sectorList.map(s => {
      const y = sectorSeries[s].map((v, i, a) =>
        i === 0 || a[i - 1] === 0 ? null : ((v - a[i - 1]) / a[i - 1] * 100));
      return {
        x: periods, y, name: s, type: "scatter", mode: "lines+markers",
        line: { color: SECTOR_PALETTE[s] || "#6b7280" },
      };
    });
  } else {
    traces = sectorList.map(s => ({
      x: periods, y: sectorSeries[s], name: s,
      type: "scatter", stackgroup: "one", mode: "none",
      fillcolor: SECTOR_PALETTE[s] || "#6b7280",
    }));
  }
  Plotly.newPlot("chart-trends-sector-stack", traces,
    { margin: { t: 10, l: 60, r: 10, b: 60 }, xaxis: { tickangle: -40 },
      yaxis: { title: mode === "mom" ? "%" : "ton" },
      legend: { orientation: "h", y: -0.2 } },
    { displayModeBar: false, responsive: true });

  // 2) Per-class trend (Cargo sector only, lines)
  const cargoRows = rows.filter(r => r.sector === "CARGO");
  const classList = Array.from(new Set(cargoRows.map(r => r.vessel_class)));
  const classTraces = classList.map(cls => ({
    x: periods,
    y: periods.map(p => {
      let sum = 0;
      for (const r of cargoRows) {
        if (r.vessel_class === cls && r.period === p) sum += r.ton_total;
      }
      return sum;
    }),
    name: cls, type: "scatter", mode: "lines+markers",
  }));
  Plotly.newPlot("chart-trends-class", classTraces,
    { margin: { t: 10, l: 60, r: 10, b: 60 }, xaxis: { tickangle: -40 },
      yaxis: { title: "ton" }, legend: { orientation: "h", y: -0.25 } },
    { displayModeBar: false, responsive: true });

  // 3) Sector calls trend (volume of vessel calls across months)
  const callsTraces = sectorList.map(s => ({
    x: periods,
    y: periods.map(p => {
      let sum = 0;
      for (const r of rows) {
        if (r.sector === s && r.period === p) sum += r.calls;
      }
      return sum;
    }),
    name: s, type: "scatter", mode: "lines+markers",
    line: { color: SECTOR_PALETTE[s] || "#6b7280" },
  }));
  Plotly.newPlot("chart-trends-calls", callsTraces,
    { margin: { t: 10, l: 60, r: 10, b: 60 }, xaxis: { tickangle: -40 },
      yaxis: { title: "calls" }, legend: { orientation: "h", y: -0.25 } },
    { displayModeBar: false, responsive: true });
}

function renderPortTable() {
  const rows = cgState.portsAll || [];
  const q = (document.getElementById("cg-port-q").value || "").toLowerCase().trim();
  const filtered = q ? rows.filter(r =>
    (r.port || "").toLowerCase().includes(q) || (r.name || "").toLowerCase().includes(q)) : rows;
  const { col, dir } = cgState.portSort;
  const sorted = filtered.slice().sort((a, b) => {
    const x = a[col], y = b[col];
    if (typeof x === "number" && typeof y === "number") return (x - y) * dir;
    return String(x).localeCompare(String(y)) * dir;
  });
  document.getElementById("cg-port-count").textContent =
    `${filtered.length.toLocaleString()} / ${rows.length.toLocaleString()} 항구`;
  const tbody = document.querySelector("#cg-port-tbl tbody");
  const num = (v) => v == null ? "" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  tbody.innerHTML = sorted.slice(0, 1000).map(r => `<tr>
    <td class="px-2 py-1 font-mono">${r.port}</td>
    <td class="px-2 py-1">${r.name || ""}</td>
    <td class="px-2 py-1 text-right">${num(r.ton_bongkar)}</td>
    <td class="px-2 py-1 text-right">${num(r.ton_muat)}</td>
    <td class="px-2 py-1 text-right font-semibold">${num(r.ton_total)}</td>
    <td class="px-2 py-1 text-right">${num(r.calls)}</td>
  </tr>`).join("");
}

function renderKomTable() {
  const rows = cgState.komAll || [];
  const q = (document.getElementById("cg-kom-q").value || "").toLowerCase().trim();
  const filtered = q ? rows.filter(r => (r.komoditi || "").toLowerCase().includes(q)) : rows;
  const { col, dir } = cgState.komSort;
  const sorted = filtered.slice().sort((a, b) => {
    const x = a[col], y = b[col];
    if (typeof x === "number" && typeof y === "number") return (x - y) * dir;
    return String(x).localeCompare(String(y)) * dir;
  });
  document.getElementById("cg-kom-count").textContent =
    `${filtered.length.toLocaleString()} / ${rows.length.toLocaleString()} 품목`;
  const tbody = document.querySelector("#cg-kom-tbl tbody");
  const num = (v) => v == null ? "" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  tbody.innerHTML = sorted.slice(0, 500).map(r => `<tr>
    <td class="px-2 py-1">${r.komoditi}</td>
    <td class="px-2 py-1 text-right">${num(r.ton)}</td>
  </tr>`).join("");
}

function renderHeatmap() {
  const c = state.cargo;
  const kind = document.getElementById("cargo-kind").value;
  const filtered = c.traffic.filter(t => t.kind === kind);
  const portTotals = {};
  filtered.forEach(t => { portTotals[t.port] = (portTotals[t.port] || 0) + t.rows; });
  const topPorts = Object.entries(portTotals).sort((a, b) => b[1] - a[1]).slice(0, 40).map(([p]) => p);
  const periods = Array.from(new Set(filtered.map(t => t.period))).sort();
  const z = topPorts.map(p => periods.map(per => {
    const r = filtered.find(t => t.port === p && t.period === per);
    return r ? r.rows : 0;
  }));
  const portLabels = topPorts.map(p => c.ports[p] ? `${p} ${c.ports[p].slice(0, 16)}` : p);
  Plotly.newPlot("chart-heatmap", [{
    z, x: periods, y: portLabels, type: "heatmap", colorscale: "Blues",
    hoverongaps: false, hovertemplate: "%{y}<br>%{x}<br>rows %{z}<extra></extra>",
  }], { margin: { t: 10, l: 200, r: 10, b: 90 }, xaxis: { tickangle: -45 } },
  { displayModeBar: false, responsive: true });
}

function renderCargoGaps() {
  const c = state.cargo;
  const have = new Set(c.traffic.map(t => `${t.port}|${t.period}|${t.kind}`));
  const ports = Object.keys(c.ports);
  const periods = Array.from(new Set(c.traffic.map(t => t.period))).sort();
  const kinds = ["dn", "ln"];
  const missing = [];
  for (const p of ports) {
    for (const per of periods) {
      for (const k of kinds) {
        if (!have.has(`${p}|${per}|${k}`)) missing.push({ port: p, name: c.ports[p] || "", period: per, kind: k });
      }
    }
  }
  document.getElementById("cargo-gap-summary").textContent =
    `누락 ${missing.length.toLocaleString()} 키 (port ${ports.length} × period ${periods.length} × kind 2 = ${ports.length * periods.length * 2}, 보유 ${c.traffic.length.toLocaleString()})`;
  const tbody = document.querySelector("#gap-tbl tbody");
  tbody.innerHTML = missing.slice(0, 2000).map(r =>
    `<tr><td class="px-2 py-1">${r.port}</td><td class="px-2 py-1">${r.name}</td>
     <td class="px-2 py-1">${r.period}</td><td class="px-2 py-1">${r.kind}</td></tr>`).join("");
}

// ---------- Changes ----------
function renderChanges() {
  if (!state.changes) {
    document.getElementById("kpi-changes2").innerHTML =
      `<div class="col-span-full text-center text-slate-400 py-12">변경 탐지 결과가 없습니다 (baseline).</div>`;
    return;
  }
  const k = state.changes;
  const v = k.vessel_kpi || {}; const c = k.cargo_kpi || {};
  renderKpis("kpi-changes2", [
    { label: "선박 ADDED", value: fmt(v.ADDED || 0) },
    { label: "선박 REMOVED", value: fmt(v.REMOVED || 0) },
    { label: "선박 MODIFIED 셀", value: fmt(v.MODIFIED || 0) },
    { label: "Cargo ADDED 키", value: fmt(c.ADDED || 0) },
    { label: "Cargo REMOVED 키", value: fmt(c.REMOVED || 0) },
    { label: "Cargo REVISED 셀", value: fmt(c.REVISED || 0) },
  ]);
  // vessel_modified_fields
  const fields = Object.entries(k.vessel_modified_fields || {}).sort((a, b) => b[1] - a[1]);
  Plotly.newPlot("chart-vessel-fields", [{
    x: fields.map(f => f[0]), y: fields.map(f => f[1]), type: "bar",
    marker: { color: "#dc2626" },
  }], { margin: { t: 10, l: 40, r: 10, b: 80 }, xaxis: { tickangle: -30 } },
  { displayModeBar: false, responsive: true });

  Plotly.newPlot("chart-cargo-types", [{
    x: Object.keys(c), y: Object.values(c), type: "bar",
    marker: { color: "#0d9488" },
  }], { margin: { t: 10, l: 40, r: 10, b: 40 } }, { displayModeBar: false, responsive: true });

  renderVcTable(); renderCcTable();
  document.getElementById("vc-type").addEventListener("change", renderVcTable);
  document.getElementById("vc-q").addEventListener("input", renderVcTable);
  document.getElementById("cc-type").addEventListener("change", renderCcTable);
  document.getElementById("cc-kind").addEventListener("change", renderCcTable);
  document.getElementById("cc-q").addEventListener("input", renderCcTable);
}

function renderVcTable() {
  const t = document.getElementById("vc-type").value;
  const q = (document.getElementById("vc-q").value || "").toLowerCase();
  let rows = state.changes.vessel_samples;
  if (t) rows = rows.filter(r => r.type === t);
  if (q) rows = rows.filter(r => (r.vessel_key || "").toLowerCase().includes(q)
                              || (r.field || "").toLowerCase().includes(q)
                              || (r.old || "").toString().toLowerCase().includes(q)
                              || (r.new || "").toString().toLowerCase().includes(q));
  document.getElementById("vc-count").textContent = `${rows.length.toLocaleString()} rows`;
  const tbody = document.querySelector("#vc-tbl tbody");
  tbody.innerHTML = rows.slice(0, 2000).map(r => `<tr>
    <td class="px-2 py-1">${r.type}</td>
    <td class="px-2 py-1">${r.vessel_key || ""}</td>
    <td class="px-2 py-1">${r.field || ""}</td>
    <td class="px-2 py-1">${r.old == null ? "" : String(r.old).slice(0, 80)}</td>
    <td class="px-2 py-1">${r.new == null ? "" : String(r.new).slice(0, 80)}</td>
  </tr>`).join("");
}

function renderCcTable() {
  const t = document.getElementById("cc-type").value;
  const k = document.getElementById("cc-kind").value;
  const q = (document.getElementById("cc-q").value || "").toLowerCase();
  let rows = state.changes.cargo_samples;
  if (t) rows = rows.filter(r => r.type === t);
  if (k) rows = rows.filter(r => r.kind === k);
  if (q) rows = rows.filter(r => (r.port || "").toLowerCase().includes(q)
                              || (r.field || "").toLowerCase().includes(q));
  document.getElementById("cc-count").textContent = `${rows.length.toLocaleString()} rows`;
  const tbody = document.querySelector("#cc-tbl tbody");
  tbody.innerHTML = rows.slice(0, 2000).map(r => `<tr>
    <td class="px-2 py-1">${r.type}</td>
    <td class="px-2 py-1">${r.port}</td>
    <td class="px-2 py-1">${r.year}</td>
    <td class="px-2 py-1">${r.month}</td>
    <td class="px-2 py-1">${r.kind}</td>
    <td class="px-2 py-1">${r.field || ""}</td>
    <td class="px-2 py-1">${r.old == null ? "" : String(r.old).slice(0, 60)}</td>
    <td class="px-2 py-1">${r.new == null ? "" : String(r.new).slice(0, 60)}</td>
    <td class="px-2 py-1 text-right">${r.delta == null ? "" : fmt1(r.delta)}</td>
    <td class="px-2 py-1 text-right">${r.delta_pct == null ? "" : fmt1(r.delta_pct) + "%"}</td>
  </tr>`).join("");
}

// ---------- Sector Delta (Changes tab) ----------
const sdState = { kind: "all", threshold: 15, initialized: false };

function renderSectorDelta() {
  const sm = state.sectorMonthly;
  if (!sm) {
    document.getElementById("sd-summary").textContent =
      "cargo_sector_monthly.json 미로드 (이전 빌드 데이터)";
    return;
  }

  if (!sdState.initialized) {
    sdState.initialized = true;
    document.getElementById("sd-kind").addEventListener("change", (e) => {
      sdState.kind = e.target.value; renderSectorDelta();
    });
    document.getElementById("sd-threshold").addEventListener("change", (e) => {
      const v = parseFloat(e.target.value);
      sdState.threshold = isNaN(v) ? 15 : v;
      renderSectorDelta();
    });
  }

  const kind = sdState.kind;
  const rows = kind === "all" ? sm.rows : sm.rows.filter(r => r.kind === kind);

  // Build (sector, period) → ton matrix.
  const sectors = Array.from(new Set(rows.map(r => r.sector)));
  const periods = Array.from(new Set(rows.map(r => r.period))).sort();
  const tonGrid = {};   // sector -> {period -> ton}
  for (const s of sectors) tonGrid[s] = {};
  for (const r of rows) {
    tonGrid[r.sector][r.period] = (tonGrid[r.sector][r.period] || 0) + r.ton_total;
  }

  // MoM% per (sector, period).
  const momGrid = sectors.map(s => periods.map((p, i) => {
    if (i === 0) return null;
    const prev = tonGrid[s][periods[i - 1]] || 0;
    const curr = tonGrid[s][p] || 0;
    if (!prev) return null;
    return (curr - prev) / prev * 100;
  }));

  Plotly.newPlot("chart-sd-heatmap", [{
    z: momGrid, x: periods, y: sectors, type: "heatmap",
    colorscale: [[0, "#dc2626"], [0.5, "#f1f5f9"], [1, "#1e3a8a"]],
    zmid: 0, hoverongaps: false,
    hovertemplate: "%{y}<br>%{x}<br>MoM %{z:.1f}%<extra></extra>",
  }], { margin: { t: 10, l: 140, r: 10, b: 60 }, xaxis: { tickangle: -40 } },
  { displayModeBar: false, responsive: true });

  // Top Movers — for the latest period vs the previous one, by absolute Δ ton.
  // Compute (sector, vessel_class) granularity for movers.
  if (periods.length < 2) {
    document.querySelector("#sd-movers-tbl tbody").innerHTML =
      `<tr><td colspan="6" class="text-center text-slate-400 py-2">period가 부족합니다.</td></tr>`;
    document.querySelector("#sd-alerts-tbl tbody").innerHTML =
      `<tr><td colspan="6" class="text-center text-slate-400 py-2">period가 부족합니다.</td></tr>`;
    return;
  }
  const latest = periods[periods.length - 1];
  const prev = periods[periods.length - 2];
  const cellGrid = {}; // key "sector|class" -> {prev, curr}
  for (const r of rows) {
    const k = `${r.sector}|${r.vessel_class}`;
    if (!cellGrid[k]) cellGrid[k] = { sector: r.sector, vc: r.vessel_class, prev: 0, curr: 0 };
    if (r.period === prev) cellGrid[k].prev += r.ton_total;
    else if (r.period === latest) cellGrid[k].curr += r.ton_total;
  }
  const movers = Object.values(cellGrid)
    .map(c => ({
      ...c,
      delta: c.curr - c.prev,
      momPct: c.prev ? (c.curr - c.prev) / c.prev * 100 : (c.curr ? Infinity : null),
    }))
    .filter(c => c.momPct !== null && (c.prev > 0 || c.curr > 0))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .slice(0, 20);

  const num = (v) => v == null ? "" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  const pct = (v) => v == null ? "" : (Number.isFinite(v) ? `${v >= 0 ? "+" : ""}${v.toFixed(1)}%` : "+∞");
  const cellColor = (v) => {
    if (v == null || !Number.isFinite(v)) return "";
    if (v > sdState.threshold) return "background:#dbeafe";
    if (v < -sdState.threshold) return "background:#fee2e2";
    return "";
  };
  document.querySelector("#sd-movers-tbl tbody").innerHTML = movers.map(m => `<tr>
    <td class="px-2 py-1">${m.sector}</td>
    <td class="px-2 py-1">${m.vc}</td>
    <td class="px-2 py-1 text-right">${num(m.prev)}</td>
    <td class="px-2 py-1 text-right">${num(m.curr)}</td>
    <td class="px-2 py-1 text-right ${m.delta < 0 ? 'text-red-600' : 'text-blue-700'}">${num(m.delta)}</td>
    <td class="px-2 py-1 text-right" style="${cellColor(m.momPct)}">${pct(m.momPct)}</td>
  </tr>`).join("");

  // Alerts — every (sector, class, period) with |MoM%| > threshold across all
  // periods (not just the latest). Sorted by abs MoM desc.
  const alertRows = [];
  for (const r of rows) {
    const k = `${r.sector}|${r.vessel_class}`;
    // need previous period's value in the same kind
  }
  // To compute alerts cleanly, build a (sector, class) -> period -> ton index.
  const idx = {};
  for (const r of rows) {
    const k = `${r.sector}|${r.vessel_class}`;
    if (!idx[k]) idx[k] = { sector: r.sector, vc: r.vessel_class, byPeriod: {} };
    idx[k].byPeriod[r.period] = (idx[k].byPeriod[r.period] || 0) + r.ton_total;
  }
  for (const cell of Object.values(idx)) {
    for (let i = 1; i < periods.length; i++) {
      const p = periods[i], pp = periods[i - 1];
      const cur = cell.byPeriod[p] || 0;
      const pre = cell.byPeriod[pp] || 0;
      if (!pre) continue;
      const m = (cur - pre) / pre * 100;
      if (Math.abs(m) > sdState.threshold) {
        alertRows.push({ sector: cell.sector, vc: cell.vc, period: p, prev: pre, curr: cur, momPct: m });
      }
    }
  }
  alertRows.sort((a, b) => Math.abs(b.momPct) - Math.abs(a.momPct));
  document.getElementById("sd-alerts-sub").textContent =
    `${alertRows.length.toLocaleString()} 건 (|Δ| > ${sdState.threshold}%, ${rows.length.toLocaleString()}개 셀 검사)`;
  document.querySelector("#sd-alerts-tbl tbody").innerHTML = alertRows.slice(0, 500).map(a => `<tr>
    <td class="px-2 py-1">${a.sector}</td>
    <td class="px-2 py-1">${a.vc}</td>
    <td class="px-2 py-1">${a.period}</td>
    <td class="px-2 py-1 text-right">${num(a.prev)}</td>
    <td class="px-2 py-1 text-right">${num(a.curr)}</td>
    <td class="px-2 py-1 text-right ${a.momPct < 0 ? 'text-red-600' : 'text-blue-700'}">${pct(a.momPct)}</td>
  </tr>`).join("");

  document.getElementById("sd-summary").textContent =
    `${sectors.length} sector × ${periods.length} 월 (${kind === "all" ? "전체" : kind})`;
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
  document.getElementById(`tab-${name}`).classList.remove("hidden");
  ensureLoaded(name);
}

async function ensureLoaded(tab) {
  try {
    if (tab === "fleet" && !state.loaded.has("fleet")) {
      if (!state.vessels) {
        state.vessels = await loadJson("vessels_search.json");
        state.vesselsRows = state.vessels.items;
      }
      setBounds();
      bindFleetControls();
      applyFleetFilters();
      renderFleet();
      state.loaded.add("fleet");
    }
    if (tab === "cargo" && !state.loaded.has("cargo")) {
      if (!state.cargo) state.cargo = await loadJson("cargo.json");
      if (!state.sectorMonthly) {
        try { state.sectorMonthly = await loadJson("cargo_sector_monthly.json"); }
        catch (e) { state.sectorMonthly = null; }
      }
      renderCargo();
      state.loaded.add("cargo");
    }
    if (tab === "trends" && !state.loaded.has("trends")) {
      if (!state.sectorMonthly) {
        state.sectorMonthly = await loadJson("cargo_sector_monthly.json");
      }
      renderTrends();
      state.loaded.add("trends");
    }
    if (tab === "financials" && !state.loaded.has("financials")) {
      if (!state.financials) {
        try { state.financials = await loadJson("companies_financials.json"); }
        catch (e) { state.financials = null; }
      }
      renderFinancials();
      state.loaded.add("financials");
    }
    if (tab === "changes" && !state.loaded.has("changes")) {
      if (!state.changes) state.changes = await loadJson("changes.json");
      if (!state.sectorMonthly) {
        try { state.sectorMonthly = await loadJson("cargo_sector_monthly.json"); }
        catch (e) { state.sectorMonthly = null; }
      }
      renderChanges();
      renderSectorDelta();
      state.loaded.add("changes");
    }
  } catch (e) {
    console.error(e);
  }
}

// ---------- Boot ----------
async function boot() {
  state.meta = await loadJson("meta.json");
  state.overview = await loadJson("overview.json");
  // changes might or might not exist; load eagerly so overview KPIs work
  try { state.changes = await loadJson("changes.json"); } catch (e) { state.changes = null; }
  // kpi_summary + taxonomy are post-PR2 additions; degrade gracefully
  // when older deployments don't have them yet.
  try { state.kpi = await loadJson("kpi_summary.json"); } catch (e) { state.kpi = null; }
  try { state.taxonomy = await loadJson("sector_taxonomy.json"); } catch (e) { state.taxonomy = null; }
  renderOverview();
  document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));
  showTab("overview");
}

boot().catch(e => {
  console.error(e);
  document.body.insertAdjacentHTML("afterbegin",
    `<div class="bg-red-100 text-red-800 p-4">데이터 로드 실패: ${e.message}</div>`);
});
