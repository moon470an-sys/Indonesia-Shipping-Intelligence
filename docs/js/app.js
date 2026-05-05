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
function renderOverview() {
  const o = state.overview;
  const k = state.changes;
  document.getElementById("meta-line").textContent =
    `snapshot ${o.snapshot_month} · change month ${k ? k.change_month : "(없음)"} · ${state.meta.vessel_months.length} snapshots`;
  document.getElementById("generated-at").textContent = state.meta.generated_at || "—";
  document.getElementById("about-meta").textContent =
    `Snapshots: ${state.meta.vessel_months.length} (vessel) / ${state.meta.cargo_months.length} (cargo) — generated ${state.meta.generated_at}`;

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
function renderFleet() {
  const f = state.fleet;
  const o = state.overview;
  renderKpis("kpi-fleet", [
    { label: "선박 등록", value: fmt(o.vessel_total) },
    { label: "검색 코드", value: `${o.vessel_codes}/56` },
    { label: "평균 GT", value: fmt0(o.vessel_avg_gt) },
    { label: "최대 GT", value: fmt0(o.vessel_max_gt) },
  ]);

  // Types
  const types = f.types.slice(0, 30).reverse();
  Plotly.newPlot("chart-types", [{
    x: types.map(t => t.count), y: types.map(t => t.type), type: "bar", orientation: "h",
    marker: { color: "#0d9488" },
    hovertemplate: "%{y}<br>척수 %{x:,}<br>평균 GT %{customdata[0]:,.0f}<extra></extra>",
    customdata: types.map(t => [t.avg_gt, t.sum_gt]),
  }], { margin: { t: 10, l: 240, r: 10, b: 30 } }, { displayModeBar: false, responsive: true });

  // Ages
  Plotly.newPlot("chart-ages", [{
    x: f.ages.map(a => a.year), y: f.ages.map(a => a.count), type: "bar",
    marker: { color: "#6366f1" },
  }], { margin: { t: 10, l: 40, r: 10, b: 40 } }, { displayModeBar: false, responsive: true });

  // GT histogram
  Plotly.newPlot("chart-gt", [{
    x: f.gt_histogram.bins, y: f.gt_histogram.counts, type: "bar",
    marker: { color: "#a855f7" },
  }], { margin: { t: 10, l: 40, r: 10, b: 60 }, xaxis: { tickangle: -30 } },
  { displayModeBar: false, responsive: true });

  // Owners
  const owners = f.owners.slice(0, 50).reverse();
  Plotly.newPlot("chart-owners", [{
    x: owners.map(o => o.fleet), y: owners.map(o => o.owner), type: "bar", orientation: "h",
    marker: { color: "#0369a1" },
    hovertemplate: "%{y}<br>척수 %{x}<br>총 GT %{customdata[0]:,.0f}<extra></extra>",
    customdata: owners.map(o => [o.sum_gt]),
  }], { margin: { t: 10, l: 280, r: 10, b: 30 } }, { displayModeBar: false, responsive: true });

  // Type / code dropdowns
  const typeSel = document.getElementById("vessels-type");
  if (typeSel.options.length === 1) {
    f.types.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.type; opt.textContent = `${t.type} (${t.count})`;
      typeSel.appendChild(opt);
    });
  }
  const codeSel = document.getElementById("vessels-code");
  if (codeSel.options.length === 1) {
    f.codes.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.code; opt.textContent = `${c.code} (${c.count})`;
      codeSel.appendChild(opt);
    });
  }
}

function renderVesselsTable() {
  const tbody = document.querySelector("#vessels-tbl tbody");
  const q = (document.getElementById("vessels-q").value || "").toLowerCase();
  const tp = document.getElementById("vessels-type").value;
  const cd = document.getElementById("vessels-code").value;

  let rows = state.vesselsRows;
  if (q) rows = rows.filter(r => (r[2] || "").toLowerCase().includes(q)
                              || (r[3] || "").toLowerCase().includes(q)
                              || (r[5] || "").toLowerCase().includes(q)
                              || (r[8] || "").toLowerCase().includes(q));
  if (tp) rows = rows.filter(r => r[4] === tp);
  if (cd) rows = rows.filter(r => r[1] === cd);

  const { col, dir } = state.vesselsSort;
  rows = rows.slice().sort((a, b) => {
    const x = a[col], y = b[col];
    if (x == null) return 1; if (y == null) return -1;
    if (typeof x === "number" && typeof y === "number") return (x - y) * dir;
    return String(x).localeCompare(String(y)) * dir;
  });

  document.getElementById("vessels-count").textContent =
    `${rows.length.toLocaleString()} rows (전체 ${state.vesselsRows.length.toLocaleString()})`;

  const limit = 2000;
  const html = rows.slice(0, limit).map(r => `<tr>
    <td class="px-2 py-1">${r[0] || ""}</td>
    <td class="px-2 py-1">${r[1] || ""}</td>
    <td class="px-2 py-1">${r[2] || ""}</td>
    <td class="px-2 py-1">${r[3] || ""}</td>
    <td class="px-2 py-1">${r[4] || ""}</td>
    <td class="px-2 py-1">${r[5] || ""}</td>
    <td class="px-2 py-1 text-right">${r[6] == null ? "" : Number(r[6]).toLocaleString()}</td>
    <td class="px-2 py-1">${r[7] || ""}</td>
    <td class="px-2 py-1">${r[8] || ""}</td>
  </tr>`).join("");
  tbody.innerHTML = html;
}

function bindVesselsControls() {
  document.getElementById("vessels-q").addEventListener("input", renderVesselsTable);
  document.getElementById("vessels-type").addEventListener("change", renderVesselsTable);
  document.getElementById("vessels-code").addEventListener("change", renderVesselsTable);
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
function renderCargo() {
  const c = state.cargo;
  const o = state.overview;
  renderKpis("kpi-cargo", [
    { label: "물동량 행", value: fmt(o.cargo_rows) },
    { label: "항구", value: fmt(o.cargo_ports) },
    { label: "(port,year,month,kind) 키", value: `${fmt(o.cargo_keys)} / ${fmt(o.cargo_keys_theoretical)}` },
    { label: "커버리지", value: `${(o.cargo_keys / o.cargo_keys_theoretical * 100).toFixed(1)}%` },
  ]);

  // top ports stacked dn/ln
  const portTotals = {};
  c.traffic.forEach(t => {
    if (!portTotals[t.port]) portTotals[t.port] = { dn: 0, ln: 0 };
    portTotals[t.port][t.kind] += t.rows;
  });
  const tops = Object.entries(portTotals)
    .map(([p, v]) => ({ port: p, dn: v.dn, ln: v.ln, total: v.dn + v.ln }))
    .sort((a, b) => b.total - a.total).slice(0, 25);
  Plotly.newPlot("chart-cargo-top", [
    { x: tops.map(t => t.port), y: tops.map(t => t.dn), name: "dn", type: "bar", marker: { color: "#0ea5e9" } },
    { x: tops.map(t => t.port), y: tops.map(t => t.ln), name: "ln", type: "bar", marker: { color: "#f97316" } },
  ], { barmode: "stack", margin: { t: 10, l: 50, r: 10, b: 90 }, xaxis: { tickangle: -45 } },
  { displayModeBar: false, responsive: true });

  renderHeatmap();

  document.getElementById("cargo-kind").addEventListener("change", renderHeatmap);

  renderCargoGaps();
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
      if (!state.fleet) state.fleet = await loadJson("fleet.json");
      if (!state.vessels) {
        state.vessels = await loadJson("vessels_search.json");
        state.vesselsRows = state.vessels.items;
      }
      renderFleet();
      bindVesselsControls();
      renderVesselsTable();
      state.loaded.add("fleet");
    }
    if (tab === "cargo" && !state.loaded.has("cargo")) {
      if (!state.cargo) state.cargo = await loadJson("cargo.json");
      renderCargo();
      state.loaded.add("cargo");
    }
    if (tab === "changes" && !state.loaded.has("changes")) {
      if (!state.changes) state.changes = await loadJson("changes.json");
      renderChanges();
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
  renderOverview();
  document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));
  showTab("overview");
}

boot().catch(e => {
  console.error(e);
  document.body.insertAdjacentHTML("afterbegin",
    `<div class="bg-red-100 text-red-800 p-4">데이터 로드 실패: ${e.message}</div>`);
});
