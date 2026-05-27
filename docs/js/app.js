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
  scope: null,         // Cycle 1: cached docs/derived/scope_audit.json
  loaded: new Set(),
};

// Cycle 1: cargo scope filter. When true (default), Fleet/Supply hides
// scope=excluded rows. Toggle in #fl-scope-show-excluded.
const scopeState = {
  hideExcluded: true,
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

function addSourceLabel(_elOrId, _source) {}
function setupSourceLabels(_root = document) {}

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

// ---------- Balance tab (was: PR-D Tanker Sector) ----------
// Cycle 2: extended from 5 tanker subclasses → 9 cargo categories
// (Container, Bulk Carrier, General Cargo, Other Cargo + 5 tanker subclasses).
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

// Selected cargo card filters all widgets in the Balance tab.
const tsState = {
  filter: "ALL",
  cargoBalance: null,
  cargoBalanceTop: null,
  monthlyMode: "abs",   // abs | yoy
  colorByCat: {},       // built from cards[].color after load
};

async function renderTankerSector() {
  const cardHost = document.getElementById("ts-cards");
  if (!cardHost) return;

  try {
    [tsState.cargoBalance, tsState.cargoBalanceTop] = await Promise.all([
      loadDerived("cargo_balance.json"),
      loadDerived("cargo_balance_top.json"),
    ]);
  } catch (e) {
    cardHost.innerHTML = `<div class="col-span-full">${errorState(
      `Balance derived JSON 로드 실패: ${e.message}. <code>python scripts/build_derived.py</code>를 실행하세요.`
    )}</div>`;
    return;
  }
  tsState.colorByCat = Object.fromEntries(
    (tsState.cargoBalance?.cards || []).map(c => [c.category, c.color])
  );

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

  if (!tsState.activeYear) tsState.activeYear = _pickTankerSectorYear(tsState.cargoBalance);
  buildTankerYearPills(tsState.cargoBalance);
  buildTankerCargoPills(tsState.cargoBalance);

  const periods = tsState.cargoBalance?.monthly?.periods || [];
  const periodRange = periods.length
    ? `(${periods[0]} ~ ${periods[periods.length - 1]}, ${periods.length}개월)`
    : "";
  const monthlyPeriodEl = document.getElementById("ts-monthly-period");
  if (monthlyPeriodEl) monthlyPeriodEl.textContent = periodRange;
  const last12 = periods.slice(-12);
  const commodityPeriodEl = document.getElementById("ts-commodity-period");
  if (commodityPeriodEl && last12.length) {
    commodityPeriodEl.textContent =
      `(직전 12개월 ton 기준 · ${last12[0]} ~ ${last12[last12.length - 1]})`;
  }

  drawTankerCards();
  drawTankerMonthly();
  drawTankerCommodityBars();
  drawTankerOperatorBars();
  drawTankerOperatorDonut();
}

function buildTankerCargoPills(payload) {
  const host = document.getElementById("ts-cargo-pills");
  if (!host) return;
  const cards = payload?.cards || [];
  const cargos = cards.map(c => c.category);
  if (!cargos.length) {
    host.innerHTML = `<button class="px-2 py-1 bg-slate-100 text-slate-400 text-xs" disabled>데이터 없음</button>`;
    return;
  }
  const active = tsState.filter || "ALL";
  const items = [{ key: "ALL", label: "전체" }, ...cargos.map(c => ({ key: c, label: c }))];
  host.innerHTML = items.map(it => {
    const isActive = it.key === active;
    const cls = isActive
      ? "px-2 py-1 bg-slate-800 text-white text-xs"
      : "px-2 py-1 bg-white hover:bg-slate-100 text-xs";
    return `<button data-cargo="${it.key}" class="${cls}" role="tab" aria-selected="${isActive}">${it.label}</button>`;
  }).join("");
  host.querySelectorAll("button[data-cargo]").forEach(btn => {
    btn.addEventListener("click", () => {
      tsState.filter = btn.dataset.cargo;
      buildTankerCargoPills(payload);
      drawTankerCards();
      drawTankerMonthly();
      drawTankerCommodityBars();
      drawTankerOperatorBars();
      drawTankerOperatorDonut();
    });
  });
}

function _pickTankerSectorYear(payload) {
  const mpy = payload?.months_per_year || {};
  const years = Object.keys(mpy).sort();
  if (!years.length) return null;
  const full = years.filter(y => mpy[y] === 12);
  return full.length ? full[full.length - 1] : years[years.length - 1];
}

function buildTankerYearPills(payload) {
  const host = document.getElementById("ts-year-pills");
  if (!host) return;
  const mpy = payload?.months_per_year || {};
  const years = Object.keys(mpy).sort();
  if (!years.length) {
    host.innerHTML = `<button class="px-2 py-1 bg-slate-100 text-slate-400 text-xs" disabled>데이터 없음</button>`;
    return;
  }
  const active = tsState.activeYear;
  host.innerHTML = years.map(y => {
    const isActive = y === active;
    const isPartial = (mpy[y] || 0) < 12;
    const label = `${y}년${isPartial ? ` (${mpy[y]}mo)` : ""}`;
    const cls = isActive
      ? "px-2 py-1 bg-slate-800 text-white text-xs"
      : "px-2 py-1 bg-white hover:bg-slate-100 text-xs";
    return `<button data-year="${y}" class="${cls}" role="tab" aria-selected="${isActive}">${label}</button>`;
  }).join("");
  host.querySelectorAll("button[data-year]").forEach(btn => {
    btn.addEventListener("click", () => {
      tsState.activeYear = btn.dataset.year;
      buildTankerYearPills(payload);
      drawTankerCards();   // only the cards depend on the active year right now
    });
  });
}

// Persistent column-sort state shared by the main + sub tables.
const tsTableSort = { key: "ton", dir: -1 };

function _tsApplyFilter(cat) {
  tsState.filter = (tsState.filter === cat) ? "ALL" : cat;
  buildTankerCargoPills(tsState.cargoBalance);
  drawTankerCards();
  drawTankerMonthly();
  drawTankerCommodityBars();
  drawTankerOperatorBars();
  drawTankerOperatorDonut();
}

function _tsRowsFromCards(cards, monthlyByCat, activeYear, yearMonths) {
  return cards.map(c => {
    let tonVal = c.ton_last_12m;
    let yoy = c.yoy_pct;
    if (activeYear && c.ton_by_year && activeYear in c.ton_by_year) {
      tonVal = c.ton_by_year[activeYear];
      yoy = yearMonths === 12 ? (c.yoy_by_year || {})[activeYear] : null;
    }
    return {
      category: c.category,
      color: c.color || tsState.colorByCat[c.category] || "#64748b",
      isTankerAgg: !!c.is_tanker_aggregate,
      isTankerSub: !!c.is_tanker_subclass,
      ton: tonVal ?? 0,
      yoy: yoy,
      vessels: c.vessel_count ?? 0,
      ops: c.operator_count ?? 0,
      age: c.avg_age_gt_weighted,
      hhi: c.hhi,
      topOp: c.top_operator,
      monthly: monthlyByCat[c.category] || [],
    };
  });
}

function _tsSortRows(rows) {
  const k = tsTableSort.key, dir = tsTableSort.dir;
  rows.sort((a, b) => {
    if (k === "category") return a.category.localeCompare(b.category) * dir;
    const av = a[k], bv = b[k];
    const aNull = av == null, bNull = bv == null;
    if (aNull && bNull) return 0;
    if (aNull) return 1;
    if (bNull) return -1;
    return (av - bv) * dir;
  });
}

function _tsRenderRow(r, opts = {}) {
  const compact = !!opts.compact;
  const pY = compact ? "py-2" : "py-2.5";
  const isActive = tsState.filter !== "ALL" && tsState.filter === r.category;
  const rowCls = isActive ? "bg-amber-50/70 hover:bg-amber-100/70" : "hover:bg-slate-50";
  const tagBadge = r.isTankerAgg
    ? `<span class="text-[9px] font-medium px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 ml-1.5 align-middle">5 subclass 합계</span>`
    : "";
  const tonStr = fmtTon(r.ton);
  const yoyHtml = r.yoy == null
    ? `<span class="text-slate-400">—</span>`
    : `<span class="${r.yoy >= 0 ? "kpi-trend-up" : "kpi-trend-down"} font-semibold">${r.yoy >= 0 ? "↑" : "↓"} ${Math.abs(r.yoy).toFixed(1)}%</span>`;
  const ageTxt = r.age == null ? '<span class="text-slate-400">—</span>' : `${r.age.toFixed(1)}년`;
  const hhiTxt = r.hhi == null ? '<span class="text-slate-400">—</span>' : Math.round(r.hhi).toLocaleString();
  const opName = r.topOp
    ? (r.topOp.owner.length > 28 ? r.topOp.owner.slice(0, 26) + "…" : r.topOp.owner)
    : '<span class="text-slate-400">—</span>';
  const opCount = r.topOp ? (r.topOp.count_in_category ?? r.topOp.count_in_subclass) : null;
  const opMeta = opCount != null
    ? `<span class="text-slate-400 text-[10px] ml-1">${opCount}척</span>`
    : "";
  const catNameCls = r.isTankerAgg
    ? "font-semibold text-slate-900"
    : (compact ? "font-medium text-slate-700" : "font-medium text-slate-800");
  return `<tr class="cursor-pointer ${rowCls}" data-cat="${r.category}"
              role="button" tabindex="0" aria-pressed="${isActive}"
              aria-label="${r.category} 필터 토글">
    <td class="px-3 ${pY} align-middle">
      <span class="inline-block w-1 h-4 rounded-sm align-middle mr-2" style="background:${r.color}"></span><span class="${catNameCls}">${r.category}</span>${tagBadge}
    </td>
    <td class="px-3 ${pY} text-right font-mono font-semibold text-slate-900">${tonStr}</td>
    <td class="px-3 ${pY} text-right">${yoyHtml}</td>
    <td class="px-3 ${pY} text-right font-mono text-slate-700">${(r.vessels || 0).toLocaleString()}</td>
    <td class="px-3 ${pY} text-right font-mono text-slate-700">${ageTxt}</td>
    <td class="px-3 ${pY} text-right font-mono text-slate-700">${r.ops ?? "—"}</td>
    <td class="px-3 ${pY} text-right font-mono text-slate-700">${hhiTxt}</td>
    <td class="px-3 ${pY} align-middle truncate max-w-[18rem]"><span class="text-slate-700">${opName}</span>${opMeta}</td>
    <td class="px-3 ${pY} text-right" title="24M monthly ton">${sparkline(r.monthly, { color: r.color, width: 80, height: 22 })}</td>
  </tr>`;
}

function _tsWireRowClicks(tbodyEl) {
  tbodyEl.querySelectorAll("tr[data-cat]").forEach(el => {
    el.addEventListener("click", () => _tsApplyFilter(el.dataset.cat));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        _tsApplyFilter(el.dataset.cat);
      }
    });
  });
}

function _tsWireSortHeaders(tableEl) {
  if (!tableEl || tableEl.dataset.sortWired) return;
  tableEl.dataset.sortWired = "1";
  tableEl.querySelectorAll("th[data-sort]").forEach(th => {
    th.classList.add("cursor-pointer", "select-none", "hover:bg-slate-100");
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      if (tsTableSort.key === k) tsTableSort.dir *= -1;
      else { tsTableSort.key = k; tsTableSort.dir = (k === "category") ? 1 : -1; }
      drawTankerCards();
    });
  });
}

function _tsRefreshSortArrows(tableEl) {
  if (!tableEl) return;
  tableEl.querySelectorAll("th[data-sort]").forEach(th => {
    const base = th.dataset.sortBase || (th.dataset.sortBase = th.innerHTML);
    const arrow = (th.dataset.sort === tsTableSort.key)
      ? (tsTableSort.dir > 0 ? " <span class='text-slate-400 text-[10px]'>▲</span>"
                             : " <span class='text-slate-400 text-[10px]'>▼</span>")
      : "";
    th.innerHTML = base + arrow;
  });
}

function drawTankerCards() {
  const host = document.getElementById("ts-cards");
  const subHost = document.getElementById("ts-cards-sub");
  const activeEl = document.getElementById("ts-active-filter");
  if (!host) return;
  const cards = tsState.cargoBalance?.cards || [];
  const monthlyByCat = {};
  for (const s of (tsState.cargoBalance?.monthly?.series || [])) {
    monthlyByCat[s.category] = s.ton_by_period || [];
  }
  const mpy = tsState.cargoBalance?.months_per_year || {};
  const activeYear = tsState.activeYear;
  const yearMonths = activeYear ? (mpy[activeYear] || 0) : 12;
  const yearLabel = activeYear
    ? `${activeYear}년${yearMonths < 12 ? ` (${yearMonths}mo)` : ""}`
    : "12M";
  for (const id of ["ts-table-year", "ts-table-sub-year"]) {
    const el = document.getElementById(id);
    if (el) el.textContent = `(${yearLabel})`;
  }

  // Split: main = 4 non-tanker + Tanker aggregate; sub = 5 tanker subclasses.
  const mainCards = cards.filter(c => !c.is_tanker_subclass);
  const subCards = cards.filter(c => c.is_tanker_subclass);
  const mainRows = _tsRowsFromCards(mainCards, monthlyByCat, activeYear, yearMonths);
  const subRows = _tsRowsFromCards(subCards, monthlyByCat, activeYear, yearMonths);
  _tsSortRows(mainRows);
  _tsSortRows(subRows);

  host.innerHTML = mainRows.map(r => _tsRenderRow(r)).join("");
  if (subHost) subHost.innerHTML = subRows.map(r => _tsRenderRow(r, { compact: true })).join("");
  _tsWireRowClicks(host);
  if (subHost) _tsWireRowClicks(subHost);

  const mainTableEl = document.getElementById("ts-table");
  const subTableEl = document.getElementById("ts-table-sub");
  _tsWireSortHeaders(mainTableEl);
  _tsWireSortHeaders(subTableEl);
  _tsRefreshSortArrows(mainTableEl);
  _tsRefreshSortArrows(subTableEl);

  if (activeEl) {
    if (tsState.filter === "ALL") {
      activeEl.textContent = "전체 화물 — 표 행을 클릭하여 필터링";
      activeEl.className = "text-xs text-slate-500";
    } else {
      activeEl.innerHTML = `<span class="active-filter-pill">필터: ${tsState.filter}<button type="button" id="ts-filter-clear" aria-label="필터 해제">×</button></span>`;
      activeEl.className = "";
      const clr = document.getElementById("ts-filter-clear");
      if (clr) clr.addEventListener("click", () => _tsApplyFilter(tsState.filter));
    }
  }
}

// Subclass / aggregate name sets (derived from loaded cards).
function _tsSubclassSet() {
  return new Set((tsState.cargoBalance?.cards || [])
    .filter(c => c.is_tanker_subclass).map(c => c.category));
}
function _tsIsTankerAggOrSub(cat) {
  if (cat === "Tanker") return true;
  return _tsSubclassSet().has(cat);
}

function drawTankerMonthly() {
  const data = tsState.cargoBalance?.monthly;
  if (!data) return;
  const periods = data.periods || [];
  const filter = tsState.filter;
  const subSet = _tsSubclassSet();
  // Rules:
  //  - filter "ALL" or a non-tanker main: show 4 mains + Tanker aggregate (drop 5 subclasses to avoid double-count)
  //  - filter "Tanker": expand into the 5 subclass traces (more informative breakdown)
  //  - filter a single subclass or main: just that one
  let series;
  if (filter === "ALL") {
    series = (data.series || []).filter(s => !subSet.has(s.category));
  } else if (filter === "Tanker") {
    series = (data.series || []).filter(s => subSet.has(s.category));
  } else {
    series = (data.series || []).filter(s => s.category === filter);
  }
  const traces = series.map(s => {
    const color = s.color || tsState.colorByCat[s.category] || "#64748b";
    let y = s.ton_by_period.slice();
    if (tsState.monthlyMode === "yoy") {
      y = y.map((v, i) => (i < 12 || !y[i - 12]) ? null : ((v - y[i - 12]) / y[i - 12]) * 100);
    }
    return {
      x: periods,
      y,
      name: s.category,
      type: "scatter",
      mode: "lines",
      stackgroup: tsState.monthlyMode === "abs" ? "one" : null,
      line: { color, width: tsState.monthlyMode === "abs" ? 0.5 : 2 },
      fillcolor: color,
      hovertemplate: tsState.monthlyMode === "abs"
        ? `<b>%{x}</b><br>${s.category}: %{y:,.0f} tons<extra></extra>`
        : `<b>%{x}</b><br>${s.category}: %{y:.1f}%<extra></extra>`,
    };
  });

  // PR-34: drop a vertical dashed line + label at each Jan-01 boundary so
  // calendar-year edges are visible at a glance, complementing the year
  // pills above the subclass cards.
  const boundaries = [];
  for (let i = 0; i < periods.length; i++) {
    const p = periods[i];
    if (p && p.endsWith("-01") && i > 0) {
      boundaries.push({
        type: "line",
        x0: p, x1: p, xref: "x",
        y0: 0, y1: 1, yref: "paper",
        line: { color: "#94a3b8", width: 1, dash: "dash" },
      });
    }
  }
  // Year labels just above the top axis
  const yearLabels = [];
  const seenYears = new Set();
  for (const p of periods) {
    const y = p ? p.slice(0, 4) : null;
    if (y && !seenYears.has(y)) {
      seenYears.add(y);
      yearLabels.push({
        x: `${y}-01`, y: 1.03, xref: "x", yref: "paper",
        text: `<b>${y}년</b>`,
        showarrow: false,
        font: { size: 10, color: "#475569" },
      });
    }
  }

  Plotly.newPlot("ts-monthly", traces, {
    margin: { t: 28, l: 60, r: 20, b: 50 },
    xaxis: { tickangle: -40 },
    yaxis: {
      title: tsState.monthlyMode === "abs" ? "ton" : "YoY %",
      zeroline: tsState.monthlyMode === "yoy",
    },
    legend: { orientation: "h", y: -0.2 },
    hovermode: "x unified",
    shapes: boundaries,
    annotations: yearLabels,
  }, { displayModeBar: false, responsive: true });
}

function drawTankerCommodityBars() {
  const filter = tsState.filter;
  const byCat = tsState.cargoBalanceTop?.top_commodities_by_category || {};
  const subSet = _tsSubclassSet();
  let list;
  if (filter === "ALL") {
    // Cross-category top: take top 3 per non-subclass category (avoid
    // double-counting Tanker + its 5 subclasses), trim to top 15 by ton.
    const acc = [];
    for (const [cat, rows] of Object.entries(byCat)) {
      if (subSet.has(cat)) continue;
      for (const r of (rows || []).slice(0, 3)) {
        acc.push({ ...r, category: cat });
      }
    }
    acc.sort((a, b) => b.ton_total - a.ton_total);
    list = acc.slice(0, 15);
  } else {
    list = (byCat[filter] || []).map(r => ({ ...r, category: filter }));
  }
  if (!list.length) {
    Plotly.purge("ts-commodity-bars");
    document.getElementById("ts-commodity-bars").innerHTML =
      `<div class="text-xs text-slate-400 p-4">선택한 화물(${filter})에 해당하는 코모디티 데이터 없음.</div>`;
    return;
  }
  list.reverse();  // largest at top
  const trace = {
    x: list.map(c => c.ton_total),
    y: list.map(c => c.name),
    type: "bar",
    orientation: "h",
    marker: {
      color: list.map(c => tsState.colorByCat[c.category] || "#64748b"),
    },
    customdata: list.map(c => [c.category, c.calls || 0]),
    hovertemplate: "<b>%{y}</b><br>%{customdata[0]}<br>%{x:,.0f} tons · %{customdata[1]:,} calls<extra></extra>",
    text: list.map(c => fmtTon(c.ton_total)),
    textposition: "outside",
    cliponaxis: false,
  };
  Plotly.newPlot("ts-commodity-bars", [trace], {
    margin: { t: 10, l: 180, r: 60, b: 40 },
    xaxis: { title: "ton (24M aggregate)" },
  }, { displayModeBar: false, responsive: true });
}

function _aggregateOperatorsAcrossCats() {
  // ALL-view: aggregate per-owner across the non-subclass categories (4 mains
  // + Tanker aggregate). Skipping the 5 subclasses avoids double-counting any
  // tanker operator that also appears under Product/Chemical/etc.
  const byCat = tsState.cargoBalanceTop?.top_operators_by_category || {};
  const subSet = _tsSubclassSet();
  const agg = new Map();
  for (const [cat, rows] of Object.entries(byCat)) {
    if (subSet.has(cat)) continue;
    for (const o of (rows || [])) {
      const key = o.owner;
      if (!agg.has(key)) {
        agg.set(key, {
          owner: o.owner, ticker: o.ticker, vessels: o.vessels, sum_gt: o.sum_gt,
          vessels_in_cargo: 0, sum_gt_in_cargo_est: 0,
        });
      }
      const a = agg.get(key);
      a.vessels_in_cargo += o.vessels_in_category || 0;
      a.sum_gt_in_cargo_est += o.sum_gt_in_category_est || 0;
    }
  }
  return [...agg.values()].sort((a, b) => b.sum_gt_in_cargo_est - a.sum_gt_in_cargo_est);
}

function drawTankerOperatorBars() {
  const filter = tsState.filter;
  const metaEl = document.getElementById("ts-operator-meta");
  let list, xVals, xTitle, hovertemplate;
  if (filter === "ALL") {
    list = _aggregateOperatorsAcrossCats().slice(0, 15);
    if (metaEl) metaEl.textContent = "(전 화물 합산 · Sum GT 추정치 기준)";
  } else {
    list = (tsState.cargoBalanceTop?.top_operators_by_category?.[filter] || []).slice(0, 15);
    if (metaEl) metaEl.textContent = `(${filter} · 카테고리 선박수 기준)`;
  }
  if (!list.length) {
    Plotly.purge("ts-operator-bars");
    document.getElementById("ts-operator-bars").innerHTML =
      `<div class="text-xs text-slate-400 p-4">선택한 화물(${filter})에 해당하는 운영사 데이터 없음.</div>`;
    return;
  }
  list.reverse();   // bar paints bottom-up
  if (filter === "ALL") {
    xVals = list.map(o => o.sum_gt_in_cargo_est);
    xTitle = "Sum GT (전 화물 추정)";
    hovertemplate =
      "<b>%{y}</b><br>" +
      "전 화물 GT (추정): %{x:,.0f}<br>" +
      "전 화물 선박: %{customdata[2]}척<br>" +
      "총 선박: %{customdata[0]}척<br>" +
      "Listed: %{customdata[1]}<extra></extra>";
  } else {
    xVals = list.map(o => o.vessels_in_category || 0);
    xTitle = `${filter} 선박 수`;
    hovertemplate =
      "<b>%{y}</b><br>" +
      `${filter} 선박: %{x}척<br>` +
      "총 선박: %{customdata[0]}척<br>" +
      `${filter} GT (추정): %{customdata[3]:,.0f}<br>` +
      "Listed: %{customdata[1]}<extra></extra>";
  }
  const trace = {
    x: xVals,
    y: list.map(o => o.owner.length > 28 ? o.owner.slice(0, 26) + "…" : o.owner),
    type: "bar",
    orientation: "h",
    marker: { color: list.map(o => o.ticker ? "#1A3A6B" : "#94a3b8") },
    customdata: list.map(o => [
      o.vessels,                                      // total fleet
      o.ticker || "private",
      o.vessels_in_cargo ?? o.vessels_in_category,    // cargo/cat slice
      o.sum_gt_in_category_est ?? 0,
    ]),
    hovertemplate,
    text: list.map(o => o.ticker ? o.ticker : ""),
    textposition: "outside",
    textfont: { size: 10, color: "#1A3A6B" },
    cliponaxis: false,
  };
  Plotly.newPlot("ts-operator-bars", [trace], {
    margin: { t: 10, l: 220, r: 60, b: 40 },
    xaxis: { title: xTitle },
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
  const filter = tsState.filter;
  let top5, total, unit, totalLabel;
  if (filter === "ALL") {
    // Skip the 5 subclasses so we don't double-count the Tanker aggregate.
    const totals = tsState.cargoBalanceTop?.totals_gt_by_category || {};
    const subSet = _tsSubclassSet();
    total = Object.entries(totals).reduce((a, [cat, v]) => a + (subSet.has(cat) ? 0 : (v || 0)), 0);
    const agg = _aggregateOperatorsAcrossCats();
    top5 = agg.slice(0, 5).reduce((a, o) => a + (o.sum_gt_in_cargo_est || 0), 0);
    unit = "GT";
    totalLabel = `${fmtTon(total)} GT (추정)`;
  } else {
    // Per-category: prefer vessel-count share (more interpretable than GT proxy)
    const ops = (tsState.cargoBalanceTop?.top_operators_by_category?.[filter] || [])
      .map(o => o.vessels_in_category || 0)
      .filter(v => v > 0)
      .sort((a, b) => b - a);
    top5 = ops.slice(0, 5).reduce((a, b) => a + b, 0);
    const card = (tsState.cargoBalance?.cards || []).find(c => c.category === filter);
    total = card?.vessel_count || ops.reduce((a, b) => a + b, 0);
    unit = "척";
    totalLabel = `${total.toLocaleString()}척`;
  }
  const other = Math.max(0, total - top5);
  const trace = {
    values: [top5, other],
    labels: ["Top 5", "그 외"],
    type: "pie",
    hole: 0.55,
    marker: { colors: ["#1A3A6B", "#cbd5e1"] },
    textinfo: "label+percent",
    hovertemplate: `<b>%{label}</b><br>%{value:,.0f} ${unit} (%{percent})<extra></extra>`,
  };
  Plotly.newPlot("ts-operator-donut", [trace], {
    margin: { t: 10, l: 10, r: 10, b: 30 },
    showlegend: false,
    annotations: [{
      text: `Total<br>${totalLabel}`,
      x: 0.5, y: 0.5, showarrow: false, font: { size: 12, color: "#475569" },
    }],
  }, { displayModeBar: false, responsive: true });
}

// ---------- Financials (IDX XBRL) ----------
// docs/data/companies_financials.json schema (scripts/fetch_idx_financials.py):
//   metadata{ comparison_currency:"USD", comparison_unit:"million", years[],
//             fx_idr_per_usd{}, fx_note, ... }
//   companies[]{ ticker, name, name_short, segment, currency, homepage, years[],
//                latest_year }
//   rows[]{ ticker, year, currency, revenue, net_income, total_assets, equity,
//           total_liabilities, op_cash_flow, net_margin, roe, roa, der,
//           current_ratio, native{revenue,net_income,total_assets,...}, ... }
// 모든 금액은 USD 백만(USD M). native.* 는 보고통화 백만.
const fnState = { year: null, segment: "all", sortBy: "revenue", sortDir: -1,
                  selected: null, initialized: false };

// 정밀 세그먼트 → 색·필터용 그룹 (테이블엔 원래 세그먼트 표기).
const FN_SEG_GROUP = (seg) => {
  const s = String(seg || "");
  if (/Tanker|Gas/i.test(s)) return "Tanker · Gas";
  if (/Bulk|Coal/i.test(s)) return "Bulk · Coal";
  if (/Offshore/i.test(s)) return "Offshore";
  if (/Port|Service/i.test(s)) return "Port · Services";
  return "Container · General";
};
const FN_SEG_COLORS = {
  "Tanker · Gas":       "#1A3A6B",
  "Bulk · Coal":        "#8B5E34",
  "Offshore":           "#2E7D6B",
  "Container · General":"#C2643B",
  "Port · Services":    "#6B5B95",
};

// USD 백만 포맷: ≥1,000 → "$1.15B", else "$738M"
const fnUSD = (v) => {
  if (v == null) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(2)}B`;
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}M`;
};
const fnPct = (v) => v == null ? "—" : `${Number(v).toFixed(1)}%`;
const fnX = (v) => v == null ? "—" : `${Number(v).toFixed(2)}×`;
// native(보고통화) 백만 포맷
const fnNative = (v, cur) => {
  if (v == null) return "—";
  const n = Number(v);
  if (cur === "IDR") {  // n = IDR 백만 → 조(T) / 십억(bn)
    if (Math.abs(n) >= 1e6) return `Rp ${(n / 1e6).toFixed(2)}T`;
    return `Rp ${(n / 1e3).toLocaleString(undefined, { maximumFractionDigits: 0 })}bn`;
  }
  if (Math.abs(n) >= 1000) return `${cur} ${(n / 1000).toFixed(2)}B`;
  return `${cur} ${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}M`;
};
const curBadge = (cur) => {
  const bg = cur === "USD" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800";
  return `<span class="inline-block px-1 rounded text-[9px] font-semibold ${bg}" title="원 보고통화">${cur}</span>`;
};

function renderFinancials() {
  const f = state.financials;
  const kpiEl = document.getElementById("fn-kpi");
  if (!f || !f.companies || !f.companies.length || !f.rows) {
    if (kpiEl) kpiEl.innerHTML = `<div class="col-span-full text-center text-slate-400 py-12">
      재무 데이터를 로드하지 못했습니다 (companies_financials.json).</div>`;
    return;
  }
  const meta = f.metadata || {};
  const byTicker = {};
  for (const c of f.companies) byTicker[c.ticker] = c;

  // First-time setup: subtitle, year pills, segment options, sort headers.
  if (!fnState.initialized) {
    fnState.initialized = true;
    const sub = document.getElementById("fn-subtitle");
    const yy = meta.years || [];
    if (sub) sub.innerHTML = `${meta.source || "IDX XBRL"} · ${f.companies.length}개사 · `
      + `${yy.length ? yy[0] + "–" + yy[yy.length - 1] : ""} · 수집 ${meta.fetched_at || ""}`;
    const fxEl = document.getElementById("fn-fx-note");
    if (fxEl) {
      const fx = meta.fx_idr_per_usd || {};
      fxEl.textContent = `환율(USD/IDR) ${meta.years ? meta.years[meta.years.length - 1] : ""}: ${fmt0(fx[meta.years ? meta.years[meta.years.length - 1] : ""])}`;
      fxEl.title = (meta.fx_note || "") + "\n" + Object.entries(fx).map(([y, v]) => `${y}: ${fmt0(v)}`).join("  ");
    }
    // year pills
    const years = (meta.years && meta.years.length)
      ? meta.years.slice()
      : Array.from(new Set(f.rows.map(r => r.year))).sort();
    fnState.year = years[years.length - 1];
    const pills = document.getElementById("fn-year-pills");
    if (pills) {
      pills.innerHTML = years.map(y =>
        `<button data-year="${y}" class="px-2.5 py-1 text-xs border-r border-slate-200 last:border-r-0">${y}</button>`
      ).join("");
      pills.querySelectorAll("button").forEach(b => {
        b.addEventListener("click", () => { fnState.year = b.dataset.year; renderFinancials(); });
      });
    }
    // segment dropdown (그룹 단위)
    const segSel = document.getElementById("fn-segment");
    if (segSel) {
      const groups = Array.from(new Set(f.companies.map(c => FN_SEG_GROUP(c.segment)))).sort();
      segSel.innerHTML = `<option value="all">전체</option>`
        + groups.map(g => `<option value="${g}">${g}</option>`).join("");
      segSel.value = fnState.segment;
      segSel.addEventListener("change", (e) => { fnState.segment = e.target.value; renderFinancials(); });
    }
    // sortable headers
    document.querySelectorAll("#fn-tbl th[data-sort]").forEach(th => {
      th.setAttribute("tabindex", "0");
      th.setAttribute("role", "columnheader");
      th.classList.add("cursor-pointer", "select-none");
      const handler = () => {
        const key = th.dataset.sort;
        if (fnState.sortBy === key) fnState.sortDir = -(fnState.sortDir);
        else { fnState.sortBy = key; fnState.sortDir = th.dataset.numeric ? -1 : 1; }
        renderFinancials();
      };
      th.addEventListener("click", handler);
      th.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handler(); }
      });
    });
  }

  // year pill active state
  document.querySelectorAll("#fn-year-pills button").forEach(b => {
    const on = b.dataset.year === fnState.year;
    b.classList.toggle("bg-slate-800", on);
    b.classList.toggle("text-white", on);
    b.classList.toggle("bg-white", !on);
    b.classList.toggle("hover:bg-slate-100", !on);
  });

  const yr = fnState.year;
  const seg = fnState.segment;
  const inSeg = (t) => seg === "all" || FN_SEG_GROUP((byTicker[t] || {}).segment) === seg;
  const yrRows = f.rows.filter(r => r.year === yr && inSeg(r.ticker));

  // KPI hero — industry totals for the selected year/segment
  const sumOf = (k) => yrRows.reduce((s, r) => s + (r[k] || 0), 0);
  const totRev = sumOf("revenue");
  const totNi = sumOf("net_income");
  const totAssets = sumOf("total_assets");
  const margins = yrRows.map(r => r.net_margin).filter(v => v != null).sort((a, b) => a - b);
  const medMargin = margins.length ? margins[Math.floor(margins.length / 2)] : null;
  renderKpis("fn-kpi", [
    { label: `대상 기업 (${yr})`, value: String(yrRows.length), sub: seg === "all" ? "전체 세그먼트" : seg },
    { label: "합산 매출", value: fnUSD(totRev), sub: "USD · IDX XBRL" },
    { label: "합산 순이익", value: fnUSD(totNi), sub: totRev ? `이익률 ${(totNi / totRev * 100).toFixed(1)}%` : "—" },
    { label: "중앙값 순이익률", value: fnPct(medMargin), sub: `합산 자산 ${fnUSD(totAssets)}` },
  ]);

  // Scatter — x=revenue(log), y=operating_margin, size=assets, color=segment group
  const groups = {};
  for (const r of yrRows) {
    const g = FN_SEG_GROUP((byTicker[r.ticker] || {}).segment);
    (groups[g] = groups[g] || []).push(r);
  }
  const maxAssets = Math.max(1, ...yrRows.map(r => r.total_assets || 0));
  const traces = Object.entries(groups).map(([g, rs]) => ({
    name: g,
    x: rs.map(r => r.revenue),
    y: rs.map(r => r.operating_margin),
    text: rs.map(r => r.ticker),
    customdata: rs.map(r => [(byTicker[r.ticker] || {}).name_short || r.ticker, r.total_assets, r.roe]),
    mode: "markers+text",
    textposition: "top center",
    textfont: { size: 9, color: "#475569" },
    marker: {
      size: rs.map(r => Math.max(9, Math.sqrt((r.total_assets || 0) / maxAssets) * 46)),
      color: FN_SEG_COLORS[g] || "#64748b",
      opacity: 0.78,
      line: { color: "#0f172a", width: 1 },
    },
    hovertemplate: "<b>%{text}</b> %{customdata[0]}<br>매출 $%{x:,.0f}M · 영업이익률 %{y:.1f}%"
      + "<br>총자산 $%{customdata[1]:,.0f}M · ROE %{customdata[2]:.1f}%<extra>" + g + "</extra>",
  }));
  const scYr = document.getElementById("fn-scatter-year");
  if (scYr) scYr.textContent = `(${yr})`;
  Plotly.newPlot("fn-scatter", traces, {
    margin: { t: 10, l: 56, r: 10, b: 46 },
    xaxis: { title: "매출 (USD M, 로그)", type: "log", zeroline: false, gridcolor: "#eef2f7" },
    yaxis: { title: "영업이익률 (%)", zeroline: true, zerolinecolor: "#cbd5e1", gridcolor: "#eef2f7" },
    legend: { orientation: "h", y: -0.18, font: { size: 10 } },
    hoverlabel: { align: "left" },
  }, { displayModeBar: false, responsive: true });
  const gd = document.getElementById("fn-scatter");
  if (gd && !gd._fnClickBound) {
    gd._fnClickBound = true;
    gd.on("plotly_click", (ev) => {
      const t = ev.points && ev.points[0] && ev.points[0].text;
      if (t) { fnState.selected = t; renderFnDetail(); }
    });
  }

  // League table
  const yearTxt = document.getElementById("fn-table-year");
  if (yearTxt) yearTxt.textContent = `(${yr}${seg === "all" ? "" : " · " + seg})`;
  const cellVal = (r, key) => {
    if (key === "name_short") return (byTicker[r.ticker] || {}).name_short || "";
    if (key === "segment") return (byTicker[r.ticker] || {}).segment || "";
    return r[key];
  };
  // sortDir: +1 오름차순, -1 내림차순 (문자/숫자 동일 부호 규약)
  const sorted = yrRows.slice().sort((a, b) => {
    const x = cellVal(a, fnState.sortBy), y = cellVal(b, fnState.sortBy);
    if (x == null && y == null) return 0;
    if (x == null) return 1; if (y == null) return -1;
    if (typeof x === "string" || typeof y === "string") {
      return String(x).localeCompare(String(y)) * fnState.sortDir;
    }
    return (x < y ? -1 : (x > y ? 1 : 0)) * fnState.sortDir;
  });
  document.querySelectorAll("#fn-tbl th[data-sort]").forEach(th => {
    th.classList.remove("sort-asc", "sort-desc");
    th.setAttribute("aria-sort", "none");
    if (th.dataset.sort === fnState.sortBy) {
      th.classList.add(fnState.sortDir === 1 ? "sort-asc" : "sort-desc");
      th.setAttribute("aria-sort", fnState.sortDir === 1 ? "ascending" : "descending");
    }
  });
  const niCls = (v) => v == null ? "" : (v < 0 ? "text-red-600 font-semibold" : "");
  const derCls = (v) => v == null ? "" : (v >= 2.0 ? "text-amber-600 font-semibold" : "");
  document.querySelector("#fn-tbl tbody").innerHTML = sorted.map(r => {
    const c = byTicker[r.ticker] || {};
    const sel = r.ticker === fnState.selected ? "bg-blue-50" : "";
    return `<tr class="fn-row cursor-pointer hover:bg-slate-50 ${sel}" data-ticker="${r.ticker}">
      <td class="px-2 py-1 font-mono">${idxLink(r.ticker)} ${curBadge(r.currency)}</td>
      <td class="px-2 py-1">${c.name_short || ""}</td>
      <td class="px-2 py-1 text-[11px] text-slate-500">${c.segment || ""}</td>
      <td class="px-2 py-1 text-right">${fnUSD(r.revenue)}</td>
      <td class="px-2 py-1 text-right ${niCls(r.operating_profit)}">${fnUSD(r.operating_profit)}</td>
      <td class="px-2 py-1 text-right ${niCls(r.net_income)}">${fnUSD(r.net_income)}</td>
      <td class="px-2 py-1 text-right ${niCls(r.net_margin)}">${fnPct(r.net_margin)}</td>
      <td class="px-2 py-1 text-right">${fnPct(r.roe)}</td>
      <td class="px-2 py-1 text-right ${derCls(r.der)}">${fnX(r.der)}</td>
      <td class="px-2 py-1 text-right">${fnX(r.current_ratio)}</td>
      <td class="px-2 py-1 text-right">${fnUSD(r.total_assets)}</td>
    </tr>`;
  }).join("");
  document.querySelectorAll("#fn-tbl tbody tr.fn-row").forEach(tr => {
    tr.addEventListener("click", () => { fnState.selected = tr.dataset.ticker; renderFinancials(); });
  });

  // Detail — default to the largest-revenue company in current view
  if (!fnState.selected || !sorted.some(r => r.ticker === fnState.selected)) {
    const top = yrRows.slice().sort((a, b) => (b.revenue || 0) - (a.revenue || 0))[0];
    fnState.selected = top ? top.ticker : null;
  }
  renderFnDetail();
}

// 개별 기업 5개년 상세 — 매출/영업이익/순이익 막대 + 비율 추이 + native 수치
function renderFnDetail() {
  const f = state.financials;
  const host = document.getElementById("fn-detail");
  if (!f || !host) return;
  const ticker = fnState.selected;
  const c = (f.companies || []).find(x => x.ticker === ticker);
  if (!ticker || !c) {
    host.innerHTML = `<p class="text-xs text-slate-400">표의 행이나 그래프의 점을 클릭하면 기업별 5개년 추이가 표시됩니다.</p>`;
    return;
  }
  const rows = f.rows.filter(r => r.ticker === ticker).sort((a, b) => a.year.localeCompare(b.year));
  const latest = rows[rows.length - 1] || {};
  const homepage = c.homepage
    ? `<a href="${/^https?:/.test(c.homepage) ? "" : "https://"}${c.homepage}" target="_blank" rel="noopener" class="text-blue-600 hover:underline">${c.homepage.replace(/^https?:\/\//, "")}</a>`
    : "";
  host.innerHTML = `
    <div class="flex items-baseline justify-between flex-wrap gap-2 mb-3">
      <div>
        <h3 class="font-semibold text-lg">${c.name_short} <span class="font-mono text-sm text-slate-500">${idxLink(c.ticker)}</span> ${curBadge(c.currency)}</h3>
        <p class="text-xs text-slate-500">${c.name} · ${c.segment} ${homepage ? "· " + homepage : ""}</p>
      </div>
      <div class="text-right text-xs text-slate-500">
        <div>원 보고통화 <strong class="text-slate-700">${c.currency}</strong></div>
        <div>${latest.year} 매출 ${fnNative(latest.native ? latest.native.revenue : null, c.currency)} · 영업이익 ${fnNative(latest.native ? latest.native.operating_profit : null, c.currency)} · 순이익 ${fnNative(latest.native ? latest.native.net_income : null, c.currency)}</div>
      </div>
    </div>
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div><div id="fn-detail-bars" style="height:260px"></div></div>
      <div class="overflow-auto">
        <table class="min-w-full text-xs">
          <thead class="bg-slate-50 text-slate-500"><tr class="text-right">
            <th class="px-2 py-1 text-left">연도</th><th class="px-2 py-1">매출</th><th class="px-2 py-1">영업이익</th><th class="px-2 py-1">순이익</th>
            <th class="px-2 py-1">영업이익률</th><th class="px-2 py-1">순이익률</th><th class="px-2 py-1">ROE</th><th class="px-2 py-1">부채/자본</th>
            <th class="px-2 py-1">유동비율</th><th class="px-2 py-1">총자산</th>
          </tr></thead>
          <tbody>${rows.map(r => `<tr class="text-right border-t border-slate-100">
            <td class="px-2 py-1 text-left font-mono">${r.year}</td>
            <td class="px-2 py-1">${fnUSD(r.revenue)}</td>
            <td class="px-2 py-1 ${r.operating_profit < 0 ? "text-red-600" : ""}">${fnUSD(r.operating_profit)}</td>
            <td class="px-2 py-1 ${r.net_income < 0 ? "text-red-600" : ""}">${fnUSD(r.net_income)}</td>
            <td class="px-2 py-1">${fnPct(r.operating_margin)}</td>
            <td class="px-2 py-1">${fnPct(r.net_margin)}</td>
            <td class="px-2 py-1">${fnPct(r.roe)}</td>
            <td class="px-2 py-1">${fnX(r.der)}</td>
            <td class="px-2 py-1">${fnX(r.current_ratio)}</td>
            <td class="px-2 py-1">${fnUSD(r.total_assets)}</td>
          </tr>`).join("")}</tbody>
        </table>
        <p class="text-[10px] text-slate-400 mt-1">금액 USD 백만 (비교용 환산). 영업이익 = 매출총이익 − 판관비 + 기타영업손익(IDX XBRL 컴포넌트 도출). 원 보고통화 native 는 상단 우측.</p>
      </div>
    </div>`;
  Plotly.newPlot("fn-detail-bars", [
    { type: "bar", name: "매출", x: rows.map(r => r.year), y: rows.map(r => r.revenue),
      marker: { color: "#1A3A6B" },
      hovertemplate: "%{x} 매출 $%{y:,.0f}M<extra></extra>" },
    { type: "bar", name: "영업이익", x: rows.map(r => r.year), y: rows.map(r => r.operating_profit),
      marker: { color: rows.map(r => (r.operating_profit < 0 ? "#dc2626" : "#2E7D6B")) },
      hovertemplate: "%{x} 영업이익 $%{y:,.0f}M<extra></extra>" },
    { type: "bar", name: "순이익", x: rows.map(r => r.year), y: rows.map(r => r.net_income),
      marker: { color: rows.map(r => (r.net_income < 0 ? "#dc2626" : "#3b82f6")) },
      hovertemplate: "%{x} 순이익 $%{y:,.0f}M<extra></extra>" },
  ], {
    margin: { t: 10, l: 48, r: 8, b: 30 },
    barmode: "group",
    yaxis: { title: "USD M", zeroline: true, zerolinecolor: "#cbd5e1", gridcolor: "#eef2f7" },
    xaxis: { gridcolor: "#eef2f7" },
    legend: { orientation: "h", y: -0.16, font: { size: 10 } },
  }, { displayModeBar: false, responsive: true });
}

// ---------- Tabs ----------
// Cycle 1: 5탭 → 4탭 재편. data-tab id는 기존 호환을 위해 유지하되
// 화면 라벨은 Demand / Supply / Balance / Explorer.
const TAB_TITLES = {
  "overview":      "Demand",
  "fleet":         "Supply",
  "tanker-sector": "Balance",
  "financials":    "Financials",
  // legacy ids — accessible via deep-link only, hidden from nav
  "cargo":         "Cargo (legacy)",
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
    if (tab === "fleet" && !state.loaded.has("fleet")) {
      await renderFleet();
      state.loaded.add("fleet");
    }
    // Cycle 2: Cargo 항만 인포그래픽은 Demand 탭(tab-overview)으로 이관.
    // overview 활성화 시 한 번만 렌더링. legacy tab-cargo는 안내 페이지.
    if (tab === "overview" && !state.loaded.has("cargo")) {
      await renderCargo();
      state.loaded.add("cargo");
    }
    if (tab === "cargo" && !state.loaded.has("cargo")) {
      await renderCargo();
      state.loaded.add("cargo");
    }
    if (tab === "financials" && !state.loaded.has("financials")) {
      if (!state.financials) {
        try { state.financials = await loadJson("companies_financials.json"); }
        catch (e) { state.financials = null; }
      }
      renderFinancials();
      state.loaded.add("financials");
    }
    if (tab === "market" && !state.loaded.has("market")) {
      await renderMarket();
      state.loaded.add("market");
    }
    // Home (overview) renders eagerly in boot(), no lazy load.
  } catch (e) {
    console.error(e);
  }
}



// ---------- Boot ----------
async function boot() {
  // Renewal v2: light-weight boot. Demand (overview), Supply (fleet),
  // Balance (tanker-sector) and Explorer render lazily from docs/derived/*
  // on demand. legacy docs/data/{meta,overview,kpi_summary,...}.json reads removed.
  try { state.meta = await loadDerived("meta.json"); } catch (e) { state.meta = null; }
  // Cycle 1: scope_audit drives the meta-strip on every tab.
  try { state.scope = await loadDerived("scope_audit.json"); } catch (e) { state.scope = null; }
  populateScopeStrips();
  await renderHome();
  document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));
  // Cycle 2: 안내 페이지/탭 사이 점프 버튼. data-jump-tab 으로 표시.
  document.addEventListener("click", (e) => {
    const j = e.target.closest("[data-jump-tab]");
    if (j) { e.preventDefault(); showTab(j.dataset.jumpTab); }
  });
  bindTabKeyboardNav();
  // Cycle 19: URL hash로 시작 탭 결정. fleet 탭 deep-link 지원.
  const initialTab = (() => {
    const h = window.location.hash || "";
    const qIdx = h.indexOf("?");
    const tab = (qIdx >= 0 ? h.substring(1, qIdx) : h.substring(1)) || "";
    return ["overview", "fleet", "tanker-sector", "market", "financials"].includes(tab) ? tab : "overview";
  })();
  showTab(initialTab);
  loadGlobalFooter();
  setupSourceLabels();
  decorateGlossary(document);
}

// Cycle 1: populate every scope meta-strip from docs/derived/scope_audit.json.
// Single source of truth — each tab's strip pulls its counts from state.scope.
function populateScopeStrips() {
  const s = state.scope?.totals || {};
  // Cycle 5: Demand 탭의 scope-n-* 키들은 HTML에서 제거됨 — populator에서도 누락.
  const ids = {
    "fl-scope-cargo": s.cargo,
    "fl-scope-aux":   s.auxiliary,
    "fl-scope-excl":  s.excluded,
    "bl-scope-cargo": s.cargo,
    "bl-scope-aux":   s.auxiliary,
    "ex-scope-cargo": s.cargo,
    "ex-scope-aux":   s.auxiliary,
    "ex-scope-excl":  s.excluded,
    "ex-scope-unc":   s.unclassified,
  };
  for (const [id, v] of Object.entries(ids)) {
    const el = document.getElementById(id);
    if (el) el.textContent = v == null ? "—" : Number(v).toLocaleString();
  }
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

  // Cycle 3: d3 흐름 지도 제거에 따라 topo·sector-strip·foreign·insights
  // 호출 모두 정리. KPI + timeseries + map_flow(cv-app용 totals/routes) 만
  // 로드. cv-app의 Leaflet 인포그래픽은 renderCargo가 처리.
  let kpis, ts;
  try {
    [kpis, ts, homeState.mapData] = await Promise.all([
      loadDerived("home_kpi.json"),
      loadDerived("timeseries.json"),
      loadDerived("map_flow.json"),
    ]);
  } catch (e) {
    console.warn("Home derived load failed:", e);
    return;
  }
  // cargo_yearly.json is optional — year buttons gracefully degrade.
  try { homeState.cargoYearly = await loadDerived("cargo_yearly.json"); }
  catch (e) { homeState.cargoYearly = null; }
  // Cycle 3: CARGO 카테고리 시계열용 raw 데이터. 본 사이트 핵심 자산이라
  // 못 받으면 timeseries는 폴백(전체 sector)으로 동작.
  try { homeState.cargoMonthly = await loadJson("cargo_sector_monthly.json"); }
  catch (e) { homeState.cargoMonthly = null; }
  // Year-aware domestic/intl split — sourced from cargo_ports_periods.json
  // (per-period ports with dU/dS/iU/iS). Falls back to map_flow.totals (24M).
  try { homeState.cargoPortsPeriods = await loadDerived("cargo_ports_periods.json"); }
  catch (e) { homeState.cargoPortsPeriods = null; }
  homeState.timeseries = ts;

  renderHomeKpi(kpis, homeState.mapData);
  renderHomeTimeseries(ts);
  // Cycle 6: 시계열 차트 우측 패널 — 카테고리 상세 화물(코모디티) Top N
  renderCategoryDetails();
}

// Cycle 6 / PR-now: docs/derived/cargo_category_details.json 을 로드해서
// Demand 탭 시계열 차트 우측의 "카테고리 상세 화물" 박스를 채운다.
// schema v2 부터 카테고리별 by_year 윈도우를 지원하므로, 상단 home-year-pills
// 의 선택 연도에 맞춰 톤·코모디티 리스트가 동기화된다.
const catDetailState = { payload: null, active: null };

// 현재 활성 연도(home-kpi.dataset.activeYear) → 윈도우 헬퍼.
// 반환: { ton_total, calls_total, commodity_count, top_commodities, scope, year }
//   scope = "year" | "24m"   (year 가 없거나 매칭 안되면 24m fallback)
function _catWindowFor(cat) {
  if (!cat) return null;
  const yearAttr = (document.getElementById("home-kpi")?.dataset?.activeYear) || null;
  const byYr = cat.by_year || null;
  if (yearAttr && byYr && byYr[yearAttr]) {
    const w = byYr[yearAttr];
    return {
      ton_total:        w.ton_total,
      calls_total:      w.calls_total,
      commodity_count:  w.commodity_count,
      top_commodities:  (w.top_commodities || []).map(it => ({
        name: it.name,
        ton:  it.ton_year,
        pct:  it.pct,
        calls: it.calls_year,
      })),
      scope: "year",
      year:  yearAttr,
    };
  }
  // 24M fallback (legacy fields)
  return {
    ton_total:        cat.ton_total_24m,
    calls_total:      cat.calls_total_24m,
    commodity_count:  cat.commodity_count,
    top_commodities:  (cat.top_commodities || []).map(it => ({
      name: it.name,
      ton:  it.ton_24m,
      pct:  it.pct,
      calls: it.calls_24m,
    })),
    scope: "24m",
    year:  null,
  };
}

async function renderCategoryDetails() {
  // Reuse cached payload (year-pill 클릭 시 재호출되는 케이스).
  if (!catDetailState.payload) {
    try { catDetailState.payload = await loadDerived("cargo_category_details.json"); }
    catch (e) {
      const list = document.getElementById("cat-detail-list");
      if (list) list.innerHTML = `<div class="text-slate-400">cargo_category_details.json 로드 실패: ${e.message}</div>`;
      return;
    }
  }
  const payload = catDetailState.payload;
  const order = payload.order || [];
  if (!order.length) return;

  // Default active cat = 현재 윈도우 기준 ton desc 1위.
  // (윈도우 = 활성 연도면 그 해의 ton_total, 아니면 24M)
  const tonOf = (catName) => {
    const w = _catWindowFor(payload.categories[catName]);
    return w ? (w.ton_total || 0) : 0;
  };
  const byTon = [...order].sort((a, b) => tonOf(b) - tonOf(a));
  if (!catDetailState.active || !order.includes(catDetailState.active)) {
    catDetailState.active = byTon[0];
  }

  // Populate select (라벨에는 활성 윈도우의 톤수를 표시)
  const sel = document.getElementById("cat-detail-select");
  if (sel) {
    sel.innerHTML = order.map(c => {
      const w = _catWindowFor(payload.categories[c]);
      const tot = w ? w.ton_total : 0;
      return `<option value="${c}">${c} · ${fmtTon(tot)}</option>`;
    }).join("");
    sel.value = catDetailState.active;
    if (!sel.dataset.wired) {
      sel.dataset.wired = "1";
      sel.addEventListener("change", () => {
        catDetailState.active = sel.value;
        _drawCategoryDetailList();
      });
    }
  }
  _drawCategoryDetailList();
}

function _drawCategoryDetailList() {
  const host = document.getElementById("cat-detail-list");
  if (!host || !catDetailState.payload || !catDetailState.active) return;
  const cat = catDetailState.payload.categories[catDetailState.active];
  const w = _catWindowFor(cat);
  if (!w) {
    host.innerHTML = `<div class="text-slate-400">데이터 없음</div>`;
    return;
  }
  const color = CARGO_CATEGORY_PALETTE[catDetailState.active] || "#94a3b8";
  const items = w.top_commodities || [];
  if (!items.length) {
    host.innerHTML = `<div class="text-slate-400">상세 코모디티 없음</div>`;
    return;
  }
  const maxV = items[0].ton || 1;
  host.innerHTML = items.map((it, i) => {
    const ww = Math.max(2, Math.round((it.ton || 0) / maxV * 100));
    return `<div class="flex items-center gap-2 py-1 border-b border-slate-100 last:border-b-0">
      <span class="text-[10px] text-slate-400 font-mono w-4 text-right">${i + 1}</span>
      <div class="flex-1 min-w-0">
        <div class="flex items-baseline justify-between gap-2">
          <span class="truncate" title="${_esc(it.name)}">${_esc(it.name)}</span>
          <span class="font-mono text-slate-700 whitespace-nowrap">${fmtTon(it.ton)}</span>
        </div>
        <div class="cat-bar-wrap mt-0.5"><div class="cat-bar" style="width:${ww}%;background:${color}"></div></div>
        <div class="flex items-baseline justify-between gap-2 text-[10px] text-slate-400">
          <span>${(it.pct || 0).toFixed(1)}% · ${(it.calls || 0).toLocaleString()} 항해</span>
        </div>
      </div>
    </div>`;
  }).join("");
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

// ---------- PR-3 / PR-32: Home KPI 4 (year-aware) ----------
// PR-32 turns the two cargo-tonnage cards into year-based readouts driven by
// the new `kpis[*].by_year` payload. The selected year is tracked on the
// container element so the year-pill onclick handlers can re-render cheaply.
function _pickHomeYear(payload) {
  // Prefer most-recent FULL (12mo) year; else most-recent year available.
  let totalK = (payload.kpis || []).find(k => k.id === "total_12m_ton");
  if (!totalK || !totalK.by_year) return null;
  const ys = Object.keys(totalK.by_year).sort();
  if (!ys.length) return null;
  const mpy = totalK.months_per_year || {};
  const fullYears = ys.filter(y => mpy[y] === 12);
  return fullYears.length ? fullYears[fullYears.length - 1] : ys[ys.length - 1];
}

function _buildHomeYearPills(payload, activeYear) {
  const host = document.getElementById("home-year-pills");
  const banner = document.getElementById("home-year-banner");
  if (!host) return;
  const totalK = (payload.kpis || []).find(k => k.id === "total_12m_ton");
  if (!totalK || !totalK.by_year) {
    host.innerHTML = `<button class="px-2 py-1 bg-slate-100 text-slate-400 text-xs" disabled>데이터 없음</button>`;
    if (banner) banner.textContent = "";
    return;
  }
  const ys = Object.keys(totalK.by_year).sort();
  const mpy = totalK.months_per_year || {};
  host.innerHTML = ys.map(y => {
    const isActive = y === activeYear;
    const isPartial = (mpy[y] || 0) < 12;
    const label = `${y}년${isPartial ? ` (${mpy[y]}mo)` : ""}`;
    const cls = isActive
      ? "px-2 py-1 bg-slate-800 text-white text-xs"
      : "px-2 py-1 bg-white hover:bg-slate-100 text-xs";
    return `<button data-year="${y}" class="${cls}" role="tab" aria-selected="${isActive}">${label}</button>`;
  }).join("");
  host.querySelectorAll("button[data-year]").forEach(btn => {
    btn.addEventListener("click", () => {
      const y = btn.dataset.year;
      const el = document.getElementById("home-kpi");
      if (el) el.dataset.activeYear = y;
      renderHomeKpi(payload, homeState && homeState.mapData);
      _buildHomeYearPills(payload, y);
      // 카테고리 상세 화물 박스도 선택 연도에 동기화
      try { renderCategoryDetails(); } catch (_) {}
    });
  });
  if (banner) {
    const isPartial = (mpy[activeYear] || 0) < 12;
    banner.textContent = isPartial
      ? `⚠️ ${activeYear}년은 부분 연도 (${mpy[activeYear]}mo) — YoY 비교 시 주의.`
      : `${activeYear}년 (12개월).`;
  }
}

function renderHomeKpi(payload, mapPayload) {
  const host = document.getElementById("home-kpi");
  if (!host || !payload) return;

  // Resolve active year (URL state wins, else default = most-recent full year).
  let activeYear = host.dataset.activeYear;
  if (!activeYear) activeYear = _pickHomeYear(payload);
  if (activeYear) host.dataset.activeYear = activeYear;

  const trend = (yoy) => {
    if (yoy == null) return `<span class="text-slate-400 text-sm">YoY —</span>`;
    const cls = yoy >= 0 ? "kpi-trend-up" : "kpi-trend-down";
    const arrow = yoy >= 0 ? "↑" : "↓";
    return `<span class="${cls} text-sm font-semibold">${arrow} ${Math.abs(yoy).toFixed(1)}%</span>`;
  };

  // Year-specific value resolver — falls back to the legacy 12M fields
  // when by_year is absent (older payloads).
  const yearValue = (k) => {
    if (k.by_year && activeYear in k.by_year) {
      return {
        ton: k.by_year[activeYear],
        yoy: (k.yoy_by_year || {})[activeYear],
        months: (k.months_per_year || {})[activeYear] || 0,
      };
    }
    return { ton: k.value_ton, yoy: k.yoy_pct, months: 12 };
  };

  // Build the pills row even when activeYear is null — graceful empty state.
  _buildHomeYearPills(payload, activeYear);

  const yearLabel = activeYear
    ? `${activeYear}년${(payload.kpis.find(k => k.id === "total_12m_ton")?.months_per_year?.[activeYear] || 12) < 12 ? " (부분)" : ""}`
    : "12M";

  // Cycle 3: tanker_fleet KPI (선박 등록 척수)는 Supply 영역이므로 Demand
  // 탭에서 제외. 대체로 "국내 vs 국제 화물 비중" 카드(domestic_intl_split)
  // 를 map_flow.json.totals로부터 합성. KPI 순서: 총 화물 / 탱커 화물 /
  // 국내·국제 / 데이터 기준일.
  const cards = payload.kpis.map(k => {
    if (k.id === "total_12m_ton") {
      const v = yearValue(k);
      const partial = v.months < 12 ? `<span class="text-amber-600 text-xs">부분 ${v.months}mo</span>` : "";
      return `<div class="kpi-card-large">
        <div class="kpi-label">${yearLabel} 총 화물 물동량 (LK3)</div>
        <div>
          <div class="kpi-value-large">${fmtTon(v.ton)}<span class="text-base text-slate-400 ml-1">tons</span></div>
          <div class="kpi-sub-large">${trend(v.yoy)} ${partial}</div>
        </div>
      </div>`;
    }
    if (k.id === "tanker_12m_ton") {
      const v = yearValue(k);
      const partial = v.months < 12 ? `<span class="text-amber-600 text-xs">부분 ${v.months}mo</span>` : "";
      return `<div class="kpi-card-large">
        <div class="kpi-label">${yearLabel} 탱커 화물 물동량</div>
        <div>
          <div class="kpi-value-large">${fmtTon(v.ton)}<span class="text-base text-slate-400 ml-1">tons</span></div>
          <div class="kpi-sub-large">${trend(v.yoy)} ${partial}</div>
        </div>
      </div>`;
    }
    if (k.id === "tanker_fleet") {
      // Cycle 3: Supply 영역이므로 카드 위치만 차지 → "국내 vs 국제" 합성.
      // PR-now: 연도 선택(activeYear)에 따라 cargo_ports_periods.json의 해당
      //   기간 ports(dU/dS/iU/iS)를 합산해 dn/intl 비중을 재계산. 해당 기간
      //   데이터가 없으면 map_flow.totals(24M)로 폴백.
      let dn = null, ln = null, scopeLabel = "24M", scopeMonths = null;
      const cpp = homeState.cargoPortsPeriods;
      const yearPeriod = (cpp && activeYear && cpp.periods && cpp.periods[activeYear]) || null;
      if (yearPeriod) {
        let dnSum = 0, lnSum = 0;
        for (const code in (yearPeriod.ports || {})) {
          const pp = yearPeriod.ports[code];
          dnSum += Number(pp.dU || 0) + Number(pp.dS || 0);
          lnSum += Number(pp.iU || 0) + Number(pp.iS || 0);
        }
        dn = dnSum; ln = lnSum;
        scopeMonths = yearPeriod.months || null;
        scopeLabel = `${activeYear}년${(scopeMonths && scopeMonths < 12) ? ` (${scopeMonths}mo)` : ""}`;
      } else if (mapPayload && mapPayload.totals) {
        dn = Number(mapPayload.totals.domestic_ton || 0);
        ln = Number(mapPayload.totals.intl_ton || 0);
      } else {
        return `<div class="kpi-card-large">
          <div class="kpi-label">국내 vs 국제 비중</div>
          <div><div class="kpi-value-large">—</div>
          <div class="kpi-sub-large text-slate-400">데이터 없음</div></div>
        </div>`;
      }
      const totSum = dn + ln;
      const dnPct = totSum > 0 ? (dn / totSum * 100) : null;
      const lnPct = totSum > 0 ? (ln / totSum * 100) : null;
      const dnPctTxt = dnPct == null ? "—" : `${dnPct.toFixed(1)}%`;
      const lnPctTxt = lnPct == null ? "—" : `${lnPct.toFixed(1)}%`;
      return `<div class="kpi-card-large" title="Source: monitoring-inaportnet.dephub.go.id (LK3)">
        <div class="kpi-label">국내 vs 국제 화물 비중 <span class="text-[10px] text-slate-400 font-normal">(${scopeLabel})</span></div>
        <div>
          <div class="kpi-value-large" style="font-size:clamp(22px,3vw,30px)">
            <span class="text-blue-700">${dnPctTxt}</span>
            <span class="text-slate-400 mx-1">/</span>
            <span class="text-sky-600">${lnPctTxt}</span>
          </div>
          <div class="kpi-sub-large"><span class="text-slate-600">국내</span> ${fmtTon(dn)} <span class="text-slate-400">·</span> <span class="text-slate-600">국제</span> ${fmtTon(ln)} tons</div>
        </div>
      </div>`;
    }
    if (k.id === "data_freshness") {
      const partial = k.partial_dropped ? "(partial month dropped)" : "";
      return `<div class="kpi-card-large">
        <div class="kpi-label">데이터 기준일</div>
        <div>
          <div class="kpi-value-large" style="font-size:clamp(22px,3vw,32px)">${k.value_text || "—"}</div>
          <div class="kpi-sub-large">LK3 (vessel snapshot ${k.vessel_snapshot || "—"}) <span class="text-slate-400">${partial}</span></div>
        </div>
      </div>`;
    }
    return "";
  }).join("");
  host.innerHTML = cards;
}

// ---------- Cycle 3: Home 24M stacked area — CARGO sector 한정, 카테고리 분리 ----------
// 기존: sector(PASSENGER/CARGO/FISHING 등) stacked. 본 사이트 Demand 탭은
// 화물(LK3) 분석이므로 CARGO sector만 표시하고 그 안에서 vessel_class /
// tanker subclass 단위로 다시 분해해 카테고리별 색상을 분리한다.
// 데이터: cargo_sector_monthly.json (rows + tanker_subclass_rows).
const homeTsState = { mode: "abs", payload: null };

// Cycle 7+: Tier-2 commodity-category palette. backend/commodity_taxonomy.py
// 의 CATEGORY_COLORS 와 동기화. cv-app(Tier-1 bucket)/cat-details(Tier-2
// category)/시계열 차트 모두 동일 색상을 공유.
const CARGO_CATEGORY_PALETTE = {
  "Coal":                  "#52525b",
  "Mineral Ore":           "#71717a",
  "Other Dry Bulk":        "#a1a1aa",
  "Wood / Timber":         "#a16207",
  "Cement":                "#94a3b8",
  "Fertilizer":            "#84cc16",
  "Grain / Food":          "#f59e0b",
  "Crude Oil":             "#92400e",
  "Petroleum Product":     "#0284c7",
  "LPG / Gas":             "#d97706",
  "LNG":                   "#7c3aed",
  "Chemical":              "#059669",
  "Palm Oil":              "#16a34a",
  "Biodiesel (FAME)":      "#65a30d",
  "Other Vegetable Oil":   "#bef264",
  "Water":                 "#0ea5e9",
  "Container":             "#9333ea",
  "General Cargo":         "#f97316",
  "Vehicles":              "#ef4444",
  "Fish & Livestock":      "#06b6d4",
  "Other":                 "#cbd5e1",
};
// Stack order (bottom → top). Dry bulk family first (largest), then
// liquid bulk, then discrete cargoes. Kept in sync with the Python
// CATEGORY_ORDER tuple.
const CARGO_CATEGORY_ORDER = [
  "Coal", "Mineral Ore", "Other Dry Bulk", "Wood / Timber",
  "Cement", "Fertilizer", "Grain / Food",
  "Crude Oil", "Petroleum Product", "LPG / Gas", "LNG", "Chemical",
  "Palm Oil", "Biodiesel (FAME)", "Other Vegetable Oil", "Water",
  "Container", "General Cargo", "Vehicles", "Fish & Livestock", "Other",
];

function renderHomeTimeseries(payload) {
  homeTsState.payload = payload;
  homeTsState.mode = "abs";   // Cycle 5: 절대값 고정, YoY 토글 제거
  drawHomeTimeseries();
}

// Cycle 7+: Tier-2 commodity-category 시계열.
// 입력 우선순위:
//   1) cargo_sector_monthly.cargo_category_rows  — 신규 commodity-category
//      breakdown (mappable-port scope, cv-app 와 정합). 본 사이트 표준.
//   2) (legacy fallback) cargo_sector_monthly.rows + tanker_subclass_rows
//      — vessel-class 기반 (구 분류). schema v1 데이터일 때만 사용.
// 출력: { periods, series:[{ name, color, y }] }
function _buildCargoCategorySeries(cm) {
  if (!cm) return null;
  // 우선 경로: 신규 cargo_category_rows
  if (Array.isArray(cm.cargo_category_rows) && cm.cargo_category_rows.length) {
    const periodSet = new Set();
    const byCat = {};
    for (const r of cm.cargo_category_rows) {
      const cat = r.category;
      if (!cat) continue;
      periodSet.add(r.period);
      if (!byCat[cat]) byCat[cat] = {};
      byCat[cat][r.period] = (byCat[cat][r.period] || 0) + (Number(r.ton_total) || 0);
    }
    const periods = [...periodSet].sort();
    const knownOrder = CARGO_CATEGORY_ORDER.filter(k => byCat[k]);
    const unknownCats = Object.keys(byCat).filter(k => !CARGO_CATEGORY_ORDER.includes(k));
    const ordered = [...knownOrder, ...unknownCats];
    const series = ordered.map(name => ({
      name,
      color: CARGO_CATEGORY_PALETTE[name] || "#cbd5e1",
      y: periods.map(p => byCat[name][p] || 0),
    }));
    return { periods, series };
  }
  // 폴백: 구 vessel-class 시계열
  if (!cm.rows) return null;
  const periodSet = new Set();
  const byCat = {};
  for (const r of cm.rows) {
    if (r.sector !== "CARGO") continue;
    if (r.vessel_class === "Tanker") continue;
    periodSet.add(r.period);
    const key = r.vessel_class;
    if (!byCat[key]) byCat[key] = {};
    byCat[key][r.period] = (byCat[key][r.period] || 0) + (Number(r.ton_total) || 0);
  }
  for (const r of (cm.tanker_subclass_rows || [])) {
    periodSet.add(r.period);
    const key = r.subclass;
    if (!byCat[key]) byCat[key] = {};
    byCat[key][r.period] = (byCat[key][r.period] || 0) + (Number(r.ton_total) || 0);
  }
  const periods = [...periodSet].sort();
  const ordered = Object.keys(byCat);
  const series = ordered.map(name => ({
    name,
    color: CARGO_CATEGORY_PALETTE[name] || "#cbd5e1",
    y: periods.map(p => byCat[name][p] || 0),
  }));
  return { periods, series };
}

// Cycle 5: stacked area → 월별 stacked bar (절대값만). YoY 토글 제거.
function drawHomeTimeseries() {
  const cm = homeState && homeState.cargoMonthly;
  const built = _buildCargoCategorySeries(cm);
  let periods, series;
  if (built) {
    periods = built.periods;
    series  = built.series;
  } else {
    const payload = homeTsState.payload;
    if (!payload) return;
    periods = payload.periods || [];
    series = (payload.series || [])
      .filter(s => s.sector === "CARGO")
      .map(s => ({ name: "CARGO", color: "#1A3A6B", y: (s.ton_by_period || []).slice() }));
  }

  const traces = series.map(s => ({
    x: periods,
    y: s.y.slice(),
    name: s.name,
    type: "bar",
    marker: { color: s.color, line: { width: 0 } },
    hovertemplate: `<b>%{x}</b><br>${s.name}: %{y:,.0f} tons<extra></extra>`,
  }));

  Plotly.newPlot("home-timeseries", traces, {
    barmode: "stack",
    bargap: 0.18,
    autosize: true,
    margin: { t: 10, l: 56, r: 16, b: 50 },
    xaxis: {
      tickangle: -40,
      type: "category",
      tickfont: { size: 10 },
      automargin: true,
    },
    yaxis: {
      title: "ton",
      tickformat: "~s",
      automargin: true,
    },
    legend: { orientation: "h", y: -0.22, font: { size: 10 } },
    hovermode: "x unified",
  }, { displayModeBar: false, responsive: true });
}

// PR-35: append year buttons (2024 / 2025 / 2026) to the Home map's period
// control group. They share the same active-style + click handler as the
// 12M / 24M buttons; clicking sets homeState.filterPeriod to the 4-digit
// year string so drawHomeMap() can branch to the year-cut data path.
function _injectHomeMapYearButtons() {
  const host = document.getElementById("map-control-period");
  if (!host) return;
  const cy = homeState.cargoYearly;
  if (!cy || !cy.years || !cy.years.length) return;
  const mpy = cy.months_per_year || {};
  // Don't double-inject on re-renders
  if (host.querySelector("button[data-key^='20']")) return;
  for (const y of cy.years) {
    const partial = (mpy[y] || 0) < 12;
    const btn = document.createElement("button");
    btn.dataset.key = y;
    btn.className = "px-2 py-1 bg-white hover:bg-slate-100";
    btn.textContent = `${y}년${partial ? ` (${mpy[y]}mo)` : ""}`;
    btn.title = partial
      ? `${y}년 부분 (${mpy[y]}개월) — 카테고리 분리 없음 (단색 표시)`
      : `${y}년 풀 12개월 — 카테고리 분리 없음 (단색 표시)`;
    host.appendChild(btn);
  }
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

// PR-35: tiny helper that refreshes the "(period range)" callout next to
// the Home map title. Reads homeState.filterPeriod so it works for both
// rolling 24M and calendar-year picks.
function _refreshHomeMapPeriodLabel(timeseriesPayload) {
  const el = document.getElementById("home-map-period");
  if (!el) return;
  const period = homeState.filterPeriod || "24m";
  if (/^\d{4}$/.test(period)) {
    const mpy = homeState.cargoYearly?.months_per_year || {};
    const m = mpy[period] || 0;
    el.textContent = `(${period}년${m && m < 12 ? `, ${m}mo (부분)` : ` 달력연도`})`;
    return;
  }
  const ps = (timeseriesPayload || homeState.timeseries)?.periods || [];
  if (ps.length) {
    if (period === "12m") {
      const last12 = ps.slice(-12);
      el.textContent = `(${last12[0]} ~ ${last12[last12.length - 1]}, 12개월 누계)`;
    } else {
      el.textContent = `(${ps[0]} ~ ${ps[ps.length - 1]}, ${ps.length}개월 누계)`;
    }
  } else {
    el.textContent = "(누계)";
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

  // PR-35: filterPeriod can be "12m" / "24m" (rolling) or a 4-digit year
  // string (calendar year). Year mode swaps the data source to
  // cargo_yearly.by_year[Y].top_routes — no category breakdown is carried
  // there so routes render single-color (navy).
  const isYearMode = /^\d{4}$/.test(homeState.filterPeriod || "");
  let routes;
  let routeTonField;
  let yearLabel = null;
  if (isYearMode && homeState.cargoYearly?.by_year?.[homeState.filterPeriod]) {
    const slice = homeState.cargoYearly.by_year[homeState.filterPeriod];
    routes = (slice.top_routes || [])
      .filter(r => r.mappable !== false
        && r.lat_o != null && r.lon_o != null
        && r.lat_d != null && r.lon_d != null)
      .map(r => ({
        origin: r.origin, destination: r.destination,
        lat_o: r.lat_o, lon_o: r.lon_o,
        lat_d: r.lat_d, lon_d: r.lon_d,
        ton_24m: r.ton,                  // alias for the existing template
        vessels: 0,
        calls: r.calls || 0,
        // PR-36: backend now attaches dominant commodity category so year
        // mode colour-matches 24M mode.
        category: r.category || null,
        category_ton: r.category_ton || {},
      }));
    routeTonField = "ton_24m";
    const mpy = homeState.cargoYearly.months_per_year || {};
    const partial = (mpy[homeState.filterPeriod] || 0) < 12;
    yearLabel = `${homeState.filterPeriod}년${partial ? ` (${mpy[homeState.filterPeriod]}mo, 부분)` : ""}`;
    const cats = new Set(routes.map(r => r.category).filter(Boolean));
    notes.push(`${yearLabel} 달력연도 cut · 카테고리 ${cats.size}개 색상 분리`);
  } else {
    if (homeState.filterPeriod === "12m") {
      notes.push("12M OD 미산출 — 24M 누계 표시 중");
    }
    routes = (homeState.mapData.routes_top30 || []).slice();
  }
  // Traffic filter (dn_ln | dn | ln). Routes don't carry kind=dn/ln yet,
  // so we infer: foreign-port set = port names not in the Indonesian
  // 60-port list. Today that set is empty, so 'dn' ≡ 'dn_ln' and 'ln' = ∅
  // with an explicit note ("LK3 ln 분기 필요").
  {
    const idPortNames = new Set((homeState.mapData.ports || []).map(p => p.name));
    const isDomRoute = r => idPortNames.has(r.origin) && idPortNames.has(r.destination);
    if (homeState.filterTraffic === "dn") {
      const before = routes.length;
      routes = routes.filter(isDomRoute);
      notes.push(`국내만 · ${routes.length}/${before} routes`);
    } else if (homeState.filterTraffic === "ln") {
      const before = routes.length;
      routes = routes.filter(r => !isDomRoute(r));
      if (!routes.length) {
        notes.push(`국제 OD 데이터 미분리 — LK3 ln 분기 적재 필요 (0/${before})`);
      } else {
        notes.push(`국제만 · ${routes.length}/${before} routes`);
      }
    }
  }
  // Category filter — applies to year-mode AND 24M-mode routes.
  // Tanker-cat set: the 5 wet-cargo categories in map_flow.json.
  // Bulk-cat set: dry-bulk categories (Coal / Nickel / Iron Ore / Bauxite).
  const TANKER_CATS = new Set(["Crude", "Product / BBM", "Chemical", "LPG / LNG", "FAME / Edible"]);
  const BULK_CATS   = new Set(["Coal", "Nickel / Mineral Ore", "Iron Ore", "Bauxite", "Container / Gen Cargo"]);
  if (homeState.filterCategory === "tanker") {
    const before = routes.length;
    routes = routes.filter(r => TANKER_CATS.has(r.category));
    notes.push(`탱커만 · ${routes.length}/${before} routes`);
  } else if (homeState.filterCategory === "bulk") {
    const before = routes.length;
    routes = routes.filter(r => BULK_CATS.has(r.category));
    if (!routes.length && !isYearMode) {
      notes.push(`24M Top30은 드라이벌크 OD 미포함 — 연도 모드(2024/2025/2026)에서 가능`);
    } else {
      notes.push(`드라이벌크만 · ${routes.length}/${before} routes`);
    }
  }
  status.textContent = notes.join(" · ") || "24M 누계 · 모든 카테고리 · Top 30 routes";

  // Category color map.
  //   - 24M mode: map_flow.categories (5 tanker-focused)
  //   - year mode: cargo_yearly.categories (8 incl. Coal / Nickel-Mineral /
  //     Container) layered on top so non-tanker bulk routes get distinct
  //     colours.
  const categoryColors = {};
  for (const c of (homeState.mapData.categories || [])) categoryColors[c.name] = c.color;
  if (isYearMode && homeState.cargoYearly?.categories) {
    for (const c of homeState.cargoYearly.categories) categoryColors[c.name] = c.color;
  }

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
    // PR-35/36: categoryColors maps the 5 map_flow.categories names to hex.
    // Year-mode now has dominant category attached (PR-36) so the SAME
    // colour map applies; the gray fallback covers routes whose dominant
    // category fell outside the 5-bucket scheme.
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
  //   PR-38: in year mode, show the broader cargo_yearly category set so
  //   Coal / Nickel / Mineral legend swatches appear alongside Crude / BBM.
  const legend = document.getElementById("home-map-legend");
  if (legend) {
    const cats = isYearMode && homeState.cargoYearly?.categories
      ? homeState.cargoYearly.categories
      : (homeState.mapData.categories || []);
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
// PR-25: split Cargo & Fleet tab into separate Fleet and Cargo tabs.
//
// Both tabs use the existing `cargo_fleet.json` payload (class_counts,
// age_bins, treemap_categories, top_commodities). Fleet additionally
// pulls `owner_profile.json` for top-owner views; Cargo additionally
// pulls `route_facts.json` for OD lanes and `timeseries.json` for the
// sector trend.
// PR — Fleet tab faithfully mirrors jang1117.github.io/vessels:
//   Sidebar: Vessel Type (체크박스 + 제외 모드) + 건조연도 + GT + LOA +
//            Width + Depth + 선박명 + 초기화.
//   Right:   4 KPI cards + 평균 제원 strip + 6 charts + sortable table.
// All custom filters (Sector pills / Subclass / 선령 buckets / 선주 /
// 국적 select) from previous PRs have been stripped to keep parity with
// the reference site.
const FLEET_AGE_BUCKETS = [
  { key: "0-4",   label: "0–4년",    lo: 0,  hi: 5  },
  { key: "5-14",  label: "5–14년",   lo: 5,  hi: 15 },
  { key: "15-24", label: "15–24년",  lo: 15, hi: 25 },
  { key: "25+",   label: "25년+",    lo: 25, hi: 200 },
];
const FLEET_TANKER_SUBS = [
  "Crude Oil", "Product", "Chemical", "LPG", "LNG",
  "FAME / Vegetable Oil", "Water", "UNKNOWN",
];

async function renderFleet() {
  setupSourceLabels(document.getElementById("tab-fleet"));
  // Cycle 20: Supply 탭 헤더에 데이터 freshness 채움 (state.meta 사용)
  // Cycle 61: build_at 경과 일수에 따라 색상 적용 (≤3d emerald / 4-7d 기본 / >7d amber)
  try {
    const m = state.meta || {};
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v || "—"; };
    set("fl-meta-vessel", m.latest_vessel_snapshot_month);
    set("fl-meta-lk3", m.latest_lk3_month);
    set("fl-meta-build", (m.build_at || "").replace("T", " ").replace(/Z$/, "Z").substring(0, 16));
    if (m.build_at) {
      const ageDays = (Date.now() - new Date(m.build_at).getTime()) / 86400000;
      const buildEl = document.getElementById("fl-meta-build");
      if (buildEl && ageDays > 7) {
        buildEl.classList.add("text-amber-600");
        buildEl.title = `데이터 build 후 ${Math.round(ageDays)}일 경과 — 갱신 지연 가능`;
      } else if (buildEl && ageDays <= 3) {
        buildEl.classList.add("text-emerald-700");
        buildEl.title = `데이터 build 후 ${Math.round(ageDays)}일 경과 — fresh`;
      }
    }
  } catch (e) {}

  // Cycle 9: Top Owner 카드를 위해 fleet_owners.json 함께 로드. 실패해도
  // 메인 패널은 살아남도록 try/catch 분리.
  let fv;
  try {
    fv = await loadDerived("fleet_vessels.json");
  } catch (e) {
    const host = document.getElementById("fl-tbody");
    if (host) host.innerHTML =
      `<tr><td colspan="14">${errorState(`fleet_vessels.json 로드 실패: ${e.message}`)}</td></tr>`;
    return;
  }

  // Stash payloads on the tab element so filter handlers can re-read.
  const tabEl = document.getElementById("tab-fleet");
  tabEl._fleetVessels = fv;
  try {
    tabEl._fleetOwners = await loadDerived("fleet_owners.json");
  } catch (e) {
    tabEl._fleetOwners = null;
    console.warn("fleet_owners.json 로드 실패:", e.message);
  }
  // Cycle 47: owner_profile.json — Tanker 선박 detail에 운영사 tanker fleet 정보 보강
  try {
    const ownerProfile = await loadDerived("owner_profile.json");
    const map = new Map();
    for (const o of (ownerProfile.owners || [])) {
      if (o.owner) map.set(o.owner, o);
    }
    tabEl._fleetOwnerProfile = map;
  } catch (e) {
    tabEl._fleetOwnerProfile = null;
  }
  // Cycle 49: owner_ticker_map.json — IDX 상장사 ticker → owner name 매핑.
  //   각 owner를 normalize해 비교. 매치 시 정확한 ticker 표시.
  try {
    const tmap = await loadDerived("owner_ticker_map.json");
    const reverse = new Map();  // owner_norm → ticker
    const norm = (s) => String(s || "").toUpperCase().replace(/PT\.?\s*/g, "").replace(/[^A-Z0-9]/g, "");
    for (const [ticker, owners] of Object.entries(tmap.tickers || {})) {
      for (const o of owners) reverse.set(norm(o), ticker);
    }
    tabEl._fleetOwnerTicker = reverse;
  } catch (e) {
    tabEl._fleetOwnerTicker = null;
  }
  // Cycle 28: baseline 평균 GT / LOA — alert 비교용 (cargo + auxiliary 전체 기준)
  tabEl._fleetBaseline = _computeFleetBaseline(fv);
  // Cycle 35: vessel detail 컨텍스트용 — class median GT + owner total 사전 계산
  tabEl._fleetClassStats = _computeFleetClassStats(fv);
  tabEl._fleetOwnerTotals = _computeFleetOwnerTotals(fv);

  // Initial state object — jang1117 parity (no sector/subclass/age/owner/flag).
  if (!tabEl._fleetState) {
    tabEl._fleetState = {
      jenis: new Set(),                // checkbox selection of JenisDetailKet
      jenisQuery: "",                  // search box content
      jenisExclude: false,             // 제외 모드 toggle
      name: "",                        // 선박명 substring
      ownerExact: "",                  // Cycle 13: Top 운영사 row 클릭 시 set
      scopeOnly: null,                 // Cycle 15: null = 모두, "cargo" / "auxiliary" 선택 시 해당만
      vcFilter: null,                  // Cycle 17: vessel_class (vc) 한정 — 히트맵 셀 클릭 시 set
      flagFilter: null,                // Cycle 18: Flag chart 클릭 시 set
      gtMin: null, gtMax: null,
      yrMin: null, yrMax: null,
      loaMin: null, loaMax: null,
      widthMin: null, widthMax: null,
      depthMin: null, depthMax: null,
      sortCol: "gt",
      sortDir: "desc",
    };
  }

  _buildFleetFilters(fv);
  _wireFleetFilters();
  _wireFleetScopeToggle();
  _wireFleetAgedKpi();
  // Cycle 19: URL hash 파라미터 적용 (boot 시 한 번)
  _applyFleetUrlState();
  _wireFleetCopyLink();
  // Cycle 27: 클릭 가능한 차트 panel에 hover 강조 마커
  _markClickableFleetPanels();
  // Cycle 36: scroll-to-top 버튼 wire
  _wireFleetScrollTop();
  // Cycle 59: Esc 키로 펼친 detail 일괄 닫기
  _wireFleetKeyboardShortcuts();
  _renderFleetView();
}

// Cycle 28: 노후 alert baseline 비교용 — 전체 (cargo + aux scope) 25y+ 평균 GT/LOA 1회 계산
function _computeFleetBaseline(fv) {
  if (!fv || !fv.cols) return null;
  const I = {}; fv.cols.forEach((c, i) => I[c] = i);
  let sumGt = 0, nGt = 0, sumLoa = 0, nLoa = 0;
  for (const r of fv.rows) {
    const scope = r[I.scope];
    if (scope === "excluded" || scope === "unclassified") continue;
    const age = r[I.age];
    if (age == null || age < 25) continue;
    const gt = r[I.gt] || 0;
    if (gt > 0) { sumGt += gt; nGt += 1; }
    const loa = r[I.loa] || 0;
    if (loa > 0) { sumLoa += loa; nLoa += 1; }
  }
  return {
    avgGt: nGt > 0 ? Math.round(sumGt / nGt) : null,
    avgLoa: nLoa > 0 ? (sumLoa / nLoa) : null,
  };
}

// Cycle 35: class median GT — vessel detail에서 class 대비 표시용. cargo+aux scope만.
function _computeFleetClassStats(fv) {
  if (!fv || !fv.cols) return null;
  const I = {}; fv.cols.forEach((c, i) => I[c] = i);
  const byClass = new Map();
  for (const r of fv.rows) {
    const scope = r[I.scope];
    if (scope === "excluded" || scope === "unclassified") continue;
    const gt = r[I.gt] || 0;
    if (gt <= 0) continue;
    const cls = r[I.vc] || "Other";
    if (!byClass.has(cls)) byClass.set(cls, []);
    byClass.get(cls).push(gt);
  }
  const out = {};
  for (const [cls, arr] of byClass.entries()) {
    arr.sort((a, b) => a - b);
    out[cls] = { median: arr[Math.floor(arr.length / 2)], count: arr.length };
  }
  return out;
}

// Cycle 35: owner total — vessel detail에서 owner 컨텍스트 표시. cargo+aux scope만.
function _computeFleetOwnerTotals(fv) {
  if (!fv || !fv.cols) return null;
  const I = {}; fv.cols.forEach((c, i) => I[c] = i);
  const totals = new Map();
  for (const r of fv.rows) {
    const scope = r[I.scope];
    if (scope === "excluded" || scope === "unclassified") continue;
    const owner = r[I.owner];
    if (!owner) continue;
    const ent = totals.get(owner) || { vessels: 0, sumGt: 0 };
    ent.vessels += 1;
    ent.sumGt += r[I.gt] || 0;
    totals.set(owner, ent);
  }
  return totals;
}

// Cycle 59: keyboard shortcut — Esc 키 누르면 모든 detail rows 닫기 (포커스가 input/textarea가 아닐 때만)
function _wireFleetKeyboardShortcuts() {
  if (document.body.dataset.flKbBound) return;
  document.body.dataset.flKbBound = "1";
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    // 입력 중일 때는 무시
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    const tabEl = document.getElementById("tab-fleet");
    if (!tabEl || tabEl.classList.contains("hidden")) return;
    const exp = tabEl._fleetExpanded;
    if (!exp || exp.size === 0) return;
    exp.clear();
    _renderFleetView();
  });
}

// Cycle 36: 스크롤 깊이 따라 scroll-to-top 버튼 표시 토글
function _wireFleetScrollTop() {
  const btn = document.getElementById("fl-scroll-top");
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = "1";
  btn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  let raf = null;
  const onScroll = () => {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = null;
      const tabFleet = document.getElementById("tab-fleet");
      // 활성 탭이 fleet 일 때만 표시
      if (tabFleet?.classList.contains("hidden")) { btn.classList.add("hidden"); return; }
      if (window.scrollY > 600) btn.classList.remove("hidden");
      else btn.classList.add("hidden");
    });
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}

function _markClickableFleetPanels() {
  // 각 클릭 가능한 차트 div의 부모 panel(.bg-white.rounded-xl.shadow)에 data-clickable=1
  const ids = ["fl-ch-type", "fl-ch-age", "fl-ch-gt-bucket", "fl-ch-flag",
               "fl-age-class-heatmap", "fl-owner-scatter"];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    let p = el.parentElement;
    while (p && !p.classList.contains("rounded-xl")) p = p.parentElement;
    if (p) p.dataset.clickable = "1";
  });
}

// Cycle 19: URL hash 파라미터로 필터 상태 공유.
//   - 파라미터 key=value 쌍, 멀티값은 콤마. URLSearchParams 사용.
//   - hash 형식 `#fleet?aged=1&scope=cargo` — fleet 탭임을 명시.
const _FLEET_URL_KEYS = [
  "scope", "vc", "flag", "owner", "name",
  "yrMin", "yrMax", "gtMin", "gtMax", "loaMin", "loaMax",
  "widthMin", "widthMax", "depthMin", "depthMax",
  "jenis", "jenisExclude", "aged",
];

function _readFleetUrlParams() {
  const hash = window.location.hash || "";
  // 형식: #fleet?key=val&key2=val2 또는 #?key=val
  const qIdx = hash.indexOf("?");
  if (qIdx < 0) return null;
  const tabPart = hash.substring(1, qIdx);
  const params = new URLSearchParams(hash.substring(qIdx + 1));
  return { tab: tabPart || null, params };
}

function _applyFleetUrlState() {
  const parsed = _readFleetUrlParams();
  if (!parsed) return;
  if (parsed.tab && parsed.tab !== "fleet") return;
  const params = parsed.params;
  const tabEl = document.getElementById("tab-fleet");
  if (!tabEl) return;
  const st = tabEl._fleetState;

  // scope
  const sc = params.get("scope");
  if (sc === "cargo" || sc === "auxiliary") st.scopeOnly = sc;
  // vc / flag / owner / name
  if (params.get("vc"))   st.vcFilter = params.get("vc");
  if (params.get("flag")) st.flagFilter = params.get("flag");
  if (params.get("owner")) st.ownerExact = params.get("owner");
  if (params.get("name")) {
    st.name = params.get("name");
    const el = document.getElementById("fl-f-name"); if (el) el.value = st.name;
  }
  // jenis (comma-sep), jenisExclude
  if (params.get("jenis")) {
    params.get("jenis").split(",").map(s => s.trim()).filter(Boolean).forEach(j => st.jenis.add(j));
  }
  if (params.get("jenisExclude") === "1") {
    st.jenisExclude = true;
    const ex = document.getElementById("fl-f-jenis-exclude"); if (ex) ex.checked = true;
  }
  // aged shortcut: yrMax = currentYear - 25
  if (params.get("aged") === "1") {
    st.yrMax = new Date().getFullYear() - 25;
  }
  // numeric ranges
  const numKeys = [
    ["yrMin", "fl-f-yr-min"], ["yrMax", "fl-f-yr-max"],
    ["gtMin", "fl-f-gt-min"], ["gtMax", "fl-f-gt-max"],
    ["loaMin", "fl-f-loa-min"], ["loaMax", "fl-f-loa-max"],
    ["widthMin", "fl-f-w-min"], ["widthMax", "fl-f-w-max"],
    ["depthMin", "fl-f-d-min"], ["depthMax", "fl-f-d-max"],
  ];
  for (const [k, id] of numKeys) {
    const v = params.get(k);
    if (v != null && v !== "" && !Number.isNaN(Number(v))) {
      st[k] = Number(v);
      const el = document.getElementById(id); if (el) el.value = String(st[k]);
    }
  }
}

// URL hash 갱신 — render 마지막에 호출. 현재 필터 상태 → URL.
function _writeFleetUrl() {
  const tabEl = document.getElementById("tab-fleet");
  const st = tabEl?._fleetState;
  if (!st) return;
  const params = new URLSearchParams();
  if (st.scopeOnly) params.set("scope", st.scopeOnly);
  if (st.vcFilter)  params.set("vc", st.vcFilter);
  if (st.flagFilter) params.set("flag", st.flagFilter);
  if (st.ownerExact) params.set("owner", st.ownerExact);
  if (st.name)       params.set("name", st.name);
  if (st.jenis.size) params.set("jenis", [...st.jenis].join(","));
  if (st.jenisExclude) params.set("jenisExclude", "1");
  // aged shortcut detection
  const cutoff = new Date().getFullYear() - 25;
  if (st.yrMax === cutoff && st.yrMin == null) {
    params.set("aged", "1");
  } else {
    if (st.yrMin != null) params.set("yrMin", st.yrMin);
    if (st.yrMax != null) params.set("yrMax", st.yrMax);
  }
  if (st.gtMin != null) params.set("gtMin", st.gtMin);
  if (st.gtMax != null) params.set("gtMax", st.gtMax);
  if (st.loaMin != null) params.set("loaMin", st.loaMin);
  if (st.loaMax != null) params.set("loaMax", st.loaMax);
  if (st.widthMin != null) params.set("widthMin", st.widthMin);
  if (st.widthMax != null) params.set("widthMax", st.widthMax);
  if (st.depthMin != null) params.set("depthMin", st.depthMin);
  if (st.depthMax != null) params.set("depthMax", st.depthMax);

  const qs = params.toString();
  const newHash = qs ? `#fleet?${qs}` : `#fleet`;
  // 현재 보이는 탭이 fleet인 경우에만 hash 업데이트 (다른 탭 이동 시 보존)
  const activeTab = document.querySelector(".tab.active")?.dataset.tab;
  if (activeTab !== "fleet") return;
  if (window.location.hash !== newHash) {
    try { history.replaceState(null, "", window.location.pathname + window.location.search + newHash); }
    catch (e) {}
  }
}

function _wireFleetCopyLink() {
  const btn = document.getElementById("fl-copy-link");
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = "1";
  btn.addEventListener("click", async () => {
    _writeFleetUrl();
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      const orig = btn.textContent;
      btn.textContent = "✅ 복사됨";
      btn.classList.add("bg-emerald-50", "border-emerald-300");
      setTimeout(() => {
        btn.textContent = orig;
        btn.classList.remove("bg-emerald-50", "border-emerald-300");
      }, 1500);
    } catch (e) {
      // Clipboard 권한 미허용 fallback — prompt로 표시
      window.prompt("URL을 복사하세요:", url);
    }
  });
}

// Cycle 10: "노후선 25년+" KPI 카드 클릭 시 자동 필터.
//   - 1st click: yrMax = currentYear - 25 (only ≥25y 노후선만 보기)
//   - 2nd click: 필터 해제 (yrMax = null)
function _wireFleetAgedKpi() {
  const btn = document.getElementById("fl-kpi-aged25-card");
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = "1";
  btn.addEventListener("click", () => {
    const tabEl = document.getElementById("tab-fleet");
    if (!tabEl || !tabEl._fleetState) return;
    const st = tabEl._fleetState;
    const cutoff = new Date().getFullYear() - 25;
    const input = document.getElementById("fl-f-yr-max");
    if (st.yrMax === cutoff) {
      // toggle off — 노후선 필터 해제
      st.yrMax = null;
      if (input) input.value = "";
      btn.classList.remove("ring-2", "ring-rose-400", "bg-rose-50");
    } else {
      st.yrMax = cutoff;
      if (input) input.value = String(cutoff);
      btn.classList.add("ring-2", "ring-rose-400", "bg-rose-50");
      // 사용자가 필터 UI를 확인할 수 있도록 필터 패널 펼침
      const body = document.getElementById("fl-fbody");
      const tog = document.getElementById("fl-ftoggle");
      if (body && body.classList.contains("hidden")) {
        body.classList.remove("hidden");
        if (tog) tog.textContent = "▲ 접기";
      }
    }
    tabEl._fleetPage = 1;
    _renderFleetView();
  });
}

// Cycle 1 — wire the "제외 선종도 표시" toggle. Default OFF (cargo+aux only).
function _wireFleetScopeToggle() {
  const cb = document.getElementById("fl-scope-show-excluded");
  if (!cb || cb.dataset.wired) return;
  cb.dataset.wired = "1";
  cb.checked = !scopeState.hideExcluded;
  cb.addEventListener("change", () => {
    scopeState.hideExcluded = !cb.checked;
    const tabEl = document.getElementById("tab-fleet");
    if (tabEl) {
      tabEl._fleetPage = 1;
      _renderFleetView();
      _renderFleetJenisList(tabEl._fleetVessels);
    }
  });
  // Cycle 15: scope chip buttons (화물선 / 보조선) 클릭 토글
  const cargoBtn = document.getElementById("fl-scope-btn-cargo");
  const auxBtn   = document.getElementById("fl-scope-btn-aux");
  const setScope = (target) => {
    const tabEl = document.getElementById("tab-fleet");
    const st = tabEl?._fleetState; if (!st) return;
    st.scopeOnly = st.scopeOnly === target ? null : target;
    tabEl._fleetPage = 1;
    _refreshScopeButtonStates();
    _renderFleetView();
  };
  if (cargoBtn && !cargoBtn.dataset.wired) {
    cargoBtn.dataset.wired = "1";
    cargoBtn.addEventListener("click", () => setScope("cargo"));
  }
  if (auxBtn && !auxBtn.dataset.wired) {
    auxBtn.dataset.wired = "1";
    auxBtn.addEventListener("click", () => setScope("auxiliary"));
  }
  _refreshScopeButtonStates();
}

function _refreshScopeButtonStates() {
  const tabEl = document.getElementById("tab-fleet");
  const st = tabEl?._fleetState;
  const cur = st?.scopeOnly;
  const setActive = (id, target) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (cur === target) {
      el.classList.add("ring-2", "ring-blue-600");
      el.style.outline = "2px solid #1A3A6B";
    } else {
      el.classList.remove("ring-2", "ring-blue-600");
      el.style.outline = "";
    }
  };
  setActive("fl-scope-btn-cargo", "cargo");
  setActive("fl-scope-btn-aux",   "auxiliary");
}

function _idxOf(fv, name) { return (fv.cols || []).indexOf(name); }

function _buildFleetFilters(fv) {
  // jang1117 mirror: only build the Vessel Type list + table header.
  // (No sector/subclass/age/flag controls — removed.)
  _renderFleetJenisList(fv);

  const hbadge = document.getElementById("fl-hbadge");
  if (hbadge) hbadge.textContent = `${fv.rows.length.toLocaleString()} rows`;

  // Table header
  // Cycle 12: 의사결정 컬럼 우선 → raw 컬럼 후순위.
  //   1) 식별/소유: 선박명 / 선주 / Vessel Type / 국적
  //   2) 규모: GT / LOA / Width / Depth
  //   3) 연식: 건조 / 선령
  //   4) 보조 (raw·드물게 사용): 엔진 / 엔진 타입 / IMO / Call Sign — 시각적으로도 dim
  const th = document.getElementById("fl-thead-row");
  if (th && !th.dataset.wired) {
    th.dataset.wired = "1";
    const cols = [
      ["nama",       "선박명",       false],
      ["owner",      "선주",         false],
      ["jenis",      "Vessel Type",  false],
      ["flag",       "국적",         false],
      ["gt",         "GT",           false],
      ["loa",        "LOA (m)",      false],
      ["lebar",      "Width (m)",    false],
      ["dalam",      "Depth (m)",    false],
      ["tahun",      "건조",         false],
      ["age",        "선령",         false],
      ["mesin",      "엔진",         true ],
      ["mesin_type", "엔진 타입",    true ],
      ["imo",        "IMO",          true ],
      ["call_sign",  "Call Sign",    true ],
    ];
    th.innerHTML = cols.map(([k, l, dim]) =>
      `<th data-col="${k}" class="px-2 py-1 text-left font-semibold ${dim ? 'text-slate-400 bg-slate-50' : 'text-slate-600'} border-b border-slate-200 cursor-pointer hover:bg-slate-100 select-none" ${dim ? 'title="원천 데이터 — 운영 판단에는 보조 정보"' : ''}>${l} <span class="text-slate-300" data-sort-marker></span></th>`
    ).join("");
    th.querySelectorAll("th[data-col]").forEach(h => {
      h.addEventListener("click", () => {
        const st = document.getElementById("tab-fleet")._fleetState;
        const col = h.dataset.col;
        if (st.sortCol === col) st.sortDir = st.sortDir === "asc" ? "desc" : "asc";
        else { st.sortCol = col; st.sortDir = "asc"; }
        _renderFleetView();
      });
    });
  }
}

function _pillBtn(label, key, active, group = "fl-cls") {
  const cls = active
    ? "px-2 py-0.5 rounded border border-slate-700 bg-slate-700 text-white text-[11px]"
    : "px-2 py-0.5 rounded border border-slate-200 bg-white hover:bg-slate-50 text-[11px]";
  return `<button type="button" data-group="${group}" data-key="${key}" class="${cls}">${label}</button>`;
}

function _wireFleetFilters() {
  const tabEl = document.getElementById("tab-fleet");
  const st = tabEl._fleetState;
  const debouncedRender = _fleetDebounce(() => {
    tabEl._fleetPage = 1;
    _renderFleetView();
  }, 150);

  // ── Filter panel collapsible toggle (jang1117 동작) ──
  const fhead = document.getElementById("fl-fhead");
  if (fhead && !fhead.dataset.bound) {
    fhead.dataset.bound = "1";
    fhead.addEventListener("click", () => {
      const body = document.getElementById("fl-fbody");
      const toggle = document.getElementById("fl-ftoggle");
      if (!body) return;
      const open = body.classList.toggle("hidden");
      // hidden class added = collapsed; removed = open
      const isOpen = !open;
      if (toggle) toggle.textContent = isOpen ? "▲ 접기" : "▼ 펼치기";
    });
  }

  // ── Vessel Type search ──
  const jenisSearch = document.getElementById("fl-f-jenis-search");
  if (jenisSearch && !jenisSearch.dataset.bound) {
    jenisSearch.dataset.bound = "1";
    jenisSearch.addEventListener("input", _fleetDebounce(() => {
      st.jenisQuery = (jenisSearch.value || "").trim();
      _renderFleetJenisList(document.getElementById("tab-fleet")._fleetVessels);
    }, 120));
  }

  // ── 제외 모드 (Exclude) toggle — flips the meaning of selected jenis ──
  const excludeCb = document.getElementById("fl-f-jenis-exclude");
  if (excludeCb && !excludeCb.dataset.bound) {
    excludeCb.dataset.bound = "1";
    excludeCb.addEventListener("change", () => {
      st.jenisExclude = !!excludeCb.checked;
      _renderFleetView();
    });
  }

  // ── 선박명 substring ──
  const name = document.getElementById("fl-f-name");
  if (name && !name.dataset.bound) {
    name.dataset.bound = "1";
    name.addEventListener("input", () => {
      st.name = name.value.trim();
      debouncedRender();
    });
  }

  // ── Numeric ranges ──
  const num = (id, key) => {
    const el = document.getElementById(id);
    if (!el || el.dataset.bound) return;
    el.dataset.bound = "1";
    el.addEventListener("input", () => {
      const v = el.value === "" ? null : Number(el.value);
      st[key] = (v != null && !Number.isNaN(v)) ? v : null;
      debouncedRender();
    });
  };
  num("fl-f-gt-min",  "gtMin"); num("fl-f-gt-max",  "gtMax");
  num("fl-f-yr-min",  "yrMin"); num("fl-f-yr-max",  "yrMax");
  num("fl-f-loa-min", "loaMin"); num("fl-f-loa-max", "loaMax");
  num("fl-f-w-min",   "widthMin"); num("fl-f-w-max",   "widthMax");
  num("fl-f-d-min",   "depthMin"); num("fl-f-d-max",   "depthMax");

  // ── Reset all ──
  const reset = document.getElementById("fl-reset");
  if (reset && !reset.dataset.bound) {
    reset.dataset.bound = "1";
    reset.addEventListener("click", () => {
      st.jenis.clear();
      st.jenisQuery = "";
      st.jenisExclude = false;
      st.name = "";
      st.ownerExact = "";
      st.scopeOnly = null;
      st.vcFilter = null;
      st.flagFilter = null;
      st.gtMin = st.gtMax = st.yrMin = st.yrMax = null;
      st.loaMin = st.loaMax = null;
      st.widthMin = st.widthMax = st.depthMin = st.depthMax = null;
      const js = document.getElementById("fl-f-jenis-search"); if (js) js.value = "";
      const ex = document.getElementById("fl-f-jenis-exclude"); if (ex) ex.checked = false;
      const nm = document.getElementById("fl-f-name"); if (nm) nm.value = "";
      for (const id of ["fl-f-gt-min", "fl-f-gt-max", "fl-f-yr-min",
                         "fl-f-yr-max", "fl-f-loa-min", "fl-f-loa-max",
                         "fl-f-w-min", "fl-f-w-max",
                         "fl-f-d-min", "fl-f-d-max"]) {
        const el = document.getElementById(id); if (el) el.value = "";
      }
      document.getElementById("tab-fleet")._fleetPage = 1;
      _renderFleetJenisList(document.getElementById("tab-fleet")._fleetVessels);
      _renderFleetView();
    });
  }

  const csv = document.getElementById("fl-csv");
  if (csv && !csv.dataset.bound) {
    csv.dataset.bound = "1";
    csv.addEventListener("click", _fleetCsvDownload);
  }
  // Cycle 39: JSON export
  const jsn = document.getElementById("fl-json");
  if (jsn && !jsn.dataset.bound) {
    jsn.dataset.bound = "1";
    jsn.addEventListener("click", _fleetJsonDownload);
  }
  // Cycle 42: detail rows 일괄 닫기
  const closeAll = document.getElementById("fl-close-all-details");
  if (closeAll && !closeAll.dataset.bound) {
    closeAll.dataset.bound = "1";
    closeAll.addEventListener("click", () => {
      const tabElX = document.getElementById("tab-fleet");
      if (tabElX?._fleetExpanded) tabElX._fleetExpanded.clear();
      _renderFleetView();
    });
  }
  // Cycle 14: page size 선택. Cycle 18: 변경 시 localStorage 저장.
  const ps = document.getElementById("fl-page-size");
  if (ps && !ps.dataset.bound) {
    ps.dataset.bound = "1";
    ps.addEventListener("change", () => {
      const v = Number(ps.value);
      if (Number.isFinite(v) && v >= 25) {
        tabEl._fleetPageSize = v;
        tabEl._fleetPage = 1;
        try { localStorage.setItem("fl_pageSize", String(v)); } catch (e) {}
        _renderFleetView();
      }
    });
  }
  // Cycle 14: raw 컬럼 hide 토글. Cycle 18: localStorage 저장.
  const hr = document.getElementById("fl-hide-raw");
  if (hr && !hr.dataset.bound) {
    hr.dataset.bound = "1";
    hr.addEventListener("change", () => {
      tabEl._fleetHideRaw = !!hr.checked;
      try { localStorage.setItem("fl_hideRaw", hr.checked ? "1" : "0"); } catch (e) {}
      _renderFleetView();
    });
  }
  // Cycle 26: Vessel Type 차트 "전체 보기" 토글
  const tsa = document.getElementById("fl-type-show-all");
  if (tsa && !tsa.dataset.bound) {
    tsa.dataset.bound = "1";
    const stored = localStorage.getItem("fl_typeShowAll");
    if (stored === "1") tsa.checked = true;
    tsa.addEventListener("change", () => {
      try { localStorage.setItem("fl_typeShowAll", tsa.checked ? "1" : "0"); } catch (e) {}
      _renderFleetView();
    });
  }
  // Cycle 22: Top 운영사 sort 선택
  const os = document.getElementById("fl-owner-sort");
  if (os && !os.dataset.bound) {
    os.dataset.bound = "1";
    const stored = localStorage.getItem("fl_ownerSort");
    if (stored && ["vessels", "gt", "age"].includes(stored)) os.value = stored;
    os.addEventListener("change", () => {
      try { localStorage.setItem("fl_ownerSort", os.value); } catch (e) {}
      _renderFleetView();
    });
  }
  // Cycle 18: CSV 한글/영어 헤더 토글도 영속화
  const ko = document.getElementById("fl-csv-ko");
  if (ko && !ko.dataset.bound) {
    ko.dataset.bound = "1";
    const stored = localStorage.getItem("fl_csvKo");
    if (stored === "0") ko.checked = false;
    else if (stored === "1") ko.checked = true;
    ko.addEventListener("change", () => {
      try { localStorage.setItem("fl_csvKo", ko.checked ? "1" : "0"); } catch (e) {}
    });
  }
}

// Cycle 14: raw 컬럼 4개 (엔진/엔진타입/IMO/Call Sign) 표시/숨김 토글.
//   index 10, 11, 12, 13 (재정렬된 header 순서)
function _applyFleetRawColumnVisibility(hide) {
  const tbl = document.getElementById("fl-table");
  if (!tbl) return;
  const rawIndices = [10, 11, 12, 13];
  // thead
  const thead = document.getElementById("fl-thead-row");
  if (thead) {
    Array.from(thead.children).forEach((th, idx) => {
      th.style.display = (hide && rawIndices.includes(idx)) ? "none" : "";
    });
  }
  // tbody rows (rendered after _renderFleetTable; for safety apply ahead so re-renders preserve hide)
  const tbody = document.getElementById("fl-tbody");
  if (tbody) {
    Array.from(tbody.children).forEach(tr => {
      Array.from(tr.children).forEach((td, idx) => {
        td.style.display = (hide && rawIndices.includes(idx)) ? "none" : "";
      });
    });
  }
}

// PR-X: render the searchable Vessel Type (jenis) list. Filters the
// candidate pool by active Sector(s) and the search query; sorts by
// vessel count desc so heavy types surface first. Selected items keep
// their checkbox state via the underlying Set in fleetState.jenis.
function _renderFleetJenisList(fv) {
  const host = document.getElementById("fl-f-jenis-list");
  if (!host || !fv) return;
  const tabEl = document.getElementById("tab-fleet");
  const st = tabEl._fleetState;
  const byJenis = (fv.totals && fv.totals.by_jenis) || {};

  const q = (st.jenisQuery || "").toUpperCase();
  const items = [];
  for (const [name, meta] of Object.entries(byJenis)) {
    if (q && !name.toUpperCase().includes(q)) continue;
    items.push({ name, ...meta });
  }
  items.sort((a, b) => b.count - a.count);

  const totalEl = document.getElementById("fl-f-jenis-total");
  if (totalEl) totalEl.textContent = `${items.length} / ${Object.keys(byJenis).length}`;
  const selEl = document.getElementById("fl-f-jenis-selected");
  if (selEl) selEl.textContent = `선택 ${st.jenis.size}`;

  if (!items.length) {
    host.innerHTML = `<div class="text-slate-400 text-[11px] p-1">매치되는 type이 없습니다.</div>`;
    return;
  }

  // Cycle 2: jenis row에 scope 배지 추가. scope=cargo는 무배지(기본),
  // auxiliary/excluded/unclassified는 한 글자 배지로 즉시 식별 가능.
  // 사용자가 "Tug Boat" 를 보조선으로, "Patrol Boat" 를 제외 선종으로
  // 즉시 인지할 수 있게 한다.
  const SCOPE_BADGE = {
    cargo:        "",
    auxiliary:    `<span class="text-[9px] font-semibold px-1 py-px rounded bg-slate-200 text-slate-700" title="Cargo 보조선 (Tug)">보조</span>`,
    excluded:     `<span class="text-[9px] font-semibold px-1 py-px rounded bg-stone-200 text-stone-700" title="메인 차트에서 제외되는 선종">제외</span>`,
    unclassified: `<span class="text-[9px] font-semibold px-1 py-px rounded bg-red-100 text-red-700" title="분류 미정 — 감사 대상">미정</span>`,
  };
  host.innerHTML = items.map(it => {
    const checked = st.jenis.has(it.name) ? "checked" : "";
    const badge = SCOPE_BADGE[it.scope] || "";
    const muted = it.scope === "excluded" && scopeState.hideExcluded ? "opacity-50" : "";
    return `<label class="flex items-center gap-1.5 px-1 py-0.5 rounded hover:bg-slate-100 cursor-pointer ${muted}" title="${_esc(it.name)}${it.scope ? ' · scope: ' + it.scope : ''}">
      <input type="checkbox" data-jenis="${_esc(it.name)}" ${checked} class="cursor-pointer">
      <span class="truncate flex-1">${_esc(it.name)}</span>
      ${badge}
      <span class="text-slate-400 text-[10px] font-mono">${it.count.toLocaleString()}</span>
    </label>`;
  }).join("");

  // Bind checkbox changes (delegate)
  if (!host.dataset.boundChecks) {
    host.dataset.boundChecks = "1";
    host.addEventListener("change", (e) => {
      const cb = e.target.closest("input[data-jenis]");
      if (!cb) return;
      const name = cb.dataset.jenis;
      const stx = document.getElementById("tab-fleet")._fleetState;
      if (cb.checked) stx.jenis.add(name); else stx.jenis.delete(name);
      // Update count label without full re-render
      const selLbl = document.getElementById("fl-f-jenis-selected");
      if (selLbl) selLbl.textContent = `선택 ${stx.jenis.size}`;
      _renderFleetView();
    });
  }
}

function _fleetDebounce(fn, delay) {
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), delay);
  };
}

function _ageBucketKey(age) {
  if (age == null) return null;
  for (const b of FLEET_AGE_BUCKETS) {
    if (age >= b.lo && age < b.hi) return b.key;
  }
  return null;
}

function _applyFleetFilters() {
  const tabEl = document.getElementById("tab-fleet");
  const fv = tabEl._fleetVessels;
  const st = tabEl._fleetState;
  const cols = fv.cols;
  const I = {};
  for (const c of cols) I[c] = cols.indexOf(c);

  const nameQ = (st.name || "").toUpperCase();

  const filtered = fv.rows.filter(r => {
    // Cycle 1 — cargo scope filter (default: hide excluded + unclassified).
    // r[I.scope] is the 18th col added in fleet_vessels schema_version 5.
    if (scopeState.hideExcluded && I.scope != null) {
      const scope = r[I.scope];
      if (scope === "excluded" || scope === "unclassified") return false;
    }
    // Vessel Type filter — selected set + 제외 모드 (exclude vs include)
    if (st.jenis.size) {
      const matched = st.jenis.has(r[I.jenis] || "(blank)");
      if (st.jenisExclude ? matched : !matched) return false;
    }
    if (st.gtMin != null && r[I.gt] < st.gtMin) return false;
    if (st.gtMax != null && r[I.gt] > st.gtMax) return false;
    if (st.loaMin != null && r[I.loa] < st.loaMin) return false;
    if (st.loaMax != null && r[I.loa] > st.loaMax) return false;
    if (st.widthMin != null && (r[I.lebar] || 0) < st.widthMin) return false;
    if (st.widthMax != null && (r[I.lebar] || 0) > st.widthMax) return false;
    if (st.depthMin != null && (r[I.dalam] || 0) < st.depthMin) return false;
    if (st.depthMax != null && (r[I.dalam] || 0) > st.depthMax) return false;
    if (st.yrMin != null && (r[I.tahun] == null || r[I.tahun] < st.yrMin)) return false;
    if (st.yrMax != null && (r[I.tahun] == null || r[I.tahun] > st.yrMax)) return false;
    if (nameQ && !(r[I.nama] || "").toUpperCase().includes(nameQ)) return false;
    // Cycle 13: ownerExact 필터 (Top 운영사 row 클릭 시 set)
    if (st.ownerExact && r[I.owner] !== st.ownerExact) return false;
    // Cycle 15: scopeOnly 필터 (chip 클릭 시 set)
    if (st.scopeOnly && I.scope != null && r[I.scope] !== st.scopeOnly) return false;
    // Cycle 17: vcFilter (vessel_class) — 히트맵 셀 클릭 시 set
    if (st.vcFilter && r[I.vc] !== st.vcFilter) return false;
    // Cycle 18: flagFilter (Flag chart 클릭 시 set). Indonesia는 빈 문자열로 들어옴.
    if (st.flagFilter) {
      const f = (r[I.flag] || "Indonesia");
      if (f !== st.flagFilter) return false;
    }
    return true;
  });

  // Sort
  const sortI = I[st.sortCol] != null ? I[st.sortCol] : I.gt;
  const dir = st.sortDir === "asc" ? 1 : -1;
  filtered.sort((a, b) => {
    const av = a[sortI], bv = b[sortI];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
    return String(av).localeCompare(String(bv), "ko") * dir;
  });
  return { rows: filtered, I };
}

function _renderFleetView() {
  const tabEl = document.getElementById("tab-fleet");
  const fv = tabEl._fleetVessels;
  if (!fv) return;
  const { rows, I } = _applyFleetFilters();
  const totalRows = fv.rows.length;
  const st = tabEl._fleetState;

  // ---- KPI strip (5 cards · jang1117 layout) ----
  let sumGt = 0, nGt = 0, sumAgeGt = 0;
  let sumLoa = 0, nLoa = 0, sumW = 0, nW = 0, sumD = 0, nD = 0;
  let aged25 = 0, agedTotalForPct = 0, agedSumGt = 0;
  const jenisSet = new Set();
  for (const r of rows) {
    const gt = r[I.gt] || 0;
    if (gt > 0) { sumGt += gt; nGt++; }
    const age = r[I.age];
    if (gt > 0 && age != null) { sumAgeGt += age * gt; }
    // Cycle 9: 25년+ 노후선 카운트. age는 정수형(가용시), 결측은 KPI에서 제외.
    if (age != null) {
      agedTotalForPct += 1;
      if (age >= 25) { aged25 += 1; if (gt > 0) agedSumGt += gt; }
    }
    if ((r[I.loa] || 0) > 0)   { sumLoa += r[I.loa]; nLoa++; }
    if ((r[I.lebar] || 0) > 0) { sumW   += r[I.lebar]; nW++; }
    if ((r[I.dalam] || 0) > 0) { sumD   += r[I.dalam]; nD++; }
    if (r[I.jenis]) jenisSet.add(r[I.jenis]);
  }
  const avgGt = nGt > 0 ? sumGt / nGt : 0;
  const avgAge = sumGt > 0 ? sumAgeGt / sumGt : null;
  // jang1117 KPI writes — every setter guarded so a missing element
  // can't kill the render. Existence-checked once at the top to keep
  // hot path lean.
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };
  set("fl-kpi-count", fmtCount(rows.length));
  // Cycle 31: 선박 수 sub에 선대 GT 합계 추가 (시장 규모 신호)
  set("fl-kpi-pct",
    `${fmtCount(rows.length)} / ${fmtCount(totalRows)}` +
    (totalRows > 0 ? ` (${(rows.length / totalRows * 100).toFixed(1)}%)` : "") +
    (sumGt > 0 ? ` · GT ${fmtTon(sumGt)}` : ""));
  set("fl-kpi-jenis", fmtCount(jenisSet.size));
  set("fl-kpi-avggt", avgGt ? fmtCount(Math.round(avgGt)) : "—");
  // Cycle 9: "평균 건조연도" 대신 노후선 25년+ (척수 + %). 의사결정 직결.
  const agedPct = agedTotalForPct > 0 ? (aged25 / agedTotalForPct) * 100 : null;
  set("fl-kpi-aged25", aged25 ? fmtCount(aged25) : "—");
  // Cycle 31: 노후 KPI sub에 25y+ 척의 합계 GT 추가 (자산 규모 신호)
  set("fl-kpi-aged25-pct",
    (agedPct != null ? `전체 ${agedPct.toFixed(1)}% · ` : "") +
    (avgAge != null ? `평균 ${avgAge.toFixed(1)}년` : "평균 —") +
    (agedSumGt > 0 ? ` · GT ${fmtTon(agedSumGt)}` : ""));
  // Cycle 10: 노후선 필터 활성화 시 KPI 카드에 ring 강조.
  const agedBtn = document.getElementById("fl-kpi-aged25-card");
  if (agedBtn) {
    const cutoff = new Date().getFullYear() - 25;
    const active = st.yrMax === cutoff;
    agedBtn.classList.toggle("ring-2", active);
    agedBtn.classList.toggle("ring-rose-400", active);
    agedBtn.classList.toggle("bg-rose-50", active);
  }
  // 평균 제원 (치수 요약) — 4 sub-values
  set("fl-avg-gt",  avgGt ? fmtCount(Math.round(avgGt)) : "—");
  set("fl-avg-loa", nLoa ? (sumLoa / nLoa).toFixed(1) : "—");
  set("fl-avg-w",   nW   ? (sumW   / nW).toFixed(1)   : "—");
  set("fl-avg-d",   nD   ? (sumD   / nD).toFixed(1)   : "—");

  // ---- charts (each guarded — missing target = no-op, no throw) ----
  try { _drawFlChartYear(rows, I); }        catch (e) { console.error("Year chart:", e); }
  try { _drawFlChartType(rows, I); }        catch (e) { console.error("Type chart:", e); }
  try { _drawFlChartAge(rows, I); }         catch (e) { console.error("Age chart:", e); }
  try { _drawFlChartGtBucket(rows, I); }    catch (e) { console.error("GT bucket:", e); }
  try { _drawFlChartEngineType(rows, I); }  catch (e) { console.error("EngineType chart:", e); }
  try { _drawFlChartEngineName(rows, I); }  catch (e) { console.error("EngineName chart:", e); }
  try { _drawFlChartFlag(rows, I); }        catch (e) { console.error("Flag chart:", e); }
  try { _drawFlChartGtHist(rows, I); }      catch (e) { console.error("GT hist:", e); }
  try { _drawFleetTopOwners(rows, I); }     catch (e) { console.error("Top Owners:", e); }
  try { _drawFleetAgeClassHeatmap(rows, I); } catch (e) { console.error("Age×Class:", e); }
  try { _drawFleetOwnerScatter(rows, I); }    catch (e) { console.error("Owner scatter:", e); }
  try { _renderFleetActiveChips(st); }      catch (e) { console.error("Active chips:", e); }
  try { _renderFleetAgedAlert(rows, I, aged25, agedTotalForPct, st); } catch (e) { console.error("Aged alert:", e); }

  // ---- Active filter count badge (.fcount style: hidden when 0) ----
  const active = (st.jenis.size > 0 ? 1 : 0)
    + (st.name ? 1 : 0)
    + ((st.gtMin != null || st.gtMax != null) ? 1 : 0)
    + ((st.yrMin != null || st.yrMax != null) ? 1 : 0)
    + ((st.loaMin != null || st.loaMax != null) ? 1 : 0)
    + ((st.widthMin != null || st.widthMax != null) ? 1 : 0)
    + ((st.depthMin != null || st.depthMax != null) ? 1 : 0);
  const badge = document.getElementById("fl-fcount");
  if (badge) {
    badge.textContent = active;
    badge.style.display = active > 0 ? "inline" : "none";
  }
  const activeFilters = document.getElementById("fl-active-filters");
  if (activeFilters) activeFilters.textContent = active > 0 ? `활성 필터 ${active}개` : "";

  // ---- Sortable + paginated table ----
  // Cycle 14: page size 사용자 선택 (25/50/100/200). raw 컬럼 hide 토글.
  // Cycle 18: 사용자 preference를 localStorage에 영속화.
  if (typeof tabEl._fleetPage !== "number") tabEl._fleetPage = 1;
  if (typeof tabEl._fleetPageSize !== "number") {
    const saved = Number(localStorage.getItem("fl_pageSize"));
    tabEl._fleetPageSize = (saved && [25, 50, 100, 200].includes(saved)) ? saved : 100;
  }
  if (typeof tabEl._fleetHideRaw !== "boolean") {
    tabEl._fleetHideRaw = localStorage.getItem("fl_hideRaw") === "1";
  }
  const pageSize = tabEl._fleetPageSize;
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  if (tabEl._fleetPage > totalPages) tabEl._fleetPage = 1;
  // Apply raw column hide visually before render
  _applyFleetRawColumnVisibility(tabEl._fleetHideRaw);
  _renderFleetTable(rows, I, tabEl._fleetPage, pageSize);
  _renderFleetPagination(rows.length, tabEl._fleetPage, pageSize, totalPages);

  const info = document.getElementById("fl-list-info");
  if (info) {
    const start = (tabEl._fleetPage - 1) * pageSize + 1;
    const end = Math.min(start + pageSize - 1, rows.length);
    info.textContent = rows.length
      ? `${start.toLocaleString()}–${end.toLocaleString()} / ${rows.length.toLocaleString()}`
      : "0 / 0";
  }
  // Sync page size / hide-raw checkbox to current state
  const ps = document.getElementById("fl-page-size");
  if (ps && Number(ps.value) !== pageSize) ps.value = String(pageSize);
  const hr = document.getElementById("fl-hide-raw");
  if (hr && hr.checked !== tabEl._fleetHideRaw) hr.checked = tabEl._fleetHideRaw;
  // Cycle 42: detail close-all 버튼 visibility + count
  const closeAllBtn = document.getElementById("fl-close-all-details");
  const expCount = tabEl._fleetExpanded?.size || 0;
  if (closeAllBtn) {
    closeAllBtn.classList.toggle("hidden", expCount === 0);
    const cnt = document.getElementById("fl-close-all-count");
    if (cnt) cnt.textContent = String(expCount);
  }
  document.querySelectorAll("#fl-thead-row th[data-col]").forEach(h => {
    const m = h.querySelector("[data-sort-marker]");
    const isActive = h.dataset.col === st.sortCol;
    // Cycle 21: aria-sort 속성으로 sticky thead 강조 + 스크린리더 시그널
    if (isActive) h.setAttribute("aria-sort", st.sortDir === "asc" ? "ascending" : "descending");
    else h.removeAttribute("aria-sort");
    if (m) m.textContent = isActive ? (st.sortDir === "asc" ? "▲" : "▼") : "";
  });
  // Cycle 19: 현재 필터 상태 URL hash 동기화 (Supply 탭이 활성일 때만)
  try { _writeFleetUrl(); } catch (e) { /* ignore */ }
}

// Render pagination controls (jang1117 .pgn equivalent).
function _renderFleetPagination(total, page, pageSize, totalPages) {
  const host = document.getElementById("fl-pgn");
  if (!host) return;
  if (total === 0) {
    host.innerHTML = `<span class="text-slate-400">결과 없음</span>`;
    return;
  }
  // Cycle 25: 페이지네이션 polish — 처음/끝 버튼 + page X of Y 라벨
  const tabEl = document.getElementById("tab-fleet");
  const pages = [];
  const add = (n) => pages.push(n);
  add(1);
  if (page > 4) add("…");
  for (let p = Math.max(2, page - 2); p <= Math.min(totalPages - 1, page + 2); p++) add(p);
  if (page < totalPages - 3) add("…");
  if (totalPages > 1) add(totalPages);
  // Dedupe consecutive duplicates
  const uniq = [];
  for (const p of pages) if (uniq[uniq.length - 1] !== p) uniq.push(p);

  const btn = (label, target, disabled, active, title) =>
    `<button type="button" data-page="${target ?? ""}" ` +
    `class="px-2 py-0.5 rounded border ${active ? "border-blue-500 bg-blue-50 text-blue-700 font-semibold" : "border-slate-200 hover:bg-slate-50"} ${disabled ? "opacity-40 cursor-not-allowed" : ""}" ` +
    `${title ? `title="${title}"` : ""} ${disabled ? "disabled" : ""}>${label}</button>`;
  host.innerHTML =
    btn("⏮", 1, page <= 1, false, "처음 페이지") +
    btn("◀", page - 1, page <= 1, false, "이전 페이지") +
    uniq.map(p => p === "…"
      ? `<span class="px-1 text-slate-400">…</span>`
      : btn(p, p, false, p === page)).join("") +
    btn("▶", page + 1, page >= totalPages, false, "다음 페이지") +
    btn("⏭", totalPages, page >= totalPages, false, "마지막 페이지") +
    `<span class="px-2 text-[11px] font-mono text-slate-500 ml-2">page <strong>${page.toLocaleString()}</strong> / ${totalPages.toLocaleString()}</span>`;
  if (!host.dataset.bound) {
    host.dataset.bound = "1";
    host.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-page]");
      if (!b || b.disabled) return;
      const v = Number(b.dataset.page);
      if (!Number.isNaN(v) && v >= 1) {
        tabEl._fleetPage = v;
        _renderFleetView();
      }
    });
  }
}

function _renderFleetTable(rows, I, page = 1, pageSize = 100) {
  const body = document.getElementById("fl-tbody");
  if (!body) return;
  const start = (page - 1) * pageSize;
  const top = rows.slice(start, start + pageSize);
  // Cycle 30: 선박명 검색어 highlight 준비 — state.name 매치 부분에 <mark> 적용
  const tabEl = document.getElementById("tab-fleet");
  const nameQ = (tabEl?._fleetState?.name || "").trim();
  const hl = (s) => {
    const esc = _esc(s || "");
    if (!nameQ) return esc;
    const escQ = nameQ.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return esc.replace(new RegExp(`(${escQ})`, "ig"),
      '<mark class="bg-amber-200 text-slate-900 px-0.5 rounded">$1</mark>');
  };
  // Cycle 33: row 확장 상태 트래킹. set of "nama|tahun" keys
  if (!tabEl._fleetExpanded) tabEl._fleetExpanded = new Set();
  const exp = tabEl._fleetExpanded;
  const vKey = (r) => `${r[I.nama] || ""}|${r[I.tahun] || ""}`;
  // Cycle 12: 헤더 순서와 일치하도록 셀 순서 재정렬. raw 4개(엔진/엔진타입/IMO/Call Sign)는 dim 처리.
  body.innerHTML = top.map(r => {
    const flag = r[I.flag] || "Indonesia";
    const age = r[I.age];
    const yr = r[I.tahun];
    const k = vKey(r);
    const isOpen = exp.has(k);
    const expandArrow = isOpen ? "▼" : "▶";
    // Cycle 34: 빠른 필터 버튼 inline. data-fa-{field}=value 속성으로 카드 본문에 부착.
    const faBtn = (field, value, label) => value ? `
      <button type="button" data-fa-${field}="${_esc(value)}"
              class="fl-detail-action ml-1 text-[9px] px-1.5 py-0.5 rounded border border-blue-200 text-blue-700 hover:bg-blue-50"
              title="${_esc(label)} 만 필터링">→ 필터</button>` : "";
    // Cycle 35: owner total + class median 컨텍스트 텍스트 빌드
    const classStats = tabEl._fleetClassStats || {};
    const ownerTotals = tabEl._fleetOwnerTotals;
    const vc = r[I.vc] || "Other";
    const cs = classStats[vc] || null;
    const vGt = r[I.gt] || 0;
    // Cycle 35: % 표시는 ±200% 안쪽일 때만; 그 외엔 ×N 배수
    const classCtx = (cs && vGt > 0 && cs.median > 0) ? (() => {
      const ratio = vGt / cs.median;
      let label;
      if (ratio >= 3) label = `×${ratio.toFixed(1)} of median`;
      else if (ratio >= 0.5) label = `${((ratio - 1) * 100).toFixed(0)}% vs median`;
      else label = `${(ratio * 100).toFixed(0)}% of median`;
      return `<span class="text-[10px] opacity-70 ml-1">vs ${vc} median ${cs.median.toLocaleString()} (${label})</span>`;
    })() : "";
    const ownerOwn = r[I.owner];
    const oTot = (ownerTotals && ownerOwn) ? ownerTotals.get(ownerOwn) : null;
    const ownerCtx = oTot ? `<span class="text-[10px] opacity-70 ml-1">총 ${oTot.vessels.toLocaleString()}척 · GT ${fmtTon(oTot.sumGt)}</span>` : "";
    // Cycle 47: Tanker 선박 detail에 owner profile (tanker fleet 합계) 표시
    let tankerProfileHtml = "";
    if (isOpen && r[I.vc] === "Tanker" && tabEl._fleetOwnerProfile) {
      const op = tabEl._fleetOwnerProfile.get(r[I.owner]);
      if (op) {
        const mix = op.subclass_mix || {};
        const mixEntries = Object.entries(mix).sort((a, b) => b[1] - a[1]);
        const mixHtml = mixEntries.map(([k, v]) =>
          `<span class="inline-block px-1.5 py-0.5 mr-1 rounded bg-white border border-slate-200 text-[10px]">${_esc(k)} ${v.toLocaleString()}</span>`
        ).join("");
        const tickerChip = op.ticker
          ? `<span class="inline-block px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 text-[10px] font-mono ml-1" title="IDX 상장 티커">${_esc(op.ticker)}</span>`
          : "";
        tankerProfileHtml = `
          <div class="mt-3 pt-3 border-t border-slate-200">
            <div class="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">
              이 운영사의 Tanker fleet${tickerChip}
            </div>
            <div class="flex flex-wrap items-center gap-3 text-[11px]">
              <span><strong>${op.tankers.toLocaleString()}</strong> 척</span>
              <span class="text-slate-400">·</span>
              <span>합계 GT <strong>${(op.sum_gt || 0).toLocaleString()}</strong></span>
              <span class="text-slate-400">·</span>
              <span>평균 GT <strong>${(op.avg_gt || 0).toLocaleString()}</strong></span>
              <span class="text-slate-400">·</span>
              <span>max GT <strong>${(op.max_gt || 0).toLocaleString()}</strong></span>
            </div>
            <div class="mt-2 text-[11px]"><span class="opacity-70 mr-1">Subclass mix:</span>${mixHtml || '<em class="text-slate-400">없음</em>'}</div>
          </div>`;
      }
    }
    // Cycle 41: sister vessels — same owner의 다른 선박 top 5 (GT 내림차순)
    // Cycle 44: "더 보기" 토글로 전체 표시 가능
    let sisterListHtml = "";
    if (isOpen && r[I.owner] && tabEl._fleetVessels) {
      const ownerName = r[I.owner];
      const currentNama = r[I.nama];
      const allRows = tabEl._fleetVessels.rows;
      const siblings = [];
      for (const rr of allRows) {
        if (rr[I.owner] !== ownerName) continue;
        if (rr[I.nama] === currentNama && rr[I.tahun] === r[I.tahun]) continue;  // exclude self
        siblings.push(rr);
      }
      siblings.sort((a, b) => (b[I.gt] || 0) - (a[I.gt] || 0));
      if (!tabEl._fleetSistersExpanded) tabEl._fleetSistersExpanded = new Set();
      const showAll = tabEl._fleetSistersExpanded.has(k);
      const topSiblings = showAll ? siblings : siblings.slice(0, 5);
      if (topSiblings.length > 0) {
        const moreBtn = (siblings.length > 5) ? `
          <button type="button" class="fl-sister-toggle ml-2 text-[10px] px-2 py-0.5 rounded border border-slate-300 text-slate-600 hover:bg-slate-50"
                  data-sister-vk="${_esc(k)}">${showAll ? `상위 5만 보기` : `더 보기 (+${siblings.length - 5})`}</button>` : "";
        // Cycle 45: 전체 표시 시 max-height + overflow-y. 5만 표시는 grid 그대로.
        const gridWrap = showAll ? `style="max-height:300px;overflow-y:auto;padding:4px"` : "";
        sisterListHtml = `
          <div class="mt-3 pt-3 border-t border-slate-200">
            <div class="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2 flex items-center">
              <span>이 운영사의 다른 선박 (${topSiblings.length} of ${siblings.length}) — 클릭 시 점프</span>${moreBtn}
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 text-[11px]" ${gridWrap}>
              ${topSiblings.map(rr => {
                const sAge = rr[I.age];
                return `<button type="button" class="fl-sister-jump flex items-center gap-2 px-2 py-1 bg-white rounded border border-slate-200 hover:bg-blue-50 hover:border-blue-300 text-left transition-colors"
                                data-sister-nama="${_esc(rr[I.nama])}"
                                title="${_esc(rr[I.nama])} 로 점프 + 상세 펼치기">
                  <span class="font-semibold text-slate-800 truncate flex-1">${_esc(rr[I.nama])}</span>
                  <span class="font-mono text-slate-500 text-[10px]">GT ${(rr[I.gt]||0).toLocaleString()}</span>
                  <span class="font-mono text-[10px] ${sAge != null && sAge >= 25 ? 'text-rose-600 font-semibold' : 'text-slate-400'}">${rr[I.tahun] || '—'} · ${sAge != null ? sAge + 'y' : '—'}</span>
                  <span class="text-[10px] text-slate-400">${_esc(rr[I.vc])}</span>
                </button>`;
              }).join("")}
            </div>
          </div>`;
      }
    }
    const detailRow = isOpen ? `
      <tr class="fl-detail-row" data-vk="${_esc(k)}">
        <td colspan="14" class="px-4 py-3 bg-slate-50 border-b border-slate-200">
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px]">
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">선박명</span><span class="font-semibold">${_esc(r[I.nama])}</span></div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">선주</span><span>${_esc(r[I.owner])}</span>${faBtn("owner", r[I.owner], r[I.owner])}${ownerCtx}</div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">Sector</span><span>${_esc(r[I.sector])}</span></div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">Vessel Class</span><span>${_esc(r[I.vc])}</span>${faBtn("vc", r[I.vc], r[I.vc])}${classCtx}</div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">JenisDetailKet</span><span>${_esc(r[I.jenis])}</span>${faBtn("jenis", r[I.jenis], r[I.jenis])}</div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">Tanker Subclass</span><span>${_esc(r[I.ts]) || '—'}</span></div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">Scope</span><span>${_esc(r[I.scope])}</span></div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">국적</span><span>${_esc(flag)}</span>${faBtn("flag", flag, flag)}</div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">건조 / 선령</span><span class="font-mono ${age != null && age >= 25 ? 'text-rose-600 font-bold' : ''}">${yr || '—'} · ${age != null ? age + '년' : '—'}</span></div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">GT × LOA × W × D</span><span class="font-mono">${(r[I.gt]||0).toLocaleString()} · ${(r[I.loa]||0).toFixed(1)}m · ${(r[I.lebar]||0).toFixed(1)}m · ${(r[I.dalam]||0).toFixed(1)}m</span></div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">엔진</span><span class="font-mono">${_esc(r[I.mesin]) || '—'} <span class="opacity-60">/ ${_esc(r[I.mesin_type]) || '—'}</span></span></div>
            <div><span class="text-slate-500 font-mono uppercase text-[9px] mb-0.5 block">IMO / Call Sign</span><span class="font-mono">${(() => {
              const imo = r[I.imo];
              if (!imo || !/^\d{6,9}$/.test(String(imo).trim())) return _esc(imo) || '—';
              const cleanImo = String(imo).trim();
              return `<a href="https://www.equasis.org/EquasisWeb/restricted/Search?fs=ShipSearch&IMO=${encodeURIComponent(cleanImo)}" target="_blank" rel="noopener" class="text-blue-700 hover:underline" title="Equasis.org에서 IMO ${_esc(cleanImo)} 조회 (외부 사이트)">${_esc(cleanImo)} ↗</a>`;
            })()} / ${_esc(r[I.call_sign]) || '—'}</span></div>
          </div>
          ${tankerProfileHtml}
          ${sisterListHtml}
        </td>
      </tr>` : "";
    return `<tr class="hover:bg-slate-50 border-b border-slate-100 fl-vessel-row cursor-pointer" data-vk="${_esc(k)}">
      <td class="px-2 py-1 font-medium text-slate-800"><span class="text-slate-400 mr-1 text-[10px]">${expandArrow}</span>${hl(r[I.nama])}</td>
      <td class="px-2 py-1 text-slate-600">${_esc(r[I.owner])}</td>
      <td class="px-2 py-1">${_esc(r[I.jenis])}</td>
      <td class="px-2 py-1 text-[11px] text-slate-600">${_esc(flag)}</td>
      <td class="px-2 py-1 text-right font-mono">${(r[I.gt] || 0).toLocaleString()}</td>
      <td class="px-2 py-1 text-right font-mono">${(r[I.loa] || 0).toFixed(1)}</td>
      <td class="px-2 py-1 text-right font-mono">${(r[I.lebar] || 0).toFixed(1)}</td>
      <td class="px-2 py-1 text-right font-mono">${(r[I.dalam] || 0).toFixed(1)}</td>
      <td class="px-2 py-1 text-right">${yr || "—"}</td>
      <td class="px-2 py-1 text-right ${age != null && age >= 25 ? 'text-rose-600 font-semibold' : ''}">${age != null ? age : "—"}</td>
      <td class="px-2 py-1 text-[10px] text-slate-400 bg-slate-50/50">${_esc(r[I.mesin])}</td>
      <td class="px-2 py-1 text-[10px] text-slate-400 bg-slate-50/50">${_esc(r[I.mesin_type])}</td>
      <td class="px-2 py-1 text-[10px] text-slate-400 bg-slate-50/50 font-mono">${_esc(r[I.imo])}</td>
      <td class="px-2 py-1 text-[10px] text-slate-400 bg-slate-50/50 font-mono">${_esc(r[I.call_sign])}</td>
    </tr>${detailRow}`;
  }).join("");
  // Cycle 33: row click → toggle expand. Cycle 34: detail action buttons (owner/vc/jenis/flag 필터)
  if (!body.dataset.clickBound) {
    body.dataset.clickBound = "1";
    body.addEventListener("click", (e) => {
      const tabElX = document.getElementById("tab-fleet");
      // Cycle 44: sister "더 보기" 토글
      const sisToggle = e.target.closest(".fl-sister-toggle");
      if (sisToggle) {
        e.stopPropagation();
        const vk = sisToggle.dataset.sisterVk;
        const set = tabElX._fleetSistersExpanded || (tabElX._fleetSistersExpanded = new Set());
        if (set.has(vk)) set.delete(vk); else set.add(vk);
        _renderFleetView();
        return;
      }
      // Cycle 43: sister 점프 버튼 — 선박명으로 name filter 설정 + 자동 expand
      const sis = e.target.closest(".fl-sister-jump");
      if (sis) {
        e.stopPropagation();
        const nama = sis.dataset.sisterNama;
        if (!nama) return;
        const st = tabElX._fleetState;
        // 새 vessel로 점프: name filter set, 기존 expand 해제, 새 row 자동 expand
        st.name = nama;
        const ne = document.getElementById("fl-f-name"); if (ne) ne.value = nama;
        tabElX._fleetExpanded = new Set();
        // 정확히 같은 이름의 첫 row에서 vKey 생성해 expand
        const fv = tabElX._fleetVessels;
        const J = {}; fv.cols.forEach((c, i) => J[c] = i);
        const match = fv.rows.find(r => r[J.nama] === nama);
        if (match) {
          const key = `${match[J.nama] || ""}|${match[J.tahun] || ""}`;
          tabElX._fleetExpanded.add(key);
        }
        tabElX._fleetPage = 1;
        _renderFleetView();
        // 스크롤 to table top
        document.getElementById("fl-table")?.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      // Detail action button — fl-detail-action class
      const act = e.target.closest(".fl-detail-action");
      if (act) {
        e.stopPropagation();
        const st = tabElX._fleetState;
        if (act.dataset.faOwner) st.ownerExact = st.ownerExact === act.dataset.faOwner ? "" : act.dataset.faOwner;
        else if (act.dataset.faVc) st.vcFilter = st.vcFilter === act.dataset.faVc ? "" : act.dataset.faVc;
        else if (act.dataset.faJenis) {
          const v = act.dataset.faJenis;
          // Toggle jenis selection — if only this one is selected, clear; else replace with this
          if (st.jenis.size === 1 && st.jenis.has(v)) st.jenis.clear();
          else { st.jenis.clear(); st.jenis.add(v); }
          _renderFleetJenisList(tabElX._fleetVessels);
        } else if (act.dataset.faFlag) st.flagFilter = st.flagFilter === act.dataset.faFlag ? "" : act.dataset.faFlag;
        tabElX._fleetPage = 1;
        _renderFleetView();
        return;
      }
      // Row click → toggle expand
      const tr = e.target.closest("tr.fl-vessel-row");
      if (!tr) return;
      const setExp = tabElX._fleetExpanded || (tabElX._fleetExpanded = new Set());
      const key = tr.dataset.vk;
      if (setExp.has(key)) setExp.delete(key); else setExp.add(key);
      _renderFleetView();
    });
  }
}

function _esc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Cycle 39: JSON export — 적용 필터 메타데이터 + 데이터 배열
function _fleetJsonDownload() {
  const tabEl = document.getElementById("tab-fleet");
  const fv = tabEl._fleetVessels;
  if (!fv) return;
  const { rows, I } = _applyFleetFilters();
  const st = tabEl._fleetState;
  // 필터 메타데이터
  const filters = {};
  if (st.scopeOnly) filters.scope_only = st.scopeOnly;
  if (st.vcFilter) filters.vessel_class = st.vcFilter;
  if (st.flagFilter) filters.flag = st.flagFilter;
  if (st.ownerExact) filters.owner_exact = st.ownerExact;
  if (st.name) filters.name_substring = st.name;
  if (st.jenis.size) filters.jenis_detail_ket = { values: [...st.jenis], exclude: st.jenisExclude };
  if (st.yrMin != null) filters.tahun_min = st.yrMin;
  if (st.yrMax != null) filters.tahun_max = st.yrMax;
  if (st.gtMin != null) filters.gt_min = st.gtMin;
  if (st.gtMax != null) filters.gt_max = st.gtMax;
  if (st.loaMin != null) filters.loa_min = st.loaMin;
  if (st.loaMax != null) filters.loa_max = st.loaMax;
  if (st.widthMin != null) filters.width_min = st.widthMin;
  if (st.widthMax != null) filters.width_max = st.widthMax;
  if (st.depthMin != null) filters.depth_min = st.depthMin;
  if (st.depthMax != null) filters.depth_max = st.depthMax;
  if (scopeState.hideExcluded === false) filters.include_excluded = true;
  // 데이터 변환 (object 배열로)
  const data = rows.map(r => ({
    nama_kapal: r[I.nama],
    nama_pemilik: r[I.owner],
    sector: r[I.sector],
    vessel_class: r[I.vc],
    jenis_detail_ket: r[I.jenis],
    tanker_subclass: r[I.ts] || null,
    gt: r[I.gt],
    loa: r[I.loa],
    lebar: r[I.lebar],
    dalam: r[I.dalam],
    tahun: r[I.tahun],
    age: r[I.age],
    flag: r[I.flag] || "Indonesia",
    mesin: r[I.mesin] || null,
    mesin_type: r[I.mesin_type] || null,
    imo: r[I.imo] || null,
    call_sign: r[I.call_sign] || null,
    scope: r[I.scope],
  }));
  const meta = state.meta || {};
  const payload = {
    exported_at: new Date().toISOString(),
    source: "kapal.dephub.go.id (vessels snapshot)",
    snapshot_month: meta.latest_vessel_snapshot_month || null,
    build_at: meta.build_at || null,
    filters,
    total_rows_full: fv.rows.length,
    rows_in_export: data.length,
    data,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const date = new Date().toISOString().slice(0, 10);
  a.download = `fleet_${date}.json`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1500);
}

function _fleetCsvDownload() {
  const tabEl = document.getElementById("tab-fleet");
  const fv = tabEl._fleetVessels;
  if (!fv) return;
  const { rows, I } = _applyFleetFilters();
  // Cycle 16: 한국어/영어 헤더 토글. 사용자 체크박스 (default 한글) 기준.
  const koCheck = document.getElementById("fl-csv-ko");
  const useKorean = koCheck ? !!koCheck.checked : true;
  const FIELDS = [
    { en: "nama_kapal",       ko: "선박명",         key: "nama" },
    { en: "nama_pemilik",     ko: "선주",           key: "owner" },
    { en: "sector",           ko: "섹터",           key: "sector" },
    { en: "vessel_class",     ko: "선급",           key: "vc" },
    { en: "jenis_detail_ket", ko: "Vessel Type",    key: "jenis" },
    { en: "tanker_subclass",  ko: "탱커 subclass",  key: "ts" },
    { en: "gt",               ko: "GT",             key: "gt" },
    { en: "loa",              ko: "LOA (m)",        key: "loa" },
    { en: "lebar",            ko: "Width (m)",      key: "lebar" },
    { en: "dalam",            ko: "Depth (m)",      key: "dalam" },
    { en: "tahun",            ko: "건조연도",       key: "tahun" },
    { en: "age",              ko: "선령",           key: "age" },
    { en: "flag",             ko: "국적",           key: "flag" },
    { en: "mesin",            ko: "엔진",           key: "mesin" },
    { en: "mesin_type",       ko: "엔진 타입",      key: "mesin_type" },
    { en: "imo",              ko: "IMO",            key: "imo" },
    { en: "call_sign",        ko: "Call Sign",      key: "call_sign" },
  ];
  const header = FIELDS.map(f => useKorean ? f.ko : f.en);
  const lines = [header.map(h => /[",\n]/.test(h) ? `"${h.replace(/"/g, '""')}"` : h).join(",")];
  const cidx = FIELDS.map(f => I[f.key]);
  for (const r of rows) {
    lines.push(cidx.map(i => {
      const v = r[i];
      if (v == null) return "";
      const s = String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    }).join(","));
  }
  // BOM for Excel + UTF-8
  const blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  // Cycle 14: 파일명에 필터 컨텍스트 포함 — 다운로드 결과 출처 명확화.
  //   e.g. fleet_tanker_25plus_owner-PERTAMINA_2026-05-12.csv
  const st = tabEl._fleetState;
  const tokens = [];
  if (st.jenis.size) {
    const sample = Array.from(st.jenis)[0].replace(/[^A-Za-z0-9]/g, "");
    tokens.push((st.jenisExclude ? "not-" : "") + sample.toLowerCase() +
                (st.jenis.size > 1 ? `+${st.jenis.size - 1}` : ""));
  }
  if (st.yrMax != null) tokens.push(`built<=${st.yrMax}`);
  if (st.yrMin != null) tokens.push(`built>=${st.yrMin}`);
  if (st.gtMin != null) tokens.push(`gt>=${st.gtMin}`);
  if (st.gtMax != null) tokens.push(`gt<=${st.gtMax}`);
  if (st.ownerExact) tokens.push("owner-" + st.ownerExact.replace(/PT[.\s]*/i, "").replace(/[^A-Za-z0-9]/g, "").substring(0, 20));
  if (st.name) tokens.push("name-" + st.name.replace(/[^A-Za-z0-9]/g, "").substring(0, 20));
  if (!scopeState.hideExcluded) tokens.push("all-scope");
  const stub = tokens.length ? "_" + tokens.join("_") : "";
  const date = new Date().toISOString().slice(0, 10);
  a.download = `fleet${stub}_${date}.csv`.replace(/_{2,}/g, "_").substring(0, 180);
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1500);
}

// ────────────────────────────────────────────────────────────
// Cycle 9: Supply 탭 차트 디자인 통일.
//   - Primary palette: navy(#1A3A6B) — design system tokens
//   - Polar scope colors: cargo=navy, auxiliary=slate, excluded=stone
//   - Semantic alert: rose(#dc2626) for aged 25+, amber for warnings
// ────────────────────────────────────────────────────────────
const FL_PRIMARY    = "#1A3A6B";    // navy — design system
const FL_PRIMARY_F  = "rgba(26,58,107,0.18)";
const FL_AUXILIARY  = "#64748b";    // slate-500
const FL_EXCLUDED   = "#a8a29e";    // stone-400
const FL_ALERT      = "#dc2626";    // rose-600 — 25y+ 노후
const FL_WARN       = "#f59e0b";    // amber-500 — 20–24y
const FL_BLUE_SCALE = [
  [0.0,  "#dbeafe"], [0.25, "#93c5fd"],
  [0.55, "#3b82f6"], [1.0,  "#1A3A6B"],
];

function _drawFlChartYear(rows, I) {
  if (!document.getElementById("fl-ch-year")) return;
  const counts = new Map();
  for (const r of rows) {
    const y = r[I.tahun];
    if (y && y > 1900 && y < 2100) counts.set(y, (counts.get(y) || 0) + 1);
  }
  const years = [...counts.keys()].sort((a, b) => a - b);
  const ys = years.map(y => counts.get(y));
  Plotly.newPlot("fl-ch-year", [{
    x: years, y: ys,
    type: "scatter", mode: "lines", fill: "tozeroy",
    line: { color: FL_PRIMARY, width: 1.6, shape: "spline" },
    fillcolor: FL_PRIMARY_F,
    hovertemplate: "<b>%{x}</b><br>%{y:,} 척<extra></extra>",
  }], {
    margin: { t: 10, l: 40, r: 10, b: 30 },
    xaxis: { title: { text: "건조 연도", font: { size: 10 } }, tickfont: { size: 10 },
             showgrid: false },
    yaxis: { title: { text: "척수", font: { size: 10 } }, tickfont: { size: 10 },
             gridcolor: "#eef2f7" },
    plot_bgcolor: "white", paper_bgcolor: "white",
  }, { displayModeBar: false, responsive: true });
}

function _drawFlChartType(rows, I) {
  if (!document.getElementById("fl-ch-type")) return;
  // Cycle 9: scope별 색상 분기. cargo는 navy, auxiliary(Tug)는 slate, excluded는 stone.
  // fleet_vessels.json totals.by_jenis 에 scope 메타가 있음.
  const fv = document.getElementById("tab-fleet")._fleetVessels;
  const byJenis = (fv && fv.totals && fv.totals.by_jenis) || {};
  const counts = new Map();
  for (const r of rows) {
    const j = r[I.jenis] || "(blank)";
    counts.set(j, (counts.get(j) || 0) + 1);
  }
  // Cycle 26: 전체 보기 토글
  const showAll = document.getElementById("fl-type-show-all")?.checked || false;
  const limit = showAll ? 999 : 15;
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit);
  const totalShown = top.length;
  const titleEl = document.getElementById("fl-type-title");
  if (titleEl) {
    titleEl.textContent = showAll
      ? `Vessel Type ALL (${totalShown.toLocaleString()})`
      : `Vessel Type TOP 15`;
  }
  const labels = top.map(t => t[0]).reverse();
  const ys = top.map(t => t[1]).reverse();
  const SCOPE_COLOR = {
    cargo: FL_PRIMARY, auxiliary: FL_AUXILIARY,
    excluded: FL_EXCLUDED, unclassified: FL_ALERT,
  };
  const colors = labels.map(lbl => {
    const scope = (byJenis[lbl] && byJenis[lbl].scope) || "cargo";
    return SCOPE_COLOR[scope] || FL_PRIMARY;
  });
  // Cycle 26: showAll 시 chart height 증가 (rows × ~18px). 부모 컨테이너 height inline 설정.
  const chartEl = document.getElementById("fl-ch-type");
  if (chartEl && showAll) {
    chartEl.style.height = Math.max(280, totalShown * 18) + "px";
  } else if (chartEl) {
    chartEl.style.height = "280px";
  }
  Plotly.newPlot("fl-ch-type", [{
    x: ys, y: labels, type: "bar", orientation: "h",
    marker: { color: colors, line: { color: "#fff", width: 0.5 } },
    text: ys.map(v => v.toLocaleString()),
    textposition: "outside",
    cliponaxis: false,
    hovertemplate: "<b>%{y}</b><br>%{x:,} 척<extra>클릭 시 필터</extra>",
  }], {
    margin: { t: 5, l: 140, r: 50, b: 30 },
    xaxis: { tickfont: { size: 10 }, gridcolor: "#eef2f7" },
    yaxis: { tickfont: { size: 10 } },
    plot_bgcolor: "white", paper_bgcolor: "white",
  }, { displayModeBar: false, responsive: true });
  // Click-to-filter on Vessel Type bars. Cycle 18: re-bind every render.
  const host = document.getElementById("fl-ch-type");
  if (host) {
    host.removeAllListeners?.("plotly_click");
    host.on("plotly_click", (ev) => {
      const lbl = ev?.points?.[0]?.y;
      if (!lbl) return;
      const st = document.getElementById("tab-fleet")._fleetState;
      if (st.jenis.has(lbl)) st.jenis.delete(lbl); else st.jenis.add(lbl);
      _renderFleetJenisList(document.getElementById("tab-fleet")._fleetVessels);
      _renderFleetView();
    });
  }
}

function _drawFlChartEngineType(rows, I) {
  if (!document.getElementById("fl-ch-engine-type")) return;
  const counts = new Map();
  for (const r of rows) {
    let t = (r[I.mesin_type] || "").trim();
    if (!t || t === "|" || t === "||") continue;       // dummy placeholders
    counts.set(t, (counts.get(t) || 0) + 1);
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  if (!top.length) {
    Plotly.purge("fl-ch-engine-type");
    document.getElementById("fl-ch-engine-type").innerHTML =
      `<div class="text-xs text-slate-400 p-4 text-center">엔진 타입 데이터 없음</div>`;
    return;
  }
  Plotly.newPlot("fl-ch-engine-type", [{
    labels: top.map(t => t[0]),
    values: top.map(t => t[1]),
    type: "pie", hole: 0.55,
    textinfo: "percent",
    textposition: "inside",
    hovertemplate: "<b>%{label}</b><br>%{value:,} 척 (%{percent})<extra></extra>",
    marker: { line: { color: "#fff", width: 1 } },
  }], {
    margin: { t: 5, l: 5, r: 5, b: 30 },
    showlegend: true,
    legend: { font: { size: 9 }, orientation: "h", y: -0.15 },
  }, { displayModeBar: false, responsive: true });
}

function _drawFlChartEngineName(rows, I) {
  if (!document.getElementById("fl-ch-engine-name")) return;
  const counts = new Map();
  for (const r of rows) {
    let n = (r[I.mesin] || "").trim();
    if (!n) continue;
    // Collapse "BRAND|BRAND" multi-engine duplicates to first token
    n = n.split("|")[0].trim();
    if (!n) continue;
    counts.set(n, (counts.get(n) || 0) + 1);
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  if (!top.length) {
    Plotly.purge("fl-ch-engine-name");
    document.getElementById("fl-ch-engine-name").innerHTML =
      `<div class="text-xs text-slate-400 p-4 text-center">엔진명 데이터 없음</div>`;
    return;
  }
  const labels = top.map(t => t[0]).reverse();
  const ys = top.map(t => t[1]).reverse();
  Plotly.newPlot("fl-ch-engine-name", [{
    x: ys, y: labels, type: "bar", orientation: "h",
    marker: {
      color: ys,
      colorscale: "Greens", cmin: 0,
      line: { color: "#1e293b", width: 0.3 },
    },
    text: ys.map(v => v.toLocaleString()),
    textposition: "outside",
    cliponaxis: false,
    hovertemplate: "<b>%{y}</b><br>%{x:,} 척<extra></extra>",
  }], {
    margin: { t: 5, l: 100, r: 50, b: 30 },
    xaxis: { tickfont: { size: 10 } },
    yaxis: { tickfont: { size: 9 } },
  }, { displayModeBar: false, responsive: true });
}

function _drawFlChartFlag(rows, I) {
  if (!document.getElementById("fl-ch-flag")) return;
  const counts = new Map();
  for (const r of rows) {
    const f = r[I.flag] || "Indonesia";
    counts.set(f, (counts.get(f) || 0) + 1);
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  const labels = top.map(t => t[0]).reverse();
  const ys = top.map(t => t[1]).reverse();
  // Cycle 9: Indonesia 1척만 압도적이라 색 분기 — 자국기는 navy, 외국기는 slate.
  const colors = labels.map(l => l === "Indonesia" ? FL_PRIMARY : FL_AUXILIARY);
  Plotly.newPlot("fl-ch-flag", [{
    x: ys, y: labels, type: "bar", orientation: "h",
    marker: { color: colors, line: { color: "#fff", width: 0.5 } },
    text: ys.map(v => v.toLocaleString()),
    textposition: "outside",
    cliponaxis: false,
    hovertemplate: "<b>%{y}</b><br>%{x:,} 척<extra>클릭 시 국적 필터</extra>",
  }], {
    margin: { t: 5, l: 90, r: 50, b: 30 },
    xaxis: { tickfont: { size: 10 }, gridcolor: "#eef2f7", type: "log" },
    yaxis: { tickfont: { size: 10 } },
    plot_bgcolor: "white", paper_bgcolor: "white",
  }, { displayModeBar: false, responsive: true });
  // Cycle 18: Flag chart 클릭 → flagFilter 적용. Plotly.newPlot 시마다 re-bind.
  //   Plotly v2.35는 newPlot 시 기존 .on() 핸들러를 제거하므로 매번 재등록.
  const flagHost = document.getElementById("fl-ch-flag");
  if (flagHost) {
    flagHost.removeAllListeners?.("plotly_click");
    flagHost.on("plotly_click", (ev) => {
      const lbl = ev?.points?.[0]?.y;
      if (!lbl) return;
      const tabEl = document.getElementById("tab-fleet");
      const st = tabEl._fleetState;
      st.flagFilter = st.flagFilter === lbl ? null : lbl;
      tabEl._fleetPage = 1;
      _renderFleetView();
    });
  }
}

// Cycle 15: GT log histogram → class별 boxplot. p25/median/p75/whisker 통계로 교체.
//   class별로 GT 분포 (median 막대 + IQR + outliers).
function _drawFlChartGtHist(rows, I) {
  if (!document.getElementById("fl-ch-gt-hist")) return;
  const CLASS_ORDER = [
    "Other Cargo", "General Cargo", "Tanker",
    "Bulk Carrier", "Container", "Tug/OSV/AHTS",
  ];
  const byClass = new Map();
  for (const r of rows) {
    const g = r[I.gt];
    if (!g || g <= 0) continue;
    let cls = r[I.vc] || "Other";
    if (!CLASS_ORDER.includes(cls)) cls = "Other";
    if (!byClass.has(cls)) byClass.set(cls, []);
    byClass.get(cls).push(g);
  }
  // 표시할 class만 (rows 가 있는 것)
  const classes = CLASS_ORDER.filter(c => byClass.has(c));
  if (classes.includes("Other") === false && byClass.has("Other")) classes.push("Other");
  if (!classes.length) { Plotly.purge("fl-ch-gt-hist"); return; }
  const colorMap = {
    "Other Cargo":     "#65a30d",
    "General Cargo":   "#0891b2",
    "Tanker":          FL_PRIMARY,
    "Bulk Carrier":    "#7c3aed",
    "Container":       "#0284c7",
    "Tug/OSV/AHTS":    FL_AUXILIARY,
    "Other":           "#94a3b8",
  };
  const traces = classes.map(cls => ({
    name: cls,
    y: byClass.get(cls),
    type: "box",
    marker: { color: colorMap[cls] || FL_PRIMARY, size: 3, opacity: 0.4 },
    line: { color: colorMap[cls] || FL_PRIMARY, width: 1 },
    fillcolor: (colorMap[cls] || FL_PRIMARY) + "30",
    boxpoints: "outliers",
    hovertemplate: `<b>${cls}</b><br>GT %{y:,.0f}<extra></extra>`,
  }));
  Plotly.newPlot("fl-ch-gt-hist", traces, {
    margin: { t: 10, l: 50, r: 10, b: 50 },
    showlegend: false,
    xaxis: { tickfont: { size: 9 }, automargin: true, tickangle: -25 },
    yaxis: {
      type: "log", title: { text: "GT (log)", font: { size: 10 } },
      tickfont: { size: 10 }, gridcolor: "#eef2f7",
    },
    plot_bgcolor: "white", paper_bgcolor: "white",
  }, { displayModeBar: false, responsive: true });

  // Cycle 23: GT 전체 통계 (필터 결과). p25, median, p75, max
  const allGts = [];
  for (const arr of byClass.values()) for (const v of arr) allGts.push(v);
  allGts.sort((a, b) => a - b);
  const quantile = (arr, q) => {
    if (!arr.length) return null;
    const pos = (arr.length - 1) * q;
    const lo = Math.floor(pos), hi = Math.ceil(pos);
    if (lo === hi) return arr[lo];
    return arr[lo] * (hi - pos) + arr[hi] * (pos - lo);
  };
  const p25 = quantile(allGts, 0.25);
  const p50 = quantile(allGts, 0.50);
  const p75 = quantile(allGts, 0.75);
  const max = allGts.length ? allGts[allGts.length - 1] : null;
  const statsHost = document.getElementById("fl-gt-stats");
  if (statsHost) {
    const fmtGt = (v) => v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: 0 });
    statsHost.innerHTML = `
      <div class="bg-slate-50 rounded px-2 py-1 text-center"><div class="text-slate-400 text-[9px] uppercase">p25</div><div>${fmtGt(p25)}</div></div>
      <div class="bg-slate-50 rounded px-2 py-1 text-center"><div class="text-slate-400 text-[9px] uppercase">median</div><div class="font-semibold text-slate-800">${fmtGt(p50)}</div></div>
      <div class="bg-slate-50 rounded px-2 py-1 text-center"><div class="text-slate-400 text-[9px] uppercase">p75</div><div>${fmtGt(p75)}</div></div>
      <div class="bg-slate-50 rounded px-2 py-1 text-center"><div class="text-slate-400 text-[9px] uppercase">max</div><div>${fmtGt(max)}</div></div>`;
  }
}

// Cycle 9: 선령 분포 차트 (5년 buckets). 25년+은 알림 색상으로 강조.
//   <5y / 5–10y / 10–15y / 15–20y / 20–25y / 25–30y / 30y+
function _drawFlChartAge(rows, I) {
  if (!document.getElementById("fl-ch-age")) return;
  const BUCKETS = [
    { key: "<5",    lo: 0,  hi: 5  },
    { key: "5–10",  lo: 5,  hi: 10 },
    { key: "10–15", lo: 10, hi: 15 },
    { key: "15–20", lo: 15, hi: 20 },
    { key: "20–25", lo: 20, hi: 25 },
    { key: "25–30", lo: 25, hi: 30 },
    { key: "30+",   lo: 30, hi: 999 },
  ];
  const counts = BUCKETS.map(() => 0);
  let totalCounted = 0;
  // Cycle 23: GT 가중 평균 선령 계산 — 화물 capacity 가중 기준
  let sumAgeGt = 0, sumGtA = 0;
  for (const r of rows) {
    const age = r[I.age];
    if (age == null || age < 0) continue;
    for (let i = 0; i < BUCKETS.length; i++) {
      if (age >= BUCKETS[i].lo && age < BUCKETS[i].hi) {
        counts[i] += 1; totalCounted += 1; break;
      }
    }
    const gt = r[I.gt] || 0;
    if (gt > 0) { sumAgeGt += age * gt; sumGtA += gt; }
  }
  const avgAgeWeighted = sumGtA > 0 ? (sumAgeGt / sumGtA) : null;
  const labels = BUCKETS.map(b => b.key);
  const colors = BUCKETS.map(b =>
    b.lo >= 25 ? FL_ALERT :       // 25y+ 노후 — 빨강
    b.lo >= 20 ? FL_WARN  :       // 20–25y 경계 — 앰버
    FL_PRIMARY                    // 청정 — 네이비
  );
  const pcts = counts.map(c => totalCounted > 0 ? (c / totalCounted * 100) : 0);
  // Cycle 10: 누적 % 보조선. 25년+ 비중을 한눈에 식별.
  const cumPcts = [];
  let cum = 0;
  for (const p of pcts) { cum += p; cumPcts.push(cum); }
  Plotly.newPlot("fl-ch-age", [
    {
      name: "척수",
      x: labels, y: counts, type: "bar",
      marker: { color: colors, line: { color: "#fff", width: 0.5 } },
      text: counts.map((c, i) => c > 0 ? `${c.toLocaleString()}<br><span style="font-size:9px;opacity:.7">${pcts[i].toFixed(1)}%</span>` : ""),
      textposition: "outside",
      cliponaxis: false,
      hovertemplate: "<b>%{x}년</b><br>%{y:,} 척 (%{customdata:.1f}%)<extra>클릭 시 yrMax 필터</extra>",
      customdata: pcts,
    },
    {
      name: "누적 %",
      x: labels, y: cumPcts,
      type: "scatter", mode: "lines+markers",
      yaxis: "y2",
      line: { color: "#475569", width: 1.4, dash: "dot" },
      marker: { color: "#475569", size: 5 },
      hovertemplate: "<b>%{x}년까지 누적</b><br>%{y:.1f}%<extra></extra>",
    }
  ], {
    margin: { t: 30, l: 40, r: 45, b: 35 },
    showlegend: true,
    legend: { font: { size: 9 }, orientation: "h", y: 1.18, x: 0 },
    xaxis: { title: { text: "선령 (년)", font: { size: 10 } }, tickfont: { size: 10 } },
    yaxis: { title: { text: "척수", font: { size: 10 } }, tickfont: { size: 10 },
             gridcolor: "#eef2f7" },
    yaxis2: { title: { text: "누적 %", font: { size: 10 } }, overlaying: "y",
              side: "right", tickfont: { size: 10 }, showgrid: false,
              range: [0, 105], ticksuffix: "%" },
    // Cycle 23: GT 가중 평균 선령 annotation — 분포 안 평균 위치 표시
    annotations: avgAgeWeighted != null ? [
      {
        xref: "x", yref: "paper",
        x: (() => {
          // 평균 연령이 속하는 bucket 인덱스로 x 좌표 변환
          for (let i = 0; i < BUCKETS.length; i++) {
            if (avgAgeWeighted >= BUCKETS[i].lo && avgAgeWeighted < BUCKETS[i].hi) return BUCKETS[i].key;
          }
          return BUCKETS[BUCKETS.length - 1].key;
        })(),
        y: 1.05,
        text: `GT 가중 평균 ${avgAgeWeighted.toFixed(1)}년`,
        showarrow: true, arrowhead: 0, arrowwidth: 1, arrowcolor: "#475569",
        ax: 0, ay: -22,
        font: { size: 9, color: "#475569" },
        bgcolor: "rgba(255,255,255,0.85)",
        bordercolor: "#cbd5e1", borderwidth: 1, borderpad: 2,
      },
    ] : [],
    plot_bgcolor: "white", paper_bgcolor: "white",
  }, { displayModeBar: false, responsive: true });
  // Cycle 15: 막대 클릭 시 해당 bucket 이상 노후만 보기. Cycle 18: re-bind every render.
  const host = document.getElementById("fl-ch-age");
  if (host) {
    host.removeAllListeners?.("plotly_click");
    host.on("plotly_click", (ev) => {
      const pt = ev?.points?.[0];
      if (!pt || pt.curveNumber !== 0) return;  // 누적선 트레이스 무시
      const lbl = pt.x;
      const bucket = BUCKETS.find(b => b.key === lbl);
      if (!bucket) return;
      const tabEl = document.getElementById("tab-fleet");
      const st = tabEl._fleetState;
      const cutoff = new Date().getFullYear() - bucket.lo;
      // 토글: 같은 값이면 해제
      if (st.yrMax === cutoff) {
        st.yrMax = null;
        const inp = document.getElementById("fl-f-yr-max"); if (inp) inp.value = "";
      } else {
        st.yrMax = cutoff;
        const inp = document.getElementById("fl-f-yr-max"); if (inp) inp.value = String(cutoff);
      }
      tabEl._fleetPage = 1;
      _renderFleetView();
    });
  }
}

// Cycle 9: GT 규모별 분포 (의미 있는 카테고리 막대).
//   소형 <500 / 중형 500–5,000 / 대형 5,000–25,000 / 초대형 25,000+
function _drawFlChartGtBucket(rows, I) {
  if (!document.getElementById("fl-ch-gt-bucket")) return;
  const BUCKETS = [
    { key: "소형 (<500)",          lo: 0,     hi: 500    },
    { key: "중형 (500–5k)",        lo: 500,   hi: 5000   },
    { key: "대형 (5k–25k)",        lo: 5000,  hi: 25000  },
    { key: "초대형 (25k+)",        lo: 25000, hi: Infinity },
  ];
  const counts = BUCKETS.map(() => 0);
  const sumGt  = BUCKETS.map(() => 0);
  let totalCounted = 0, totalGt = 0;
  for (const r of rows) {
    const g = r[I.gt];
    if (!g || g <= 0) continue;
    for (let i = 0; i < BUCKETS.length; i++) {
      if (g >= BUCKETS[i].lo && g < BUCKETS[i].hi) {
        counts[i] += 1; sumGt[i] += g;
        totalCounted += 1; totalGt += g; break;
      }
    }
  }
  const labels = BUCKETS.map(b => b.key);
  const pcts = counts.map(c => totalCounted > 0 ? (c / totalCounted * 100) : 0);
  const gtShares = sumGt.map(s => totalGt > 0 ? (s / totalGt * 100) : 0);
  const colors = ["#cbd5e1", "#93c5fd", "#3b82f6", FL_PRIMARY];  // light → navy
  Plotly.newPlot("fl-ch-gt-bucket", [
    {
      name: "척수",
      x: labels, y: counts, type: "bar", yaxis: "y",
      marker: { color: colors, line: { color: "#fff", width: 0.5 } },
      text: counts.map((c, i) => c > 0 ? `${c.toLocaleString()}` : ""),
      textposition: "outside",
      cliponaxis: false,
      hovertemplate: "<b>%{x}</b><br>%{y:,} 척 (%{customdata:.1f}%)<extra>클릭 시 GT 범위 필터</extra>",
      customdata: pcts,
    },
    {
      name: "GT 점유 %",
      x: labels, y: gtShares, type: "scatter", mode: "lines+markers",
      yaxis: "y2",
      line: { color: FL_ALERT, width: 1.6, dash: "dot" },
      marker: { color: FL_ALERT, size: 7 },
      hovertemplate: "<b>%{x}</b><br>GT 점유 %{y:.1f}%<extra></extra>",
    }
  ], {
    margin: { t: 30, l: 40, r: 50, b: 35 },
    showlegend: true,
    legend: { font: { size: 9 }, orientation: "h", y: 1.18, x: 0 },
    xaxis: { tickfont: { size: 10 } },
    yaxis: { title: { text: "척수", font: { size: 10 } }, tickfont: { size: 10 },
             gridcolor: "#eef2f7" },
    yaxis2: { title: { text: "GT 점유 %", font: { size: 10 } }, overlaying: "y",
              side: "right", tickfont: { size: 10 }, showgrid: false,
              rangemode: "tozero", ticksuffix: "%" },
    plot_bgcolor: "white", paper_bgcolor: "white",
  }, { displayModeBar: false, responsive: true });
  // Cycle 17: 막대 클릭 → gtMin/gtMax 필터. Cycle 18: re-bind every render.
  const gtHost = document.getElementById("fl-ch-gt-bucket");
  if (gtHost) {
    gtHost.removeAllListeners?.("plotly_click");
    gtHost.on("plotly_click", (ev) => {
      const pt = ev?.points?.[0];
      if (!pt || pt.curveNumber !== 0) return;  // 점유율 line 무시
      const lbl = pt.x;
      const bucket = BUCKETS.find(b => b.key === lbl);
      if (!bucket) return;
      const tabEl = document.getElementById("tab-fleet");
      const st = tabEl._fleetState;
      const newMin = bucket.lo;
      const newMax = isFinite(bucket.hi) ? bucket.hi : null;
      const inMin = document.getElementById("fl-f-gt-min");
      const inMax = document.getElementById("fl-f-gt-max");
      if (st.gtMin === newMin && st.gtMax === newMax) {
        st.gtMin = null; st.gtMax = null;
        if (inMin) inMin.value = ""; if (inMax) inMax.value = "";
      } else {
        st.gtMin = newMin; st.gtMax = newMax;
        if (inMin) inMin.value = String(newMin);
        if (inMax) inMax.value = newMax != null ? String(newMax) : "";
      }
      tabEl._fleetPage = 1;
      _renderFleetView();
    });
  }
}

// Cycle 9: Top 운영사 카드.
//   fleet_owners.json (전체 cargo fleet 기준 사전계산) + 현 필터의 척수 cross-check.
//   필터가 활성화되어 있으면 "현재 필터 적용" 알림 + 필터된 rows에서 재계산.
function _drawFleetTopOwners(rows, I) {
  const host = document.getElementById("fl-top-owners");
  if (!host) return;
  const tabEl = document.getElementById("tab-fleet");
  const ownerPayload = tabEl._fleetOwners;

  // 현재 rows 기준으로 owner 재계산. 필터 활성 여부 무관하게 always-fresh.
  const acc = new Map();
  for (const r of rows) {
    const owner = (r[I.owner] || "").trim();
    if (!owner) continue;
    const gt = r[I.gt] || 0;
    const age = r[I.age];
    const cls = r[I.vc] || "Other";
    const ent = acc.get(owner) || { owner, vessels: 0, sum_gt: 0,
                                     age_weight: 0, gt_weight: 0,
                                     class_mix: {} };
    ent.vessels += 1;
    ent.sum_gt += gt;
    if (gt > 0 && age != null) { ent.age_weight += age * gt; ent.gt_weight += gt; }
    ent.class_mix[cls] = (ent.class_mix[cls] || 0) + 1;
    acc.set(owner, ent);
  }
  // Cycle 22: sort 선택 — 척수 / 선대 GT / 평균선령(GT 가중)
  const sortMode = (document.getElementById("fl-owner-sort")?.value) || "vessels";
  const sorted = [...acc.values()].sort((a, b) => {
    if (sortMode === "gt") return b.sum_gt - a.sum_gt;
    if (sortMode === "age") {
      const aA = a.gt_weight > 0 ? a.age_weight / a.gt_weight : -1;
      const bA = b.gt_weight > 0 ? b.age_weight / b.gt_weight : -1;
      return bA - aA;
    }
    return b.vessels - a.vessels;
  });
  const top = sorted.slice(0, 10);
  // Cycle 51: 시장 구조 신호 — Top 5/10/All GT 합산 + 점유율
  const totalGt = sorted.reduce((s, o) => s + (o.sum_gt || 0), 0);
  const top5Gt = sorted.slice(0, 5).reduce((s, o) => s + (o.sum_gt || 0), 0);
  const top10Gt = sorted.slice(0, 10).reduce((s, o) => s + (o.sum_gt || 0), 0);
  const top5Pct = totalGt > 0 ? (top5Gt / totalGt * 100) : 0;
  const top10Pct = totalGt > 0 ? (top10Gt / totalGt * 100) : 0;
  const ownersCount = sorted.length;
  // Cycle 52: HHI (Herfindahl-Hirschman Index) — sum of (share_%)². [0, 10000]
  //   KPPU 임계점: <1500 분산 / 1500-2500 중간 / >2500 집중
  let hhi = 0;
  if (totalGt > 0) {
    for (const o of sorted) {
      const sharePct = (o.sum_gt || 0) / totalGt * 100;
      hhi += sharePct * sharePct;
    }
  }
  const hhiLabel = hhi < 1500 ? "분산" : hhi < 2500 ? "중간" : "집중";
  const hhiCls = hhi < 1500 ? "text-emerald-700" : hhi < 2500 ? "text-amber-700" : "text-rose-700";
  if (!top.length) {
    host.innerHTML = `<div class="text-slate-400 text-[11px] p-4 text-center">필터 결과 운영사 없음</div>`;
    return;
  }
  const maxV = Math.max(...top.map(o => o.vessels));
  const maxGt = Math.max(...top.map(o => o.sum_gt));

  // class mix 색상 (작은 dot 묶음)
  const CLS_COLOR = {
    "Container":         "#0284c7",
    "Bulk Carrier":      "#7c3aed",
    "Tanker":            "#1A3A6B",
    "General Cargo":     "#0891b2",
    "Other Cargo":       "#65a30d",
    "Passenger Ship":    "#0d9488",
    "Ferry":             "#14b8a6",
    "Fishing Vessel":    "#d97706",
    "Tug/OSV/AHTS":      "#64748b",
    "Dredger/Special":   "#a8a29e",
    "Government/Navy/Other": "#6b7280",
    "UNMAPPED":          "#dc2626",
    "Other":             "#94a3b8",
  };

  // Class 라벨 약어 — 좁은 셀에 들어가도록 짧게.
  const CLS_LABEL = {
    "Container":             "Container",
    "Bulk Carrier":          "Bulk",
    "Tanker":                "Tanker",
    "General Cargo":         "GenCargo",
    "Other Cargo":           "Other",
    "Passenger Ship":        "Passenger",
    "Ferry":                 "Ferry",
    "Fishing Vessel":        "Fishing",
    "Tug/OSV/AHTS":          "Tug/OSV",
    "Dredger/Special":       "Dredger",
    "Government/Navy/Other": "Gov/Navy",
    "UNMAPPED":              "UNMAPPED",
    "Other":                 "Other",
  };

  host.innerHTML = `
    <div class="grid grid-cols-12 gap-2 text-[10px] font-mono uppercase tracking-wider text-slate-500 px-2 py-1 border-b border-slate-100">
      <div class="col-span-1 text-right">#</div>
      <div class="col-span-3">운영사</div>
      <div class="col-span-2 text-right">척수</div>
      <div class="col-span-2 text-right">선대 GT</div>
      <div class="col-span-1 text-right">평균<br>선령</div>
      <div class="col-span-3">선종 mix (top 3)</div>
    </div>
    ${top.map((o, idx) => {
      const avgAge = o.gt_weight > 0 ? (o.age_weight / o.gt_weight) : null;
      const vPct = (o.vessels / maxV * 100).toFixed(1);
      const gtPct = (o.sum_gt / maxGt * 100).toFixed(1);
      const totalClass = Object.values(o.class_mix).reduce((a, b) => a + b, 0);
      const sortedClasses = Object.entries(o.class_mix).sort((a, b) => b[1] - a[1]);
      // 상위 3 class 라벨 (chip 스타일). 나머지는 + N개.
      const top3 = sortedClasses.slice(0, 3);
      const extra = sortedClasses.length - 3;
      const labelHtml = top3.map(([k, v]) => {
        const c = CLS_COLOR[k] || "#94a3b8";
        const lbl = CLS_LABEL[k] || k;
        const pct = (v / totalClass * 100).toFixed(0);
        return `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-50 border border-slate-200 mr-1 mb-0.5 text-[10px] whitespace-nowrap"
                       title="${_esc(k)} · ${v.toLocaleString()}척 (${pct}%)">
          <span class="inline-block w-1.5 h-1.5 rounded-full" style="background:${c}"></span>
          <span class="text-slate-700">${lbl}</span>
          <span class="text-slate-400 font-mono">${pct}%</span>
        </span>`;
      }).join("");
      const extraHtml = extra > 0 ?
        `<span class="text-[10px] text-slate-400 align-middle">+${extra}</span>` : "";
      // Cycle 12: Top 1-3 메달 강조 (gold/silver/bronze 도트). 4위 이하는 일반 숫자.
      const MEDAL = ["#fbbf24", "#94a3b8", "#a16207"]; // gold / silver / bronze
      const rankBadge = idx < 3
        ? `<span class="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold text-white"
                  style="background:${MEDAL[idx]}" title="Top ${idx + 1}">${idx + 1}</span>`
        : `<span class="font-mono text-[10px] text-slate-400">${idx + 1}</span>`;
      // Cycle 16: hover tooltip detail — 평균선령 + 척수 + 모든 class breakdown
      const classDetail = sortedClasses
        .map(([k, v]) => `${k}: ${v.toLocaleString()}척`)
        .join(" / ");
      const idxNote = _ownerIsIdxListed(o.owner) ? "\n· IDX 상장사" : "";
      const tooltip = `${o.owner}\n· 척수: ${o.vessels.toLocaleString()}\n· 선대 GT: ${o.sum_gt.toLocaleString()}\n· 평균선령: ${avgAge != null ? avgAge.toFixed(1) + '년' : '—'}\n· 선종 mix: ${classDetail}${idxNote}\n\n클릭 시 이 운영사로 필터`;
      return `
        <div class="grid grid-cols-12 gap-2 items-center px-2 py-1.5 hover:bg-slate-50 border-b border-slate-50 transition-colors"
             data-owner-row="${_esc(o.owner)}" title="${_esc(tooltip)}">
          <div class="col-span-1 text-right">${rankBadge}</div>
          <div class="col-span-3 truncate text-slate-800 text-[12px] flex items-center gap-1" title="${_esc(o.owner)}${_ownerIdxTicker(o.owner) ? ' · IDX ' + _ownerIdxTicker(o.owner) : ''}">
            <span class="truncate">${_esc(o.owner)}</span>
            ${(() => {
              const t = _ownerIdxTicker(o.owner);
              if (!t) return '';
              return `<span class="inline-block px-1 py-px text-[8px] font-mono rounded bg-blue-100 text-blue-700 flex-shrink-0" title="IDX 상장사 — 티커 ${_esc(t)}">${_esc(t)}</span>`;
            })()}
          </div>
          <div class="col-span-2 text-right font-mono">
            <div class="text-[11px]">${o.vessels.toLocaleString()}</div>
            <div class="h-1 rounded bg-slate-100 mt-0.5">
              <div class="h-1 rounded" style="width:${vPct}%;background:${FL_PRIMARY}"></div>
            </div>
          </div>
          <div class="col-span-2 text-right font-mono">
            <div class="text-[11px]">${fmtTon(o.sum_gt)}</div>
            <div class="h-1 rounded bg-slate-100 mt-0.5">
              <div class="h-1 rounded" style="width:${gtPct}%;background:#3b82f6"></div>
            </div>
          </div>
          <div class="col-span-1 text-right font-mono text-[11px] ${avgAge != null && avgAge >= 25 ? 'text-rose-600 font-semibold' : 'text-slate-700'}">${avgAge != null ? avgAge.toFixed(1) : '—'}</div>
          <div class="col-span-3 flex flex-wrap items-center">${labelHtml}${extraHtml}</div>
        </div>`;
    }).join("")}
    <div class="px-2 pt-2 text-[10px] text-slate-500 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-100">
      <span><strong class="text-slate-700">시장 구조:</strong> Top 5 GT ${fmtTon(top5Gt)} · <strong>${top5Pct.toFixed(1)}%</strong> of 전체 GT ${fmtTon(totalGt)}</span>
      <span class="text-slate-400">·</span>
      <span>Top 10 GT ${fmtTon(top10Gt)} · <strong>${top10Pct.toFixed(1)}%</strong></span>
      <span class="text-slate-400">·</span>
      <span title="Herfindahl-Hirschman Index — sum of (share %)². KPPU: <1500 분산 / 1500-2500 중간 / >2500 집중">HHI <strong class="${hhiCls}">${hhi.toFixed(0)}</strong> (<span class="${hhiCls}">${hhiLabel}</span>)</span>
      <span class="text-slate-400">·</span>
      <span>${ownersCount.toLocaleString()}개 운영사</span>
    </div>
    <div class="text-[10px] text-slate-400 px-2 pt-1">
      <em>현재 필터 적용 결과 기준 · 평균선령 25년+ → rose · row 클릭 → 필터 · ★ IDX</em>
    </div>`;
  // Cycle 13: row 클릭 시 ownerExact 필터 적용.
  //   - 클릭한 owner의 척수가 차지하는 row가 highlight.
  //   - 같은 row 재클릭 시 토글 해제.
  host.querySelectorAll(".grid.grid-cols-12[data-owner-row]").forEach(row => {
    row.style.cursor = "pointer";
    row.addEventListener("click", () => {
      const tabEl = document.getElementById("tab-fleet");
      const stx = tabEl._fleetState;
      const target = row.dataset.ownerRow;
      stx.ownerExact = stx.ownerExact === target ? "" : target;
      tabEl._fleetPage = 1;
      _renderFleetView();
    });
  });
  // Highlight 현재 ownerExact row
  const cur = document.getElementById("tab-fleet")._fleetState.ownerExact;
  if (cur) {
    const row = host.querySelector(`.grid.grid-cols-12[data-owner-row="${CSS.escape(cur)}"]`);
    if (row) row.classList.add("bg-blue-50", "ring-1", "ring-blue-200");
  }
}

// Cycle 20: Top 50 운영사 분포 scatter — 척수 vs 평균선령. 크기 = 선대 GT(sqrt).
//   - 사분면 분석: 우상단(많은 척수 + 노후) vs 우하단(많은 척수 + 신생)
//   - 25년+ 평균선령 owner는 rose 색상으로 강조
function _drawFleetOwnerScatter(rows, I) {
  const host = document.getElementById("fl-owner-scatter");
  if (!host) return;
  // 현재 필터된 rows 기준 owner 집계
  const acc = new Map();
  for (const r of rows) {
    const owner = (r[I.owner] || "").trim();
    if (!owner) continue;
    const gt = r[I.gt] || 0;
    const age = r[I.age];
    const ent = acc.get(owner) || { owner, vessels: 0, sum_gt: 0,
                                     age_w: 0, gt_w: 0 };
    ent.vessels += 1;
    ent.sum_gt += gt;
    if (gt > 0 && age != null) { ent.age_w += age * gt; ent.gt_w += gt; }
    acc.set(owner, ent);
  }
  const top = [...acc.values()]
    .filter(o => o.vessels >= 3 && o.gt_w > 0)
    .sort((a, b) => b.vessels - a.vessels)
    .slice(0, 50);
  if (!top.length) {
    Plotly.purge("fl-owner-scatter");
    host.innerHTML = `<div class="text-xs text-slate-400 p-4 text-center">필터 결과 운영사 부족 (3척+ 기준)</div>`;
    return;
  }
  // Cycle 22: IDX 상장사는 별표(★), 일반은 원(●). 두 trace로 분리.
  const idxIdx = top.map((o, i) => _ownerIsIdxListed(o.owner) ? i : -1).filter(i => i >= 0);
  const norIdx = top.map((_, i) => i).filter(i => !idxIdx.includes(i));
  const mkSubset = (idxArr) => ({
    xs: idxArr.map(i => top[i].vessels),
    ys: idxArr.map(i => top[i].age_w / top[i].gt_w),
    sizes: idxArr.map(i => Math.max(8, Math.sqrt(top[i].sum_gt) / 10)),
    colors: idxArr.map(i => {
      const a = top[i].age_w / top[i].gt_w;
      return a >= 25 ? FL_ALERT : a >= 15 ? FL_WARN : FL_PRIMARY;
    }),
    labels: idxArr.map(i => {
      const n = top[i].owner;
      return n.length > 20 ? n.substring(0, 18) + "…" : n;
    }),
    hovers: idxArr.map(i => {
      const o = top[i];
      const idx = _ownerIsIdxListed(o.owner) ? '<br><i style="color:#1d4ed8">★ IDX 상장</i>' : '';
      return `<b>${o.owner}</b><br>척수: ${o.vessels.toLocaleString()}<br>선대 GT: ${o.sum_gt.toLocaleString()}<br>평균선령(GT가중): ${(o.age_w / o.gt_w).toFixed(1)}년${idx}`;
    }),
  });
  const sNorm = mkSubset(norIdx);
  const sIdx  = mkSubset(idxIdx);
  // Cycle 24: 사분면 가이드 — median 척수 / median 평균선령 라인.
  const sortedVessels = [...top].map(o => o.vessels).sort((a, b) => a - b);
  const sortedAges = [...top].map(o => o.age_w / o.gt_w).sort((a, b) => a - b);
  const medV = sortedVessels[Math.floor(sortedVessels.length / 2)] || 1;
  const medA = sortedAges[Math.floor(sortedAges.length / 2)] || 15;
  // Cycle 57: 2 trace 구분을 위해 legend 표시. 우상단에 컴팩트 배치.
  Plotly.newPlot("fl-owner-scatter", [
    {
      name: "일반",
      x: sNorm.xs, y: sNorm.ys, text: sNorm.labels, type: "scatter", mode: "markers",
      marker: {
        size: sNorm.sizes, color: sNorm.colors,
        line: { color: "white", width: 1 },
        opacity: 0.78,
        symbol: "circle",
      },
      hovertext: sNorm.hovers, hovertemplate: "%{hovertext}<extra>클릭 시 owner 필터</extra>",
      customdata: norIdx,
    },
    {
      name: "IDX 상장",
      x: sIdx.xs, y: sIdx.ys, text: sIdx.labels, type: "scatter", mode: "markers",
      marker: {
        size: sIdx.sizes.map(s => s * 1.2), color: sIdx.colors,
        line: { color: "#1d4ed8", width: 2 },
        opacity: 0.9,
        symbol: "star",
      },
      hovertext: sIdx.hovers, hovertemplate: "%{hovertext}<extra>★ IDX · 클릭 시 owner 필터</extra>",
      customdata: idxIdx,
    },
  ], {
    margin: { t: 40, l: 50, r: 80, b: 50 },
    showlegend: true,
    legend: { x: 1.02, y: 1, xanchor: "left", yanchor: "top",
              font: { size: 9 }, bgcolor: "rgba(255,255,255,0.85)",
              bordercolor: "#e2e8f0", borderwidth: 1 },
    xaxis: { title: { text: "척수 (log)", font: { size: 10 } }, type: "log",
             tickfont: { size: 10 }, gridcolor: "#eef2f7" },
    yaxis: { title: { text: "평균 선령 (년, GT 가중)", font: { size: 10 } },
             tickfont: { size: 10 }, gridcolor: "#eef2f7" },
    shapes: [
      // 25y+ 노후 임계점
      { type: "line", xref: "x", yref: "y",
        x0: 1, x1: 9999, y0: 25, y1: 25,
        line: { color: "#dc262640", width: 1, dash: "dot" } },
      // Cycle 24: median 가이드 — 척수 / 평균선령
      { type: "line", xref: "x", yref: "y",
        x0: medV, x1: medV, y0: 0, y1: 60,
        line: { color: "#94a3b840", width: 1, dash: "dash" } },
      { type: "line", xref: "x", yref: "y",
        x0: 1, x1: 9999, y0: medA, y1: medA,
        line: { color: "#94a3b840", width: 1, dash: "dash" } },
    ],
    annotations: [
      { xref: "paper", yref: "y", x: 0.99, y: 25.5, text: "25y+ (노후)",
        showarrow: false, font: { size: 9, color: "#dc2626" }, xanchor: "right" },
      // Cycle 24: 사분면 라벨 (4개)
      { xref: "paper", yref: "paper", x: 0.99, y: 1.06,
        text: `↗ 대규모 노후 (>${medV.toLocaleString()}척 · >${medA.toFixed(0)}y)`,
        showarrow: false, font: { size: 9, color: "#475569" }, xanchor: "right" },
      { xref: "paper", yref: "paper", x: 0.01, y: 1.06,
        text: `↖ 소규모 노후`,
        showarrow: false, font: { size: 9, color: "#475569" }, xanchor: "left" },
      { xref: "paper", yref: "paper", x: 0.99, y: -0.13,
        text: `↘ 대규모 신생`,
        showarrow: false, font: { size: 9, color: "#475569" }, xanchor: "right" },
      { xref: "paper", yref: "paper", x: 0.01, y: -0.13,
        text: `↙ 소규모 신생`,
        showarrow: false, font: { size: 9, color: "#475569" }, xanchor: "left" },
    ],
    plot_bgcolor: "white", paper_bgcolor: "white",
  }, { displayModeBar: false, responsive: true });
  // 클릭 → owner 필터. Cycle 22: customdata로 top[] 인덱스 역추적
  if (host) {
    host.removeAllListeners?.("plotly_click");
    host.on("plotly_click", (ev) => {
      const pt = ev?.points?.[0];
      if (!pt) return;
      // pt.customdata 가 top[] 인덱스. 없으면 pointIndex fallback.
      const idx = pt.customdata != null ? pt.customdata : pt.pointIndex;
      const owner = top[idx]?.owner;
      if (!owner) return;
      const tabEl = document.getElementById("tab-fleet");
      const stx = tabEl._fleetState;
      stx.ownerExact = stx.ownerExact === owner ? "" : owner;
      tabEl._fleetPage = 1;
      _renderFleetView();
    });
  }
}

// Cycle 13: 25y+ 비중 임계점 alert callout.
//   ≥ 50% → red severe (시급 교체 필요 신호)
//   ≥ 30% → amber warn (구조적 노후화)
//   < 30% → hidden
// Cycle 16: class별 노후 breakdown 추가 — 어느 class에 노후가 집중되어 있는지 한 줄 표시
function _renderFleetAgedAlert(rows, I, aged25, agedTotal, st) {
  const host = document.getElementById("fl-aged-alert");
  if (!host) return;
  if (!agedTotal || aged25 == null) { host.classList.add("hidden"); return; }
  const pct = (aged25 / agedTotal) * 100;
  let severity = null;
  if (pct >= 50) severity = "severe";
  else if (pct >= 30) severity = "warn";
  if (!severity) { host.classList.add("hidden"); host.innerHTML = ""; return; }
  // Cycle 20: owner 필터 활성 시 컨텍스트 라벨 — "PT.XXX 노후 N척"
  const ownerContext = (st && st.ownerExact)
    ? `<span class="ml-2 inline-block px-2 py-0.5 rounded bg-white/40 text-[11px] font-mono" title="현재 운영사 필터 적용 중">📌 ${_esc(st.ownerExact.length > 32 ? st.ownerExact.substring(0,30) + '…' : st.ownerExact)}</span>`
    : "";

  // class별 25y+ 척수 집계 + Cycle 23: 평균 GT / 평균 LOA 집계
  const byClass = new Map();
  let agedTotalByClass = 0;
  let agedSumGt = 0, agedNGt = 0, agedSumLoa = 0, agedNLoa = 0;
  for (const r of rows) {
    const age = r[I.age];
    if (age == null || age < 25) continue;
    let cls = r[I.vc] || "Other";
    byClass.set(cls, (byClass.get(cls) || 0) + 1);
    agedTotalByClass += 1;
    const gt = r[I.gt] || 0;
    if (gt > 0) { agedSumGt += gt; agedNGt += 1; }
    const loa = r[I.loa] || 0;
    if (loa > 0) { agedSumLoa += loa; agedNLoa += 1; }
  }
  const agedAvgGt = agedNGt > 0 ? Math.round(agedSumGt / agedNGt) : null;
  const agedAvgLoa = agedNLoa > 0 ? (agedSumLoa / agedNLoa) : null;
  // Cycle 28: baseline 비교 — 전체 (cargo+aux) 25y+ 평균과 비교
  const baseline = document.getElementById("tab-fleet")?._fleetBaseline || null;
  const diff = (cur, base) => {
    if (cur == null || base == null || base === 0) return "";
    const d = (cur - base) / base * 100;
    const sign = d > 0 ? "+" : "";
    const cls = Math.abs(d) < 2 ? "text-slate-500" : d > 0 ? "text-rose-700" : "text-emerald-700";
    return `<span class="text-[10px] ml-1 ${cls}" title="vs 전체 25y+ baseline ${base.toLocaleString()}">${sign}${d.toFixed(0)}% vs 전체</span>`;
  };
  const dimsLine = (agedAvgGt != null || agedAvgLoa != null) ?
    `<div class="text-[11px] opacity-90 mt-1 leading-5">
       <span class="opacity-75 mr-1">노후선 평균 제원:</span>
       ${agedAvgGt != null ? `<strong>평균 GT</strong> ${agedAvgGt.toLocaleString()}${baseline ? diff(agedAvgGt, baseline.avgGt) : ''}` : ''}
       ${agedAvgGt != null && agedAvgLoa != null ? '<span class="opacity-50 mx-2">·</span>' : ''}
       ${agedAvgLoa != null ? `<strong>평균 LOA</strong> ${agedAvgLoa.toFixed(1)}m${baseline ? diff(agedAvgLoa, baseline.avgLoa) : ''}` : ''}
     </div>` : '';
  const topClasses = [...byClass.entries()]
    .sort((a, b) => b[1] - a[1]).slice(0, 4);
  // Cycle 18: 각 chip은 button — 클릭 시 vcFilter + yrMax(25y+) 즉시 적용
  const breakdown = topClasses.map(([cls, n]) => {
    const p = agedTotalByClass > 0 ? (n / agedTotalByClass * 100).toFixed(0) : "0";
    return `<button type="button" data-alert-class="${_esc(cls)}"
                    class="inline-block mr-2 px-2 py-0.5 rounded bg-white/40 hover:bg-white border border-current/30 cursor-pointer transition-colors"
                    title="${_esc(cls)} 노후 25년+ 만 보기">
              <strong>${_esc(cls)}</strong> ${n.toLocaleString()}척 <em class="opacity-70 not-italic">(${p}%)</em>
            </button>`;
  }).join("");

  host.classList.remove("hidden");
  const isSevere = severity === "severe";
  const cls = isSevere
    ? "bg-rose-50 border-rose-300 text-rose-900"
    : "bg-amber-50 border-amber-300 text-amber-900";
  host.className = `mb-4 px-4 py-3 rounded-lg border text-[12px] flex items-start gap-3 ${cls}`;
  const icon = isSevere ? "⚠" : "ℹ";
  const lvl = isSevere ? "시장 구조 시급" : "시장 구조 주의";
  host.innerHTML = `
    <span class="text-[20px] leading-none flex-shrink-0 mt-0.5">${icon}</span>
    <div class="flex-1">
      <strong class="mr-1 text-[13px]">${lvl} — 노후선 ${pct.toFixed(1)}%</strong>${ownerContext}
      <span>${aged25.toLocaleString()}척 / 분석 대상 ${agedTotal.toLocaleString()}척 (선령 미상 제외) · 필터 결과 ${rows.length.toLocaleString()}척 기준.</span>
      <div class="text-[11px] opacity-90 mt-1 leading-5">
        <span class="opacity-75 mr-1">노후선 25년+ 집중도:</span> ${breakdown || "<em class=\"opacity-60\">데이터 없음</em>"}
      </div>
      ${dimsLine}
      <div class="text-[11px] opacity-70 mt-0.5">
        ${isSevere
          ? "노후선 비중이 50%를 초과 — 신조 발주·매각 등 교체 사이클 의사결정에 직결되는 신호."
          : "노후선 비중 30% 초과 — 히트맵에서 class × 선령 cross 확인."}
      </div>
    </div>`;
  // Cycle 18: class chip 클릭 시 vcFilter + 25y+ 노후 필터 동시 적용
  host.querySelectorAll("button[data-alert-class]").forEach(btn => {
    btn.addEventListener("click", () => {
      const tabEl = document.getElementById("tab-fleet");
      const st = tabEl._fleetState;
      const cls = btn.dataset.alertClass;
      const cutoff = new Date().getFullYear() - 25;
      // Toggle: 같은 vcFilter + cutoff yrMax 가 이미 적용 중이면 해제
      const isActive = st.vcFilter === cls && st.yrMax === cutoff;
      if (isActive) {
        st.vcFilter = null; st.yrMax = null;
        const yr = document.getElementById("fl-f-yr-max"); if (yr) yr.value = "";
      } else {
        st.vcFilter = cls; st.yrMax = cutoff;
        const yr = document.getElementById("fl-f-yr-max"); if (yr) yr.value = String(cutoff);
      }
      tabEl._fleetPage = 1;
      _renderFleetView();
    });
  });
}

// Cycle 11: 운영사명에서 IDX 상장 여부 추정.
//   ".Tbk" / "TBK" suffix 매치 OR owner_ticker_map.json 명시적 매핑.
// Cycle 49: owner_ticker_map.json 매핑 우선 (정확한 ticker 반환), fallback Tbk regex.
function _ownerIdxTicker(owner) {
  if (!owner) return null;
  const tabEl = document.getElementById("tab-fleet");
  const map = tabEl?._fleetOwnerTicker;
  if (map) {
    const norm = String(owner).toUpperCase().replace(/PT\.?\s*/g, "").replace(/[^A-Z0-9]/g, "");
    const t = map.get(norm);
    if (t) return t;
  }
  // Fallback: Tbk-suffix detection (ticker unknown → return "Tbk")
  const s = String(owner).toUpperCase();
  if (/\.\s*TBK\b/.test(s) || /\bTBK\b/.test(s)) return "Tbk";
  return null;
}
function _ownerIsIdxListed(owner) {
  return _ownerIdxTicker(owner) !== null;
}

// Cycle 11: 노후 × class 히트맵. 7 age bucket × 7 class.
function _drawFleetAgeClassHeatmap(rows, I) {
  const host = document.getElementById("fl-age-class-heatmap");
  if (!host) return;
  const AGE_BUCKETS = [
    { key: "<5",    lo: 0,  hi: 5  },
    { key: "5–10",  lo: 5,  hi: 10 },
    { key: "10–15", lo: 10, hi: 15 },
    { key: "15–20", lo: 15, hi: 20 },
    { key: "20–25", lo: 20, hi: 25 },
    { key: "25–30", lo: 25, hi: 30 },
    { key: "30+",   lo: 30, hi: 999 },
  ];
  // Cargo + auxiliary 7 classes — order = market priority (큰→작은)
  const CLASSES = [
    "Other Cargo", "General Cargo", "Tanker", "Bulk Carrier", "Container",
    "Tug/OSV/AHTS", "Other",
  ];
  // matrix[ageIdx][classIdx] = count
  const matrix = AGE_BUCKETS.map(() => CLASSES.map(() => 0));
  let total = 0;
  for (const r of rows) {
    const age = r[I.age];
    if (age == null || age < 0) continue;
    let cls = r[I.vc] || "Other";
    if (!CLASSES.includes(cls)) cls = "Other";
    let aIdx = -1;
    for (let i = 0; i < AGE_BUCKETS.length; i++) {
      if (age >= AGE_BUCKETS[i].lo && age < AGE_BUCKETS[i].hi) { aIdx = i; break; }
    }
    if (aIdx < 0) continue;
    const cIdx = CLASSES.indexOf(cls);
    matrix[aIdx][cIdx] += 1;
    total += 1;
  }
  // Cycle 13: row/col totals — 마지막 row/col에 합계 추가.
  // 가장자리 합계는 별도 색감(slate) 셀로 분리해 본문 셀과 구별.
  const rowTotals = matrix.map(r => r.reduce((a, b) => a + b, 0));
  const colTotals = CLASSES.map((_, ci) => matrix.reduce((s, r) => s + r[ci], 0));
  // 25y+ 행 라벨에 rose 색상 강조 (HTML span을 plotly tickformat에 쓸 수 없으므로 unicode bullet 사용)
  const yLabels = AGE_BUCKETS.map(b =>
    b.lo >= 25 ? `${b.key}년 ●` :    // ● 표시로 25y+ 시각 강조
    b.lo >= 20 ? `${b.key}년 ▸` :
    `${b.key}년`
  );
  // Append row totals column
  const xLabelsWithTotal = [...CLASSES, "Σ row"];
  const yLabelsWithTotal = [...yLabels, "Σ col"];
  // Build augmented matrix: main + row totals as last column; bottom row = col totals + grand total
  const augMatrix = matrix.map((row, ri) => [...row, rowTotals[ri]]);
  augMatrix.push([...colTotals, total]);
  // 각 셀에 척수 + (총 대비 %) 텍스트. 합계 셀은 % 생략 + bold.
  const text = augMatrix.map((row, aI) => row.map((v, cI) => {
    const isTotal = aI === augMatrix.length - 1 || cI === row.length - 1;
    if (v === 0) return "";
    if (isTotal) {
      return `<b>${v.toLocaleString()}</b>`;
    }
    return `${v.toLocaleString()}<br><span style="font-size:9px;opacity:.65">${(v / total * 100).toFixed(1)}%</span>`;
  }));
  // For coloring: blank out the totals row/col by passing null in z so they show neutral.
  // Plotly heatmap doesn't easily allow per-cell colorscale override; instead we keep z including totals
  // but legends keep range from main data. Totals will appear darker which is acceptable.
  // Custom hovertemplate: 합계 셀은 별도 텍스트.
  const customHover = augMatrix.map((row, ri) => row.map((v, ci) => {
    const isRowTotal = ci === row.length - 1;
    const isColTotal = ri === augMatrix.length - 1;
    if (isRowTotal && isColTotal) return `전체 ${total.toLocaleString()}척`;
    if (isRowTotal) return `${yLabelsWithTotal[ri]} 합계: ${v.toLocaleString()}척`;
    if (isColTotal) return `${xLabelsWithTotal[ci]} 합계: ${v.toLocaleString()}척`;
    return `${yLabelsWithTotal[ri]} · ${xLabelsWithTotal[ci]}: ${v.toLocaleString()}척`;
  }));
  Plotly.newPlot("fl-age-class-heatmap", [{
    z: augMatrix,
    x: xLabelsWithTotal,
    y: yLabelsWithTotal,
    type: "heatmap",
    colorscale: FL_BLUE_SCALE,
    showscale: true,
    text: text,
    texttemplate: "%{text}",
    textfont: { family: "Pretendard, sans-serif", size: 10 },
    customdata: customHover,
    hovertemplate: "%{customdata}<extra>셀 클릭 시 age+class 필터</extra>",
    xgap: 1, ygap: 1,
    colorbar: { thickness: 6, len: 0.7, tickfont: { size: 9 }, title: { text: "척수", font: { size: 9 } } },
  }], {
    margin: { t: 10, l: 85, r: 50, b: 40 },
    xaxis: { tickfont: { size: 10 }, side: "bottom" },
    yaxis: { tickfont: { size: 10 }, autorange: "reversed" },  // <5 위, Σ 아래
    plot_bgcolor: "white", paper_bgcolor: "white",
  }, { displayModeBar: false, responsive: true });
  // Cycle 17: 셀 클릭 → age bucket + vc class 둘 다 필터. Cycle 18: re-bind every render.
  const heatHost = document.getElementById("fl-age-class-heatmap");
  if (heatHost) {
    heatHost.removeAllListeners?.("plotly_click");
    heatHost.on("plotly_click", (ev) => {
      const pt = ev?.points?.[0];
      if (!pt) return;
      const xRaw = pt.x;        // e.g. "Tanker" or "Σ row"
      const yRaw = pt.y;        // e.g. "20–25년 ▸" or "Σ col"
      const tabEl = document.getElementById("tab-fleet");
      const st = tabEl._fleetState;
      // age bucket parse — remove 년 + 강조 마커
      const isColTotal = yRaw === "Σ col";
      const isRowTotal = xRaw === "Σ row";
      let bucket = null;
      if (!isColTotal) {
        // yRaw에서 ●, ▸, "년" 제거 → "20–25" 등
        const key = String(yRaw).replace(/[●▸]/g, "").replace(/년/g, "").trim();
        bucket = AGE_BUCKETS.find(b => b.key === key);
      }
      const yr = new Date().getFullYear();
      // Apply age filter (only when row is a real bucket)
      if (bucket) {
        const newYrMin = yr - bucket.hi;     // hi exclusive on age
        const newYrMax = yr - bucket.lo;
        // Toggle when already exactly matching
        if (st.yrMin === newYrMin && st.yrMax === newYrMax) {
          st.yrMin = null; st.yrMax = null;
          const a = document.getElementById("fl-f-yr-min"); if (a) a.value = "";
          const b = document.getElementById("fl-f-yr-max"); if (b) b.value = "";
        } else {
          st.yrMin = newYrMin; st.yrMax = newYrMax;
          const a = document.getElementById("fl-f-yr-min"); if (a) a.value = String(newYrMin);
          const b = document.getElementById("fl-f-yr-max"); if (b) b.value = String(newYrMax);
        }
      }
      // Apply class filter (only when column is a real class)
      if (!isRowTotal) {
        const cls = String(xRaw);
        st.vcFilter = st.vcFilter === cls ? null : cls;
      }
      tabEl._fleetPage = 1;
      _renderFleetView();
    });
  }
}

// Cycle 11: 적용된 필터를 chip으로 시각화. 각 chip에 X 버튼.
function _renderFleetActiveChips(st) {
  const host = document.getElementById("fl-active-chips");
  if (!host) return;
  const chips = [];
  if (st.jenis.size) {
    chips.push({
      key: "jenis", label: `Vessel Type ${st.jenisExclude ? "≠" : "="}`,
      value: `${st.jenis.size}개 선택`,
      reset: () => { st.jenis.clear(); st.jenisExclude = false;
                     const ex = document.getElementById("fl-f-jenis-exclude"); if (ex) ex.checked = false; },
    });
  }
  if (st.name) chips.push({
    key: "name", label: "선박명", value: `"${st.name}"`,
    reset: () => { st.name = ""; const el = document.getElementById("fl-f-name"); if (el) el.value = ""; },
  });
  if (st.ownerExact) chips.push({
    key: "owner", label: "운영사",
    value: st.ownerExact.length > 28 ? st.ownerExact.substring(0, 26) + "…" : st.ownerExact,
    reset: () => { st.ownerExact = ""; },
  });
  if (st.scopeOnly) chips.push({
    key: "scope", label: "Scope",
    value: st.scopeOnly === "cargo" ? "화물선만" : "보조선만",
    reset: () => { st.scopeOnly = null;
                   _refreshScopeButtonStates(); },
  });
  if (st.vcFilter) chips.push({
    key: "vc", label: "선급",
    value: st.vcFilter,
    reset: () => { st.vcFilter = null; },
  });
  if (st.flagFilter) chips.push({
    key: "flag", label: "국적",
    value: st.flagFilter,
    reset: () => { st.flagFilter = null; },
  });
  const range = (label, lo, hi, idMin, idMax, keyMin, keyMax, suffix = "") => {
    if (st[keyMin] == null && st[keyMax] == null) return;
    let v = "";
    if (st[keyMin] != null && st[keyMax] != null) v = `${st[keyMin]}–${st[keyMax]}`;
    else if (st[keyMin] != null) v = `≥${st[keyMin]}`;
    else v = `≤${st[keyMax]}`;
    chips.push({
      key: keyMin, label, value: v + suffix,
      reset: () => {
        st[keyMin] = null; st[keyMax] = null;
        const a = document.getElementById(idMin); if (a) a.value = "";
        const b = document.getElementById(idMax); if (b) b.value = "";
      },
    });
  };
  range("건조", "yr", "yr", "fl-f-yr-min", "fl-f-yr-max", "yrMin", "yrMax", "년");
  range("GT", "gt", "gt", "fl-f-gt-min", "fl-f-gt-max", "gtMin", "gtMax");
  range("LOA", "loa", "loa", "fl-f-loa-min", "fl-f-loa-max", "loaMin", "loaMax", "m");
  range("Width", "w", "w", "fl-f-w-min", "fl-f-w-max", "widthMin", "widthMax", "m");
  range("Depth", "d", "d", "fl-f-d-min", "fl-f-d-max", "depthMin", "depthMax", "m");

  if (!chips.length) {
    host.classList.add("hidden");
    host.innerHTML = "";
    return;
  }
  host.classList.remove("hidden");
  host.innerHTML = `
    <span class="text-[10px] uppercase tracking-wider text-slate-500 font-mono mr-1 inline-flex items-center gap-1">
      적용 필터
      <span class="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1.5 rounded-full bg-blue-600 text-white text-[11px] font-bold leading-none">${chips.length}</span>
    </span>
    ${chips.map((c, i) => `
      <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white border border-slate-300 text-slate-700"
            data-chip-idx="${i}">
        <span class="font-mono text-[10px] text-slate-500">${c.label}</span>
        <span class="font-semibold">${c.value}</span>
        <button type="button" data-chip-x="${i}" class="text-slate-400 hover:text-rose-600 ml-0.5"
                title="이 필터 제거" aria-label="이 필터 제거">×</button>
      </span>
    `).join("")}
    <button type="button" id="fl-chips-clear" class="ml-auto px-2 py-0.5 rounded-full border border-rose-300 bg-rose-50 text-rose-700 text-[10px] font-semibold hover:bg-rose-100 hover:border-rose-500 transition-colors">
      ⊗ 모두 해제
    </button>`;
  // Bind X buttons
  host.querySelectorAll("button[data-chip-x]").forEach(btn => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.chipX);
      const chip = chips[idx];
      if (!chip) return;
      chip.reset();
      const tabEl = document.getElementById("tab-fleet");
      if (tabEl) {
        tabEl._fleetPage = 1;
        _renderFleetJenisList(tabEl._fleetVessels);
        _renderFleetView();
      }
    });
  });
  // Clear all
  const clearBtn = document.getElementById("fl-chips-clear");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      const resetTopBtn = document.getElementById("fl-reset");
      if (resetTopBtn) resetTopBtn.click();
    });
  }
}

const _FLEET_CLASS_COLORS = {
  // Cargo classes
  "Container":             "#0284c7",
  "Bulk Carrier":          "#7c3aed",
  "Tanker":                "#1A3A6B",
  "General Cargo":         "#0891b2",
  "Other Cargo":           "#65a30d",
  // PR-X: non-cargo classes
  "Passenger Ship":        "#0d9488",
  "Ferry":                 "#14b8a6",
  "Fishing Vessel":        "#d97706",
  "Tug/OSV/AHTS":          "#475569",
  "Dredger/Special":       "#78716c",
  "Government/Navy/Other": "#6b7280",
  "UNMAPPED":              "#dc2626",
  "Other":                 "#94a3b8",
};
function _drawFleetClassDonutCounts(counts) {
  const labels = Object.keys(counts);
  const values = labels.map(l => counts[l]);
  if (!labels.length) {
    Plotly.purge("fl-class-donut");
    return;
  }
  Plotly.newPlot("fl-class-donut", [{
    values, labels, type: "pie", hole: 0.55,
    marker: { colors: labels.map(l => _FLEET_CLASS_COLORS[l] || "#94a3b8") },
    textinfo: "label+percent",
    textposition: "inside",
    hovertemplate: "<b>%{label}</b><br>%{value:,} 척 (%{percent})<extra></extra>",
  }], {
    margin: { t: 5, l: 5, r: 5, b: 5 },
    showlegend: false,
  }, { displayModeBar: false, responsive: true });
}

function _drawFleetAgeBarsCounts(buckets) {
  const labels = Object.keys(buckets);
  const values = labels.map(l => buckets[l]);
  Plotly.newPlot("fl-age-bars", [{
    x: labels, y: values, type: "bar",
    marker: { color: labels.map(l => l === "25년+" ? "#dc2626" : "#1A3A6B") },
    text: values.map(v => v.toLocaleString()),
    textposition: "outside",
    cliponaxis: false,
    hovertemplate: "<b>%{x}</b><br>%{y:,} 척<extra></extra>",
  }], {
    margin: { t: 20, l: 40, r: 10, b: 30 },
    xaxis: { tickfont: { size: 10 } },
    yaxis: { tickfont: { size: 10 } },
  }, { displayModeBar: false, responsive: true });
}

// ─────────────────────────────────────────────────────────────
// Cargo tab — mirrors jang1117.github.io/shipping_volume infographic
// Data: docs/derived/cargo_ports.json
//   { commodities: [...], ports: { code: { n, lat, lng, dU, dS, iU, iS, comms: {...} } } }
// ─────────────────────────────────────────────────────────────
const CV_OG_KEYS = [
  "CPO", "PERTALITE", "LPG", "CRUDE OIL", "FAME", "BIO SOLAR",
  "AVTUR", "RBD PALM OLEIN", "PERTAMAX", "RBD PALM OIL", "MFO/HSFO",
  "CONDENSATE", "METHANOL", "HSD", "ASPAL/BITUMEN", "OLEIN",
  "OMAN BLEND CRUDE OIL", "PKO",
];
const CV_ETC_EXCLUDE = ["PERTAMAX","HSD","ASPAL/BITUMEN","LPG","METHANOL","MFO/HSFO","FAME","AVTUR","CONDENSATE"];
let _cvState = null;     // shared state, lazily initialised in renderCargo

function _cvColorForIndex(i, total) {
  const hue = Math.round((i * 360 / Math.max(total, 1)) % 360);
  return `hsl(${hue} 72% 45%)`;
}

async function renderCargo() {
  setupSourceLabels(document.getElementById("tab-cargo"));
  // Cycle 4: cargo_ports_periods.json (기간별)이 1차 데이터 소스. fallback으로
  // cargo_ports.json (24M only). map_flow.json은 흐름 라인용.
  let periodsPayload, fallbackPayload, routesPayload;
  try {
    periodsPayload = await loadDerived("cargo_ports_periods.json");
  } catch (_) { periodsPayload = null; }
  if (!periodsPayload) {
    try { fallbackPayload = await loadDerived("cargo_ports.json"); }
    catch (e) {
      const host = document.getElementById("cv-map");
      if (host) host.innerHTML =
        `<div class="cv-empty">cargo_ports 로드 실패: ${e.message}</div>`;
      return;
    }
  }
  try { routesPayload = await loadDerived("map_flow.json"); }
  catch (_) { routesPayload = { routes_top30: [], categories: [] }; }

  // Decide initial period + DATA.
  let activePeriod, allCommodities, allPorts;
  if (periodsPayload) {
    activePeriod = periodsPayload.active_period || "24m";
    const p = (periodsPayload.periods || {})[activePeriod] || {};
    allCommodities = p.commodities || [];
    allPorts = p.ports || {};
  } else {
    activePeriod = "24m";
    allCommodities = fallbackPayload.commodities || [];
    allPorts = fallbackPayload.ports || {};
  }
  const COMMS = allCommodities.map((key, i) => ({
    key, lbl: key, col: _cvColorForIndex(i, allCommodities.length),
  }));

  if (!_cvState) {
    const cpoKey = COMMS.find(c => c.key === "CPO") ? "CPO" : (COMMS[0] && COMMS[0].key);
    _cvState = {
      mode: "total",
      sub:  "both",
      multi: false,
      selComms: new Set(cpoKey ? [cpoKey] : []),
      selPort: null,
      map: null,
      circles: [],
      lines: [],
      showLines: true,
      // Cycle 4: 기간 필터 + 흐름 입자 애니메이션
      period: activePeriod,
      PERIODS: periodsPayload ? periodsPayload.periods : null,
      flowCanvas: null,
      flowRaf: null,
      flowParticles: null,   // [{routeIdx, t}]
      COMMS,
      DATA: allPorts,
      ROUTES: routesPayload.routes_top30 || [],
      ROUTE_CATS: routesPayload.categories || [],
    };
  } else {
    _cvState.COMMS = COMMS;
    _cvState.DATA = allPorts;
    _cvState.PERIODS = periodsPayload ? periodsPayload.periods : _cvState.PERIODS;
    _cvState.ROUTES = routesPayload.routes_top30 || _cvState.ROUTES || [];
    _cvState.ROUTE_CATS = routesPayload.categories || _cvState.ROUTE_CATS || [];
  }

  _cvInitMap();
  _cvBuildPeriodPills();
  _cvBuildCommodityList();
  _cvWireControls();
  _cvRebuild();
  _cvStartFlowAnimation();
}

// Cycle 4: 기간 필터 (연도별 only) 빌드 + 이벤트.
// 사용자 요청 — 24m / 12m 롤링 윈도우 버튼은 제거하고 달력 연도 단위로만
// 기간을 선택. 기본 활성 기간이 24m/12m 이면 가장 최근(=마지막) 연도로 승격.
function _cvBuildPeriodPills() {
  const host = document.getElementById("cv-period-pills");
  if (!host || !_cvState.PERIODS) return;
  const yrs = Object.keys(_cvState.PERIODS).filter(k => /^\d{4}$/.test(k)).sort();
  if (!yrs.length) {
    host.innerHTML = `<button class="px-2 py-1 bg-slate-100 text-slate-400" disabled>연도 데이터 없음</button>`;
    return;
  }
  // Auto-promote rolling-window default to the most recent calendar year.
  if (!yrs.includes(_cvState.period)) {
    _cvState.period = yrs[yrs.length - 1];
    const p = _cvState.PERIODS[_cvState.period];
    const newCommods = (p && p.commodities) || [];
    _cvState.COMMS = newCommods.map((key, i) => ({
      key, lbl: key, col: _cvColorForIndex(i, newCommods.length),
    }));
    _cvState.DATA = (p && p.ports) || {};
    const keep = new Set([..._cvState.selComms].filter(k0 => newCommods.includes(k0)));
    if (!keep.size && newCommods.length) keep.add(newCommods[0]);
    _cvState.selComms = keep;
  }
  host.innerHTML = yrs.map(k => {
    const p = _cvState.PERIODS[k];
    const active = k === _cvState.period;
    const label = p.label || `${k}년`;
    const sub = ` <span class="text-[10px] opacity-70">(${p.months}mo)</span>`;
    const cls = active
      ? "px-2 py-1 bg-slate-800 text-white"
      : "px-2 py-1 bg-white hover:bg-slate-100";
    return `<button data-period="${k}" class="${cls}">${label}${sub}</button>`;
  }).join("");
  host.querySelectorAll("button[data-period]").forEach(b => {
    b.addEventListener("click", () => {
      const k = b.dataset.period;
      if (!_cvState.PERIODS[k]) return;
      _cvState.period = k;
      const p = _cvState.PERIODS[k];
      // Rebuild COMMS (commodity list may differ across periods)
      const newCommods = p.commodities || [];
      _cvState.COMMS = newCommods.map((key, i) => ({
        key, lbl: key, col: _cvColorForIndex(i, newCommods.length),
      }));
      _cvState.DATA = p.ports || {};
      // Keep selection that still exists; else pick first
      const keep = new Set([..._cvState.selComms].filter(k0 => newCommods.includes(k0)));
      if (!keep.size && newCommods.length) keep.add(newCommods[0]);
      _cvState.selComms = keep;
      _cvBuildPeriodPills();
      _cvBuildCommodityList();
      _cvRebuild();
    });
  });
}

// Cycle 4: Leaflet 위에 오버레이된 Canvas에 입자(particle) 애니메이션을
// 그린다. 각 프레임마다 routes_top30 24M 항로 위에 origin→destination 방향
// 으로 흐르는 작은 점을 그려, "물류 흐름이 흐르는" 인상을 준다. 카테고리
// 색상은 _cvCatColor 를 따른다.
const _CV_FLOW_PARTICLES_PER_ROUTE = 3;
const _CV_FLOW_SPEED = 0.00045;   // t 증가량 per ms (≈ 한 항로를 2.2초에 통과)

function _cvStartFlowAnimation() {
  if (!_cvState || !_cvState.map) return;
  const mapEl = _cvState.map.getContainer();
  if (!mapEl) return;
  // Create or reuse canvas overlay
  let canvas = _cvState.flowCanvas;
  if (!canvas) {
    canvas = document.createElement("canvas");
    canvas.className = "cv-flow-canvas";
    canvas.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;z-index:399";
    mapEl.appendChild(canvas);
    _cvState.flowCanvas = canvas;
    // Re-size on Leaflet's container changes
    const _resize = () => {
      const sz = _cvState.map.getSize();
      canvas.width = sz.x;
      canvas.height = sz.y;
    };
    _resize();
    _cvState.map.on("resize zoom move", _resize);
  }
  // Initialize particles (per-route phase)
  if (!_cvState.flowParticles || _cvState.flowParticles.length === 0) {
    _cvState.flowParticles = [];
    const n = (_cvState.ROUTES || []).length;
    for (let r = 0; r < n; r++) {
      for (let i = 0; i < _CV_FLOW_PARTICLES_PER_ROUTE; i++) {
        _cvState.flowParticles.push({
          routeIdx: r,
          t: i / _CV_FLOW_PARTICLES_PER_ROUTE,
        });
      }
    }
  }
  if (_cvState.flowRaf) cancelAnimationFrame(_cvState.flowRaf);
  let last = performance.now();
  const loop = (now) => {
    const dt = Math.min(now - last, 60);
    last = now;
    _cvDrawFlowFrame(dt);
    _cvState.flowRaf = requestAnimationFrame(loop);
  };
  _cvState.flowRaf = requestAnimationFrame(loop);
}

function _cvDrawFlowFrame(dtMs) {
  const canvas = _cvState.flowCanvas;
  if (!canvas || !_cvState.map) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (!_cvState.showLines) return;
  const routes = _cvState.ROUTES || [];
  if (!routes.length) return;
  const maxV = Math.max(...routes.map(r => r.ton_24m || 0), 1);
  for (const part of _cvState.flowParticles) {
    const r = routes[part.routeIdx];
    if (!r || r.origin === r.destination) continue;
    part.t = (part.t + dtMs * _CV_FLOW_SPEED) % 1;
    // Cycle 5: 입자 위치도 quadratic Bezier 곡선 위에서 보간.
    const headLatLon = _cvBezierAt(r, part.t);
    if (!headLatLon) continue;
    const tailT = Math.max(0, part.t - 0.06);
    const tailLatLon = _cvBezierAt(r, tailT);
    const head = _cvState.map.latLngToContainerPoint([headLatLon.lat, headLatLon.lon]);
    const tail = _cvState.map.latLngToContainerPoint([tailLatLon.lat, tailLatLon.lon]);
    const color = _cvCatColor(r.category);
    const v = r.ton_24m || 0;
    const radius = 1.8 + Math.sqrt(v / maxV) * 2.6;
    // Trail (back-tail along the curve)
    const grd = ctx.createLinearGradient(tail.x, tail.y, head.x, head.y);
    grd.addColorStop(0, color + "00");
    grd.addColorStop(1, color + "cc");
    ctx.strokeStyle = grd;
    ctx.lineWidth = radius * 0.9;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(tail.x, tail.y);
    ctx.lineTo(head.x, head.y);
    ctx.stroke();
    // Bright head dot
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(head.x, head.y, radius, 0, Math.PI * 2);
    ctx.fill();
    // White inner highlight
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.beginPath();
    ctx.arc(head.x, head.y, radius * 0.35, 0, Math.PI * 2);
    ctx.fill();
  }
}

function _cvInitMap() {
  if (_cvState.map) return;
  const host = document.getElementById("cv-map");
  if (!host || !window.L) return;
  _cvState.map = L.map(host, {
    center: [-2, 118],
    zoom: 5,
    zoomControl: true,
    attributionControl: true,
    scrollWheelZoom: true,
  });
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(_cvState.map);
}

// Per-port commodity value resolver — handles 기타 deduction so totals add up.
function _cvPortCommVol(code, key) {
  const p = _cvState.DATA[code];
  if (!p || !p.comms || !p.comms[key]) return null;
  const base = p.comms[key];
  if (key !== "기타") return base;
  const adj = { dU: base.dU || 0, dS: base.dS || 0, iU: base.iU || 0, iS: base.iS || 0 };
  for (const x of CV_ETC_EXCLUDE) {
    const ex = p.comms[x];
    if (!ex) continue;
    adj.dU -= ex.dU || 0; adj.dS -= ex.dS || 0;
    adj.iU -= ex.iU || 0; adj.iS -= ex.iS || 0;
  }
  adj.dU = Math.max(0, adj.dU); adj.dS = Math.max(0, adj.dS);
  adj.iU = Math.max(0, adj.iU); adj.iS = Math.max(0, adj.iS);
  return adj;
}

function _cvSumPortComms(code, keys) {
  let dU = 0, dS = 0, iU = 0, iS = 0;
  for (const k of keys) {
    const v = _cvPortCommVol(code, k);
    if (v) { dU += v.dU || 0; dS += v.dS || 0; iU += v.iU || 0; iS += v.iS || 0; }
  }
  return { dU, dS, iU, iS };
}

function _cvBuildPorts(keys) {
  const allKeys = _cvState.COMMS.map(c => c.key);
  const isAll = keys.length === allKeys.length;
  const out = [];
  for (const code of Object.keys(_cvState.DATA)) {
    const meta = _cvState.DATA[code];
    const t = isAll
      ? { dU: meta.dU, dS: meta.dS, iU: meta.iU, iS: meta.iS }
      : _cvSumPortComms(code, keys);
    if ((t.dU + t.dS + t.iU + t.iS) === 0) continue;
    out.push({ code, name: meta.n, lat: meta.lat, lng: meta.lng, ...t });
  }
  return out;
}

function _cvVol(p) {
  const sub = _cvState.sub, mode = _cvState.mode;
  let d = 0, i = 0;
  if (sub !== "loading")   { d += p.dU || 0; i += p.iU || 0; }
  if (sub !== "unloading") { d += p.dS || 0; i += p.iS || 0; }
  if (mode === "domestic")      return d;
  if (mode === "international") return i;
  return d + i;
}
function _cvDomVol(p)  { return (_cvState.sub === "loading"   ? 0 : (p.dU || 0)) + (_cvState.sub === "unloading" ? 0 : (p.dS || 0)); }
function _cvIntlVol(p) { return (_cvState.sub === "loading"   ? 0 : (p.iU || 0)) + (_cvState.sub === "unloading" ? 0 : (p.iS || 0)); }

function _cvColor(p) {
  if (_cvState.mode === "domestic")      return "#065F46";
  if (_cvState.mode === "international") return "#1E3A8A";
  const d = _cvDomVol(p), i = _cvIntlVol(p);
  if (d > 0 && i > 0) return "#4C1D95";
  return i > d ? "#1E3A8A" : "#065F46";
}

function _cvCommodityTotals(key) {
  let dU = 0, dS = 0, iU = 0, iS = 0;
  for (const p of Object.values(_cvState.DATA)) {
    const v = p.comms && p.comms[key];
    if (v) { dU += v.dU || 0; dS += v.dS || 0; iU += v.iU || 0; iS += v.iS || 0; }
  }
  return { dU, dS, iU, iS };
}

function _cvFmt(n) { return (n || 0).toLocaleString("ko-KR"); }
function _cvFmtM(n) { return ((n || 0) / 1e6).toFixed(2) + "M"; }

// Cycle 5: cv-app 코모디티 패널을 카테고리 그룹 드롭다운으로 재구성.
// 각 카테고리는 헤더 (이름 + 합계 + ▼/▶ 토글) + 펼침 상태의 세부 코모디티
// 리스트로 구성. 카테고리 토글 상태는 _cvState.openCategories Set 에 보존.
const CV_CATEGORY_GROUPS = [
  { key: "crude",      label: "Crude / 정제유 (BBM)",  members: ["CRUDE OIL","OMAN BLEND CRUDE OIL","CONDENSATE","PERTALITE","PERTAMAX","AVTUR","HSD","BIO SOLAR","MFO/HSFO","METHANOL","ASPAL/BITUMEN"] },
  { key: "gas",        label: "Gas (LPG·LNG)",         members: ["LPG","LNG"] },
  { key: "palm",       label: "Palm / 식용유",         members: ["CPO","RBD PALM OIL","RBD PALM OLEIN","OLEIN","PKO","STEARIN","FAME"] },
  { key: "bulk",       label: "Dry Bulk (광물·곡물·시멘트)", members: ["BATU BARA CURAH KERING","COAL","NICKEL ORE","BAUXITE","IRON ORE","LIMESTONE","WOOD CHIP","SEMEN CURAH","SEMEN","PUPUK","BERAS","SALT","CHEMICAL"] },
  { key: "container",  label: "Container / General",   members: ["CONTAINER","GENERAL CARGO","BARANG"] },
  { key: "vehicle",    label: "차량",                  members: ["MOBIL","TRUK","MOTOR"] },
  { key: "other",      label: "기타 (어획·가축·미분류)",     members: ["IKAN","TERNAK","기타"] },
];

function _cvCategoryOf(commKey) {
  for (const g of CV_CATEGORY_GROUPS) {
    if (g.members.includes(commKey)) return g.key;
  }
  return "other";
}

function _cvBuildCommodityList() {
  const list = document.getElementById("cv-comm-list");
  if (!list) return;
  if (!_cvState.openCategories) {
    _cvState.openCategories = new Set();   // 초기: 모두 접힘
  }
  list.innerHTML = "";

  // Pre-compute totals + presence per category.
  const byCat = new Map();
  for (const c of _cvState.COMMS) {
    const catKey = _cvCategoryOf(c.key);
    if (!byCat.has(catKey)) byCat.set(catKey, []);
    byCat.get(catKey).push(c);
  }

  for (const g of CV_CATEGORY_GROUPS) {
    const items = byCat.get(g.key) || [];
    if (!items.length) continue;
    // Category-level aggregate ton + any-selected indicator
    let catTon = 0, anySelected = false;
    for (const c of items) {
      const nat = _cvCommodityTotals(c.key);
      catTon += (nat.dU + nat.dS + nat.iU + nat.iS);
      if (_cvState.selComms.has(c.key)) anySelected = true;
    }
    const open = _cvState.openCategories.has(g.key);
    const caret = open ? "▼" : "▶";
    const head = document.createElement("div");
    head.className = "cv-cat-head";
    head.dataset.cat = g.key;
    head.innerHTML =
      `<span class="cv-cat-caret">${caret}</span>` +
      `<span class="cv-cat-name">${g.label}</span>` +
      (anySelected ? `<span class="cv-cat-dot" title="이 카테고리 내 선택 중"></span>` : "") +
      `<span class="cv-cat-vol">${(catTon/1e6).toFixed(1)}M</span>`;
    head.onclick = () => {
      if (_cvState.openCategories.has(g.key)) _cvState.openCategories.delete(g.key);
      else _cvState.openCategories.add(g.key);
      _cvBuildCommodityList();
    };
    list.appendChild(head);

    if (!open) continue;
    // Sort items inside the category by ton desc.
    items.sort((a, b) => {
      const va = (() => { const x = _cvCommodityTotals(a.key); return x.dU+x.dS+x.iU+x.iS; })();
      const vb = (() => { const x = _cvCommodityTotals(b.key); return x.dU+x.dS+x.iU+x.iS; })();
      return vb - va;
    });
    for (const c of items) {
      const nat = _cvCommodityTotals(c.key);
      const tot = (nat.dU + nat.dS + nat.iU + nat.iS) / 1e6;
      const on = _cvState.selComms.has(c.key);
      const row = document.createElement("div");
      row.className = "cv-comm-row cv-comm-row-nested" + (on ? " selected" : "");
      row.style.color = c.col;
      row.dataset.key = c.key;
      row.innerHTML =
        `<div class="cv-chk"><svg class="cv-chk-svg" viewBox="0 0 10 10" fill="none"><path d="M1.5 5L4 7.5L8.5 2.5" stroke="${c.col}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></div>` +
        `<span class="cv-sw" style="background:${c.col}"></span>` +
        `<span class="cv-comm-name">${c.lbl}</span>` +
        `<span class="cv-comm-vol">${tot.toFixed(1)}M</span>`;
      row.onclick = () => _cvHandleCommClick(c.key);
      list.appendChild(row);
    }
  }

  // If a selected commodity falls into a folded category, auto-open it once.
  for (const k of _cvState.selComms) {
    const catKey = _cvCategoryOf(k);
    if (!_cvState.openCategories.has(catKey)) {
      _cvState.openCategories.add(catKey);
      _cvBuildCommodityList();   // re-render to reflect the auto-open
      return;
    }
  }
}

function _cvHandleCommClick(key) {
  if (_cvState.multi) {
    if (_cvState.selComms.has(key)) {
      if (_cvState.selComms.size === 1) return;
      _cvState.selComms.delete(key);
    } else {
      _cvState.selComms.add(key);
    }
  } else {
    _cvState.selComms = new Set([key]);
  }
  _cvRefreshCommUI();
  _cvRebuild();
}

function _cvRefreshCommUI() {
  document.querySelectorAll("#cv-comm-list .cv-comm-row").forEach(r => {
    r.classList.toggle("selected", _cvState.selComms.has(r.dataset.key));
  });
}

function _cvSetMode(m) {
  _cvState.mode = m;
  document.querySelectorAll('#tab-cargo .cv-rbtn[data-mode]').forEach(b => {
    b.classList.toggle("on-t", b.dataset.mode === m);
  });
  _cvRebuild();
}
function _cvSetSub(s) {
  _cvState.sub = s;
  document.querySelectorAll('#tab-cargo .cv-rbtn[data-sub]').forEach(b => {
    b.classList.toggle("on-s", b.dataset.sub === s);
  });
  _cvRebuild();
}

function _cvWireControls() {
  const tab = document.getElementById("tab-cargo");
  if (tab.dataset.cvWired) return;
  tab.dataset.cvWired = "1";
  // Mode + Sub buttons
  tab.querySelectorAll('.cv-rbtn[data-mode]').forEach(b => {
    b.addEventListener("click", () => _cvSetMode(b.dataset.mode));
  });
  tab.querySelectorAll('.cv-rbtn[data-sub]').forEach(b => {
    b.addEventListener("click", () => _cvSetSub(b.dataset.sub));
  });
  // Multi toggle
  const mt = document.getElementById("cv-multi-toggle");
  if (mt) mt.addEventListener("click", () => {
    _cvState.multi = !_cvState.multi;
    document.getElementById("cv-multi-track").classList.toggle("on", _cvState.multi);
    document.getElementById("cv-multi-label").style.color =
      _cvState.multi ? "var(--cv-purple)" : "";
  });
  // Presets
  const og = document.getElementById("cv-og-btn");
  if (og) og.addEventListener("click", _cvToggleOG);
  const all = document.getElementById("cv-all-btn");
  if (all) all.addEventListener("click", _cvToggleAll);
  // Line toggle (해상 물류 연결선)
  const lt = document.getElementById("cv-line-toggle");
  if (lt) lt.addEventListener("click", () => {
    _cvState.showLines = !_cvState.showLines;
    document.getElementById("cv-line-track").classList.toggle("on", _cvState.showLines);
    _cvRenderLines();
  });
}

function _cvToggleOG() {
  const avail = new Set(_cvState.COMMS.map(c => c.key));
  const og = CV_OG_KEYS.filter(k => avail.has(k));
  if (!og.length) return;
  const isOgOnly = _cvState.selComms.size === og.length
                    && og.every(k => _cvState.selComms.has(k));
  if (isOgOnly) {
    _cvState.selComms = new Set([og[0]]);
    _cvState.multi = false;
  } else {
    _cvState.selComms = new Set(og);
    _cvState.multi = true;
  }
  document.getElementById("cv-multi-track").classList.toggle("on", _cvState.multi);
  document.getElementById("cv-multi-label").style.color =
    _cvState.multi ? "var(--cv-purple)" : "";
  _cvRefreshCommUI();
  _cvRebuild();
}

function _cvToggleAll() {
  const allKeys = _cvState.COMMS.map(c => c.key);
  if (_cvState.selComms.size === allKeys.length) {
    _cvState.selComms = new Set([allKeys[0]]);
    _cvState.multi = false;
  } else {
    _cvState.selComms = new Set(allKeys);
    _cvState.multi = true;
  }
  document.getElementById("cv-multi-track").classList.toggle("on", _cvState.multi);
  document.getElementById("cv-multi-label").style.color =
    _cvState.multi ? "var(--cv-purple)" : "";
  _cvRefreshCommUI();
  _cvRebuild();
}

// Cycle 5: tooltip 4셀 + 총합을 **선택 화물 한정 값**으로 계산. p의 dU/dS/iU/iS
// 는 _cvBuildPorts 가 이미 선택 코모디티만 합산한 값을 넣어주므로 그대로 사용.
// 헤더에 선택 화물 라벨 명시.
function _cvTooltip(p) {
  const selArr = [..._cvState.selComms];
  const COMMS = _cvState.COMMS;
  const tags = selArr.slice(0, 8).map(k => {
    const c = COMMS.find(x => x.key === k);
    if (!c) return "";
    return `<span class="cv-tt-tag" style="background:${c.col}20;color:${c.col};border:1px solid ${c.col}40">${c.lbl}</span>`;
  }).join("") + (selArr.length > 8 ? `<span class="cv-tt-tag" style="background:#fff1;color:#7A8FB5">+${selArr.length - 8}</span>` : "");
  const total = (p.dU || 0) + (p.dS || 0) + (p.iU || 0) + (p.iS || 0);
  return `
    <div class="cv-tt-name">🛢 ${p.name} <span style="font-size:9px;color:#7A8FB5;font-weight:400">(${p.code})</span></div>
    <div class="cv-tt-tags">${tags}</div>
    <div class="cv-tt-grid">
      <div class="cv-tt-cell"><div class="cv-tt-cl">🟢 DOM 하역</div><div class="cv-tt-cv" style="color:#065F46">${_cvFmt(p.dU || 0)}</div></div>
      <div class="cv-tt-cell"><div class="cv-tt-cl">🟢 DOM 선적</div><div class="cv-tt-cv" style="color:#065F46">${_cvFmt(p.dS || 0)}</div></div>
      <div class="cv-tt-cell"><div class="cv-tt-cl">🔵 INTL 하역</div><div class="cv-tt-cv" style="color:#1E3A8A">${_cvFmt(p.iU || 0)}</div></div>
      <div class="cv-tt-cell"><div class="cv-tt-cl">🔵 INTL 선적</div><div class="cv-tt-cv" style="color:#1E3A8A">${_cvFmt(p.iS || 0)}</div></div>
    </div>
    <hr class="cv-tt-sep">
    <div class="cv-tt-foot"><span class="cv-tt-fl">선택 화물 ${selArr.length}종 합계</span><span class="cv-tt-fv">${_cvFmt(total)} TON</span></div>`;
}

// Cycle 4: 항만 동그라미는 더 이상 톤에 비례한 큰 마커가 아니라,
// 작은 점(클릭 타겟 + 위치 표시) 으로 약화. 톤 시그널은 흐름 라인과
// 입자 애니메이션이 담당. 사용자가 항만에 hover 시 tooltip 으로 톤 상세
// 확인. 사이드바의 항만 순위 표는 그대로 유지.
function _cvRenderCircles(PORTS) {
  for (const c of _cvState.circles) c.remove();
  _cvState.circles = [];
  if (!_cvState.map || !PORTS.length) return;
  [...PORTS].forEach(p => {
    const v = _cvVol(p);
    if (v === 0) return;
    const color = _cvColor(p);
    // Fixed-size 4px dot — visible but doesn't dominate flow lines.
    const dot = L.circleMarker([p.lat, p.lng], {
      radius: 3.5,
      fillColor: color,
      color: "#ffffff",
      weight: 1.0,
      opacity: 0.9,
      fillOpacity: 0.95,
    });
    dot.bindTooltip(_cvTooltip(p), {
      className: "cv-tt", sticky: true, offset: [10, 0], opacity: 1,
    });
    dot.on("click", () => {
      _cvState.selPort = p.code;
      _cvRenderSidebar(PORTS);
      _cvState.map.setView([p.lat, p.lng], Math.max(_cvState.map.getZoom(), 6), { animate: true });
    });
    dot.addTo(_cvState.map);
    _cvState.circles.push(dot);
  });
}

function _cvRenderSidebar(PORTS) {
  const list = document.getElementById("cv-port-list");
  if (!list) return;
  const sorted = [...PORTS].sort((a, b) => _cvVol(b) - _cvVol(a));
  const maxV = sorted.length ? (_cvVol(sorted[0]) || 1) : 1;
  list.innerHTML = "";
  let rank = 0;
  for (const p of sorted) {
    const v = _cvVol(p);
    if (v === 0) continue;
    rank++;
    const color = _cvColor(p);
    const row = document.createElement("div");
    row.className = "cv-port-row" + (p.code === _cvState.selPort ? " sel" : "");
    row.innerHTML = `
      <span class="cv-rank">${rank}</span>
      <div class="cv-pinfo">
        <div class="cv-pname">${p.name}</div>
        <div class="cv-pbar-wrap"><div class="cv-pbar" style="width:${Math.round(v/maxV*100)}%;background:${color}"></div></div>
      </div>
      <span class="cv-ptotal">${_cvFmtM(v)}</span>`;
    row.onclick = () => {
      _cvState.selPort = p.code;
      _cvState.map.setView([p.lat, p.lng], Math.max(_cvState.map.getZoom(), 7), { animate: true });
      _cvRenderSidebar(PORTS);
    };
    list.appendChild(row);
  }
}

function _cvUpdateStats(PORTS) {
  let d = 0, i = 0;
  for (const p of PORTS) { d += _cvDomVol(p); i += _cvIntlVol(p); }
  const e = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
  e("cv-st-dom",  _cvFmtM(d) + " TON");
  e("cv-st-intl", _cvFmtM(i) + " TON");
  e("cv-st-cnt",  PORTS.length + "개");
}

// ─── OD route lines (해상 물류 연결선) ───────────────────────────────
// Source: map_flow.json routes_top30 — top 30 OD pairs by 24M ton.
// Schema per route: { origin, destination, lat_o, lon_o, lat_d, lon_d,
//                     ton_24m, calls, vessels, category, category_ton: {...} }

function _cvCatColor(name) {
  const cat = (_cvState.ROUTE_CATS || []).find(c => c.name === name);
  return (cat && cat.color) || "#475569";
}

// Cycle 5: route tooltip 을 **선택 화물과 매칭되는 카테고리만** 표시하도록 변경.
// cv-app commodity (e.g. "CRUDE OIL") → map_flow 카테고리 (e.g. "Crude") 매핑을
// 사용. 선택 화물 매칭이 없으면 안내 메시지.
const CV_COMM_TO_ROUTE_CAT = {
  "CRUDE OIL": "Crude", "OMAN BLEND CRUDE OIL": "Crude",
  "PERTALITE": "Product / BBM", "PERTAMAX": "Product / BBM", "AVTUR": "Product / BBM",
  "HSD": "Product / BBM", "BIO SOLAR": "Product / BBM", "MFO/HSFO": "Product / BBM",
  "METHANOL": "Product / BBM", "ASPAL/BITUMEN": "Product / BBM", "CONDENSATE": "Product / BBM",
  "CHEMICAL": "Chemical",
  "LPG": "LPG / LNG", "LNG": "LPG / LNG",
  "CPO": "FAME / Edible", "RBD PALM OIL": "FAME / Edible", "RBD PALM OLEIN": "FAME / Edible",
  "OLEIN": "FAME / Edible", "PKO": "FAME / Edible", "STEARIN": "FAME / Edible", "FAME": "FAME / Edible",
  "COAL": "Coal", "BATU BARA CURAH KERING": "Coal",
  "NICKEL ORE": "Nickel / Mineral Ore", "BAUXITE": "Nickel / Mineral Ore",
  "IRON ORE": "Nickel / Mineral Ore", "LIMESTONE": "Nickel / Mineral Ore",
  "CONTAINER": "Container / Gen Cargo", "GENERAL CARGO": "Container / Gen Cargo",
  "BARANG": "Container / Gen Cargo", "SEMEN": "Container / Gen Cargo", "SEMEN CURAH": "Container / Gen Cargo",
};

function _cvSelectedRouteCategories() {
  const out = new Set();
  for (const k of _cvState.selComms) {
    const cat = CV_COMM_TO_ROUTE_CAT[k];
    if (cat) out.add(cat);
  }
  return out;
}

function _cvRouteTooltip(r) {
  const o = r.origin, d = r.destination;
  const sameOD = o === d;
  const heading = sameOD ? `🔁 ${o} (STS)` : `${o} <span style="color:#7A8FB5">→</span> ${d}`;
  const allCatTon = r.category_ton || {};
  const selCats = _cvSelectedRouteCategories();
  const filtered = selCats.size
    ? Object.fromEntries(Object.entries(allCatTon).filter(([k]) => selCats.has(k)))
    : allCatTon;
  const filteredEntries = Object.entries(filtered).sort((a, b) => b[1] - a[1]);
  const filteredTotal = filteredEntries.reduce((s, [, v]) => s + (v || 0), 0);
  const breakdown = filteredEntries.slice(0, 4).map(([k, v]) => {
    const col = _cvCatColor(k);
    return `<div class="cv-tt-cell"><div class="cv-tt-cl" style="color:${col}">${k}</div><div class="cv-tt-cv">${_cvFmt(v)}</div></div>`;
  }).join("") || `<div class="cv-tt-cell" style="grid-column:1 / -1"><div class="cv-tt-cl" style="color:#7A8FB5">선택 화물과 매칭되는 카테고리 없음</div></div>`;
  // Primary tag — show only if it survived the filter; else fall back to "선택 화물 한정" 안내.
  const showPrimary = !selCats.size || selCats.has(r.category);
  const tag = showPrimary
    ? `<span class="cv-tt-tag" style="background:${_cvCatColor(r.category)}20;color:${_cvCatColor(r.category)};border:1px solid ${_cvCatColor(r.category)}40">${r.category}</span>`
    : `<span class="cv-tt-tag" style="background:#fff1;color:#7A8FB5">선택 화물 한정 보기</span>`;
  return `<div class="cv-tt-name">${heading}</div>
    <div class="cv-tt-tags">${tag}</div>
    <div class="cv-tt-grid">${breakdown}</div>
    <hr class="cv-tt-sep">
    <div class="cv-tt-foot"><span class="cv-tt-fl">선택 화물 24M 합계 · 항해 ${r.calls||0} · 선박 ${r.vessels||0}</span><span class="cv-tt-fv">${_cvFmt(filteredTotal)} TON</span></div>`;
}

// Cycle 5: 라우트를 quadratic Bezier 곡선으로 표현. 두 항만 사이 중간점에
// perpendicular offset(거리의 18%)를 적용한 컨트롤 포인트로 휘어진 곡선.
// 같은 방향(rotate 90° clockwise)으로 일관되게 휘어 시각적 통일.
// 입자도 동일 곡선 위에서 보간되도록 _route._curve 캐시 사용.
const _CV_BEZIER_SAMPLES = 32;
const _CV_BEZIER_OFFSET = 0.18;

function _cvComputeRouteCurve(r) {
  if (r._curve) return r._curve;
  const latO = r.lat_o, lonO = r.lon_o;
  const latD = r.lat_d, lonD = r.lon_d;
  if (r.origin === r.destination) {
    r._curve = null;
    return null;
  }
  const dLat = latD - latO;
  const dLon = lonD - lonO;
  const len = Math.sqrt(dLat * dLat + dLon * dLon) || 1;
  // Perpendicular vector — rotate (dLat, dLon) 90° clockwise: (dLon, -dLat)
  // 정규화 후 길이의 일정 비율로 offset.
  const pLat = dLon / len;
  const pLon = -dLat / len;
  const mLat = (latO + latD) / 2;
  const mLon = (lonO + lonD) / 2;
  const cLat = mLat + pLat * len * _CV_BEZIER_OFFSET;
  const cLon = mLon + pLon * len * _CV_BEZIER_OFFSET;
  const points = [];
  for (let i = 0; i <= _CV_BEZIER_SAMPLES; i++) {
    const t = i / _CV_BEZIER_SAMPLES;
    const mt = 1 - t;
    points.push([
      mt * mt * latO + 2 * mt * t * cLat + t * t * latD,
      mt * mt * lonO + 2 * mt * t * cLon + t * t * lonD,
    ]);
  }
  r._curve = { points, ctrlLat: cLat, ctrlLon: cLon };
  return r._curve;
}

// Bezier 곡선 위의 점 — 입자 애니메이션에서 매 프레임 호출.
function _cvBezierAt(r, t) {
  const curve = _cvComputeRouteCurve(r);
  if (!curve) return null;
  const mt = 1 - t;
  return {
    lat: mt * mt * r.lat_o + 2 * mt * t * curve.ctrlLat + t * t * r.lat_d,
    lon: mt * mt * r.lon_o + 2 * mt * t * curve.ctrlLon + t * t * r.lon_d,
  };
}

function _cvRenderLines() {
  for (const l of _cvState.lines) l.remove();
  _cvState.lines = [];
  if (!_cvState.map || !_cvState.showLines) return;
  const routes = _cvState.ROUTES || [];
  if (!routes.length) return;
  const maxV = Math.max(...routes.map(r => r.ton_24m || 0), 1);
  [...routes].sort((a, b) => (a.ton_24m || 0) - (b.ton_24m || 0)).forEach(r => {
    const v = r.ton_24m || 0;
    if (v <= 0) return;
    const w = 0.5 + Math.sqrt(v / maxV) * 3.5;
    const color = _cvCatColor(r.category);
    if (r.origin === r.destination) {
      // STS 자기루프 — 점선 동심원
      const m = L.circleMarker([r.lat_o, r.lon_o], {
        radius: Math.max(4, w * 1.4), fillColor: color, color: color,
        weight: 1.0, opacity: 0.5, fillOpacity: 0,
        dashArray: "3,3",
      });
      m.bindTooltip(_cvRouteTooltip(r), { className: "cv-tt", sticky: true, opacity: 1 });
      m.addTo(_cvState.map);
      _cvState.lines.push(m);
      return;
    }
    const curve = _cvComputeRouteCurve(r);
    const line = L.polyline(curve.points, {
      color, weight: w, opacity: 0.22, lineCap: "round", smoothFactor: 1.0,
    });
    line.bindTooltip(_cvRouteTooltip(r), { className: "cv-tt", sticky: true, opacity: 1 });
    line.addTo(_cvState.map);
    _cvState.lines.push(line);
  });
}

function _cvRebuild() {
  const keys = [..._cvState.selComms];
  const PORTS = _cvBuildPorts(keys);
  // Leaflet inside a hidden tab can mis-size — force invalidate when shown.
  if (_cvState.map) setTimeout(() => _cvState.map.invalidateSize(), 0);
  _cvUpdateStats(PORTS);
  _cvRenderLines();
  _cvRenderCircles(PORTS);
  _cvRenderSidebar(PORTS);
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
  Plotly.newPlot("fl-class-donut", [{
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
  Plotly.newPlot("fl-age-bars", [{
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

// Sourced from fleet_owners.json — full cargo fleet (kapal.dephub.go.id).
// Each owner entry: {owner, vessels, sum_gt, avg_age_gt_weighted,
// top_flag, class_mix:{Container:n, Bulk Carrier:n, Tanker:n, ...},
// tanker_subclass_mix:{}}.
function drawFleetOwnerBars(owners) {
  if (!owners.length) return;
  const top = (owners || []).slice(0, 25);
  // Truncate long names and append top_flag chip for foreign-flag operators
  const labels = top.map(o => {
    const flagChip = o.top_flag && o.top_flag !== "Indonesia" ? ` 🌐${o.top_flag}` : "";
    const name = o.owner.length > 38 ? o.owner.slice(0, 36) + "…" : o.owner;
    return `${name}${flagChip}`;
  }).reverse();
  const counts = top.map(o => o.vessels).reverse();
  const gts = top.map(o => o.sum_gt).reverse();
  const ages = top.map(o => o.avg_age_gt_weighted).reverse();
  // top-2 classes per owner, for hover detail
  const mixSummaries = top.map(o => {
    const mix = o.class_mix || {};
    return Object.entries(mix).sort((a, b) => b[1] - a[1])
      .slice(0, 3).map(([k, v]) => `${k} ${v}`).join(" · ") || "-";
  }).reverse();
  Plotly.newPlot("fl-owner-bars", [{
    x: counts,
    y: labels,
    type: "bar",
    orientation: "h",
    marker: {
      color: gts,
      colorscale: "Blues",
      cmin: 0,
      cmax: Math.max(...gts, 1),
      line: { color: "#1e293b", width: 0.4 },
      colorbar: { title: "총 GT", thickness: 8, len: 0.5 },
    },
    text: counts.map(v => `${v}척`),
    textposition: "outside",
    cliponaxis: false,
    customdata: top.map((_o, i) => [
      gts[counts.length - 1 - i] ?? 0,
      ages[counts.length - 1 - i],
      mixSummaries[i],
    ]),
    hovertemplate:
      "<b>%{y}</b><br>" +
      "%{x} 척 · 총 GT %{customdata[0]:,.0f}<br>" +
      "평균 선령 (GT 가중) %{customdata[1]:.1f}년<br>" +
      "Class mix — %{customdata[2]}<extra></extra>",
  }], {
    margin: { t: 10, l: 280, r: 70, b: 40 },
    xaxis: { title: "보유 척수 (cargo only)" },
  }, { displayModeBar: false, responsive: true });
}

// Per-owner Vessel Class mix (stacked bars). Replaces the old tanker-only
// subclass mix chart. Uses _CARGO_CLASS_PALETTE so colors match the Cargo
// tab map legend conventions.
const FL_CLASS_PALETTE = {
  "Container":     "#0284c7",
  "Bulk Carrier":  "#7c3aed",
  "Tanker":        "#1A3A6B",
  "General Cargo": "#0891b2",
  "Other Cargo":   "#65a30d",
  "Other":         "#94a3b8",
};
function drawFleetOwnerClassmix(owners) {
  if (!owners.length) return;
  const topN = (owners || []).slice(0, 8);
  const classOrder = ["Container", "Bulk Carrier", "Tanker", "General Cargo", "Other Cargo", "Other"];
  const traces = classOrder
    .filter(cls => topN.some(o => (o.class_mix || {})[cls]))
    .map(cls => ({
      x: topN.map(o => o.owner.length > 22 ? o.owner.slice(0, 20) + "…" : o.owner),
      y: topN.map(o => (o.class_mix || {})[cls] || 0),
      name: cls,
      type: "bar",
      marker: { color: FL_CLASS_PALETTE[cls] || "#94a3b8" },
      hovertemplate: `<b>%{x}</b><br>${cls}: %{y} 척<extra></extra>`,
    }));
  Plotly.newPlot("fl-owner-classmix", traces, {
    barmode: "stack",
    margin: { t: 10, l: 60, r: 20, b: 110 },
    xaxis: { tickangle: -25 },
    yaxis: { title: "척수" },
    legend: { orientation: "h", y: -0.35, font: { size: 10 } },
  }, { displayModeBar: false, responsive: true });
}

// ────────────────────────────────────────────────────────────
// Market 탭 — 표 + 그래프 중심 (2026-05-27 모던 재설계).
//   docs/data/market.json 의 indices / scrap / fuel / vessel pricing /
//   S&P / news / events 를 정렬 가능한 표로 노출. 부가 카드·설명은 제거.
// ────────────────────────────────────────────────────────────
const mkSort = {
  indices: { key: "value", dir: -1 },
  sp:      { key: "price", dir: -1 },
  news:    { key: "date",  dir: -1 },
  events:  { key: "date",  dir:  1 },
};

const _fmtNum = (v) => v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
const _fmtPct = (v) => v == null ? '<span class="text-slate-300">—</span>'
  : `<span class="${v >= 0 ? "text-emerald-600" : "text-rose-600"} font-medium">${v >= 0 ? "+" : ""}${v.toFixed(1)}%</span>`;

function _mkSrcLink(name, url) {
  const label = _esc(name || "—");
  return url
    ? `<a href="${_esc(url)}" target="_blank" rel="noopener" class="text-sky-700 hover:underline">${label}</a>`
    : `<span class="text-slate-500">${label}</span>`;
}

function _mkSortRows(rows, key, dir) {
  rows.sort((a, b) => {
    const av = a[key], bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "string") return av.localeCompare(bv) * dir;
    return (av - bv) * dir;
  });
}

function _mkWireSort(tableId, stateKey, redraw) {
  const t = document.getElementById(tableId);
  if (!t || t.dataset.sortWired) return;
  t.dataset.sortWired = "1";
  t.querySelectorAll("th[data-sort]").forEach(th => {
    th.classList.add("cursor-pointer", "select-none", "hover:bg-slate-100");
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      const s = mkSort[stateKey];
      if (s.key === k) s.dir *= -1;
      else { s.key = k; s.dir = (k === "name" || k === "date" || k === "as_of") ? 1 : -1; }
      redraw();
    });
  });
}

function _mkRefreshSortArrows(tableId, stateKey) {
  const t = document.getElementById(tableId);
  if (!t) return;
  const s = mkSort[stateKey];
  t.querySelectorAll("th[data-sort]").forEach(th => {
    const base = th.dataset.sortBase || (th.dataset.sortBase = th.innerHTML);
    th.innerHTML = base + (th.dataset.sort === s.key
      ? ` <span class="text-slate-400 text-[10px]">${s.dir > 0 ? "▲" : "▼"}</span>` : "");
  });
}

// ---- Indices: combined bar chart (color-coded by sector) + 3 sub-tables ----
const MK_SECTOR_ORDER  = ["Dry Bulk", "Tanker", "Container"];
const MK_SECTOR_COLORS = { "Dry Bulk": "#0369a1", "Tanker": "#7c3aed", "Container": "#059669" };

function _mkClassifySector(name) {
  const n = String(name || "").toLowerCase();
  if (/(ncfi|ningbo|contex|container)/.test(n))                        return "Container";
  if (/(bdti|bcti|tanker|vlcc|suezmax|aframax|lr1|lr2|\bmr\b)/.test(n)) return "Tanker";
  return "Dry Bulk";
}

function _mkRenderIndicesChart(rows) {
  const el = document.getElementById("mk-indices-chart");
  if (!el || !rows.length) return;
  // Sort within each sector by wow desc, then concat in sector order so the
  // bar chart visually groups them.
  const ordered = [];
  for (const s of MK_SECTOR_ORDER) {
    const grp = rows.filter(r => (r.sector || _mkClassifySector(r.name)) === s);
    grp.sort((a, b) => (b.wow_pct ?? -999) - (a.wow_pct ?? -999));
    ordered.push(...grp);
  }
  const trace = {
    type: "bar", orientation: "h",
    x: ordered.map(r => r.wow_pct ?? 0),
    y: ordered.map(r => r.name),
    marker: { color: ordered.map(r => MK_SECTOR_COLORS[r.sector || _mkClassifySector(r.name)] || "#475569") },
    text: ordered.map(r => r.wow_pct == null ? "—" : `${r.wow_pct >= 0 ? "+" : ""}${r.wow_pct.toFixed(1)}%`),
    textposition: "outside",
    customdata: ordered.map(r => [_fmtNum(r.value), r.unit || "", r.sector || _mkClassifySector(r.name)]),
    hovertemplate: "<b>%{y}</b><br>Sector: %{customdata[2]}<br>Value: %{customdata[0]} %{customdata[1]}<br>W-o-W: %{x:+.1f}%<extra></extra>",
    cliponaxis: false,
  };
  // Sector divider shapes + labels
  const shapes = [], annotations = [];
  let yi = 0;
  for (const s of MK_SECTOR_ORDER) {
    const grp = ordered.filter(r => (r.sector || _mkClassifySector(r.name)) === s);
    if (!grp.length) continue;
    if (yi > 0) {
      shapes.push({
        type: "line", x0: 0, x1: 1, xref: "paper",
        y0: yi - 0.5, y1: yi - 0.5, yref: "y",
        line: { color: "#e2e8f0", width: 1, dash: "solid" },
      });
    }
    annotations.push({
      x: 1, xref: "paper", xanchor: "right",
      y: yi + grp.length - 0.5, yref: "y", yanchor: "top",
      text: `<b>${s}</b>`,
      showarrow: false,
      font: { size: 10, color: MK_SECTOR_COLORS[s] || "#475569" },
    });
    yi += grp.length;
  }
  Plotly.newPlot("mk-indices-chart", [trace], {
    margin: { t: 16, l: 240, r: 64, b: 36 },
    xaxis: { title: "W-o-W %", zeroline: true, zerolinecolor: "#cbd5e1", gridcolor: "#f1f5f9" },
    yaxis: { automargin: true, tickfont: { size: 11 }, autorange: "reversed" },
    paper_bgcolor: "white", plot_bgcolor: "white",
    showlegend: false,
    shapes, annotations,
  }, { displayModeBar: false, responsive: true });
}

function _mkRenderIndicesSectors(rows) {
  const host = document.getElementById("mk-indices-sectors");
  if (!host) return;
  // Group rows by sector
  const grouped = new Map(MK_SECTOR_ORDER.map(s => [s, []]));
  for (const r of rows) {
    const s = r.sector || _mkClassifySector(r.name);
    if (!grouped.has(s)) grouped.set(s, []);
    grouped.get(s).push(r);
  }
  // Default sort within a sector: value desc
  const sortDir = mkSort.indices.dir;
  const sortKey = mkSort.indices.key;
  for (const arr of grouped.values()) {
    _mkSortRows(arr, sortKey, sortDir);
  }

  const renderTbl = (sector, arr) => {
    const color = MK_SECTOR_COLORS[sector] || "#475569";
    return `<div class="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <div class="flex items-center gap-2.5 px-4 py-2 bg-slate-50/60 border-b border-slate-200">
        <span class="inline-block w-1 h-4 rounded-sm" style="background:${color}"></span>
        <span class="text-[12px] font-semibold text-slate-700">${sector}</span>
        <span class="text-[11px] text-slate-400 font-mono ml-1">${arr.length} rows</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-[13px]" data-sec-table="${sector}">
          <thead class="bg-slate-50 text-slate-500 text-[11px] uppercase tracking-wide">
            <tr>
              <th class="px-3 py-2 text-left font-medium" data-sort="name">Index</th>
              <th class="px-3 py-2 text-right font-medium" data-sort="value">Value</th>
              <th class="px-3 py-2 text-left font-medium">Unit</th>
              <th class="px-3 py-2 text-right font-medium" data-sort="wow_pct">W-o-W</th>
              <th class="px-3 py-2 text-left font-medium" data-sort="as_of">As of</th>
              <th class="px-3 py-2 text-left font-medium">Source</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            ${arr.map(r => `<tr class="hover:bg-slate-50">
              <td class="px-3 py-2 font-medium text-slate-800">${_esc(r.name)}</td>
              <td class="px-3 py-2 text-right font-mono font-semibold text-slate-900">${_fmtNum(r.value)}</td>
              <td class="px-3 py-2 text-slate-500 text-[12px]">${_esc(r.unit || "—")}</td>
              <td class="px-3 py-2 text-right">${_fmtPct(r.wow_pct)}</td>
              <td class="px-3 py-2 text-slate-500 font-mono text-[12px]">${_esc(r.as_of || "—")}</td>
              <td class="px-3 py-2 text-[12px] truncate max-w-[28rem]">${_mkSrcLink(r.source_name, r.source_url)}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>`;
  };

  host.innerHTML = MK_SECTOR_ORDER
    .filter(s => (grouped.get(s) || []).length > 0)
    .map(s => renderTbl(s, grouped.get(s)))
    .join("");

  // Wire sort headers on each sub-table; sort applies to all sub-tables.
  host.querySelectorAll("table[data-sec-table] th[data-sort]").forEach(th => {
    th.classList.add("cursor-pointer", "select-none", "hover:bg-slate-100");
    th.addEventListener("click", () => {
      const k = th.dataset.sort;
      if (mkSort.indices.key === k) mkSort.indices.dir *= -1;
      else { mkSort.indices.key = k; mkSort.indices.dir = (k === "name" || k === "as_of") ? 1 : -1; }
      _mkRenderIndicesSectors(rows);
      _mkRenderIndicesChart(rows);
    });
  });
  // Visual sort arrows
  host.querySelectorAll("table[data-sec-table]").forEach(t => {
    t.querySelectorAll("th[data-sort]").forEach(th => {
      const base = th.dataset.sortBase || (th.dataset.sortBase = th.innerHTML);
      th.innerHTML = base + (th.dataset.sort === mkSort.indices.key
        ? ` <span class="text-slate-400 text-[10px]">${mkSort.indices.dir > 0 ? "▲" : "▼"}</span>` : "");
    });
  });

  const cnt = document.getElementById("mk-cnt-indices");
  if (cnt) cnt.textContent = `${rows.length} rows · ${MK_SECTOR_ORDER.filter(s => (grouped.get(s) || []).length).length} sectors`;
}

// ---- Scrap matrix: pivot dry+tanker into a single region table ----
function _mkRenderScrapMatrix(dry, tnk) {
  const host = document.getElementById("mk-scrap-tbody");
  if (!host) return;
  const byRegion = new Map();
  const seed = (reg) => byRegion.set(reg, { region: reg, bulker: null, tanker: null, as_of: null, src_name: null, src_url: null });
  for (const r of dry || []) {
    if (!byRegion.has(r.region)) seed(r.region);
    const o = byRegion.get(r.region);
    o.bulker = r.ldt_usd; o.as_of = r.as_of; o.src_name = r.source_name; o.src_url = r.source_url;
  }
  for (const r of tnk || []) {
    if (!byRegion.has(r.region)) seed(r.region);
    const o = byRegion.get(r.region);
    o.tanker = r.ldt_usd; if (!o.as_of) o.as_of = r.as_of; if (!o.src_name) { o.src_name = r.source_name; o.src_url = r.source_url; }
  }
  const rows = [...byRegion.values()].sort((a, b) => (b.bulker ?? 0) - (a.bulker ?? 0));
  host.innerHTML = rows.map(r => `<tr class="hover:bg-slate-50">
    <td class="px-3 py-2.5 font-medium text-slate-800">${_esc(r.region)}</td>
    <td class="px-3 py-2.5 text-right font-mono">${r.bulker == null ? '<span class="text-slate-300">—</span>' : _fmtNum(r.bulker)}</td>
    <td class="px-3 py-2.5 text-right font-mono">${r.tanker == null ? '<span class="text-slate-300">—</span>' : _fmtNum(r.tanker)}</td>
    <td class="px-3 py-2.5 text-slate-500 font-mono text-[12px]">${_esc(r.as_of || "—")}</td>
    <td class="px-3 py-2.5 text-[12px] truncate max-w-[24rem]">${_mkSrcLink(r.src_name, r.src_url)}</td>
  </tr>`).join("");
  const cnt = document.getElementById("mk-cnt-scrap");
  if (cnt) cnt.textContent = `${rows.length} regions`;
}

// ---- Fuel / domestic commodities ----
function _mkRenderFuelTable(fs) {
  const host = document.getElementById("mk-fuel-tbody");
  if (!host) return;
  const flat = [];
  const push = (label, arr) => (arr || []).forEach(o => flat.push({
    label, value: o.value ?? o.price ?? o.ldt_usd,
    unit: o.unit, as_of: o.as_of,
    src_name: o.source_name || (o.sources?.[0]?.name),
    src_url: o.source_url || (o.sources?.[0]?.url),
  }));
  push("CPO Price (GAPKI)", fs.cpo_price_index_gapki);
  push("Solar B40 / HSD",   fs.solar_b40_hsd);
  push("HFO 180 / MFO",     fs.hfo_180_mfo);
  push("Scrap — Domestic",  fs.scrap_domestic);
  host.innerHTML = flat.map(r => `<tr class="hover:bg-slate-50">
    <td class="px-3 py-2.5 font-medium text-slate-800">${_esc(r.label)}</td>
    <td class="px-3 py-2.5 text-right font-mono">${_fmtNum(r.value)}</td>
    <td class="px-3 py-2.5 text-slate-500 text-[12px]">${_esc(r.unit || "—")}</td>
    <td class="px-3 py-2.5 text-slate-500 font-mono text-[12px]">${_esc(r.as_of || "—")}</td>
    <td class="px-3 py-2.5 text-[12px] truncate max-w-[24rem]">${_mkSrcLink(r.src_name, r.src_url)}</td>
  </tr>`).join("");
  const cnt = document.getElementById("mk-cnt-fuel");
  if (cnt) cnt.textContent = `${flat.length} items`;
}

// ---- Vessel pricing: web listings, chart + table ----
function _mkRenderVesselChart(rows) {
  const el = document.getElementById("mk-vessel-chart");
  if (!el || !rows.length) return;
  const trace = {
    type: "bar",
    x: rows.map(r => `${r.category} ${r.size}`),
    y: rows.map(r => (r.value_low + r.value_high) / 2),
    error_y: { type: "data",
      symmetric: false,
      array:      rows.map(r => r.value_high - (r.value_low + r.value_high) / 2),
      arrayminus: rows.map(r => (r.value_low + r.value_high) / 2 - r.value_low),
      color: "#475569", thickness: 1, width: 4,
    },
    marker: { color: "#0284c7" },
    hovertemplate: "<b>%{x}</b><br>Range: %{customdata[0]} ~ %{customdata[1]} M IDR<extra></extra>",
    customdata: rows.map(r => [_fmtNum(r.value_low), _fmtNum(r.value_high)]),
  };
  Plotly.newPlot("mk-vessel-chart", [trace], {
    margin: { t: 16, l: 56, r: 16, b: 90 },
    xaxis: { tickangle: -32, automargin: true, tickfont: { size: 10 } },
    yaxis: { title: "millions IDR", gridcolor: "#f1f5f9" },
    paper_bgcolor: "white", plot_bgcolor: "white",
    showlegend: false,
  }, { displayModeBar: false, responsive: true });
}

function _mkRenderVesselTable(markets) {
  const host = document.getElementById("mk-vessel-tbody");
  if (!host) return;
  const rows = [];
  for (const mk of markets || []) {
    for (const c of mk.categories || []) {
      const className = (c.label || "").replace(/—.*$/, "").trim();
      for (const r of c.rows || []) {
        if (r.value_low == null && r.value_high == null) continue;
        rows.push({ category: className, ...r,
          src_name: r.sources?.[0]?.name, src_url: r.sources?.[0]?.url });
      }
    }
  }
  host.innerHTML = rows.map(r => `<tr class="hover:bg-slate-50">
    <td class="px-3 py-2.5 text-[12px] text-slate-600">${_esc(r.category)}</td>
    <td class="px-3 py-2.5 font-medium text-slate-800">${_esc(r.size)}</td>
    <td class="px-3 py-2.5 text-slate-500 text-[12px]">${_esc(r.year_built || "—")}</td>
    <td class="px-3 py-2.5 text-right font-mono">${_fmtNum(r.value_low)}</td>
    <td class="px-3 py-2.5 text-right font-mono font-semibold">${_fmtNum(r.value_high)}</td>
    <td class="px-3 py-2.5 text-[12px] truncate max-w-[24rem]">${_mkSrcLink(r.src_name, r.src_url)}</td>
  </tr>`).join("");
  const cnt = document.getElementById("mk-cnt-vessel");
  if (cnt) cnt.textContent = `${rows.length} listings`;
  _mkRenderVesselChart(rows);
}

// ---- S&P transactions ----
function _mkRenderSpTable(rows) {
  const host = document.getElementById("mk-sp-tbody");
  if (!host) return;
  const data = rows.map(r => ({
    name: r.vessel_name, type: r.type, dwt: r.dwt, year: r.year,
    price: r.price_musd, buyer: r.buyer, as_of: r.as_of,
    src_name: r.source_name, src_url: r.source_url,
  }));
  _mkSortRows(data, mkSort.sp.key, mkSort.sp.dir);
  host.innerHTML = data.map(r => `<tr class="hover:bg-slate-50">
    <td class="px-3 py-2.5 font-medium text-slate-800">${_esc(r.name)}</td>
    <td class="px-3 py-2.5 text-[12px] text-slate-600">${_esc(r.type)}</td>
    <td class="px-3 py-2.5 text-right font-mono text-slate-700">${r.dwt == null ? '<span class="text-slate-300">—</span>' : Number(r.dwt).toLocaleString()}</td>
    <td class="px-3 py-2.5 text-right font-mono text-slate-700">${r.year ?? "—"}</td>
    <td class="px-3 py-2.5 text-right font-mono font-semibold text-slate-900">${r.price == null ? "—" : "$" + Number(r.price).toFixed(1)}</td>
    <td class="px-3 py-2.5 text-[12px] text-slate-600">${_esc(r.buyer || "—")}</td>
    <td class="px-3 py-2.5 text-[12px] truncate max-w-[20rem]">${_mkSrcLink(r.src_name, r.src_url)}</td>
  </tr>`).join("");
  _mkWireSort("mk-sp-table", "sp", () => _mkRenderSpTable(rows));
  _mkRefreshSortArrows("mk-sp-table", "sp");
  const cnt = document.getElementById("mk-cnt-sp");
  if (cnt) cnt.textContent = `${rows.length} deals`;
}

// ---- Commodity news ----
function _mkRenderNewsTable(byTopic) {
  const host = document.getElementById("mk-news-tbody");
  if (!host) return;
  const data = [];
  for (const [topic, items] of Object.entries(byTopic || {})) {
    for (const it of items) {
      data.push({
        topic, name: it.title_ko || it.title, date: it.as_of,
        src_name: it.source_name, src_url: it.source_url,
      });
    }
  }
  _mkSortRows(data, mkSort.news.key, mkSort.news.dir);
  host.innerHTML = data.map(r => `<tr class="hover:bg-slate-50">
    <td class="px-3 py-2.5 text-[11px] uppercase tracking-wider text-slate-500 font-medium">${_esc(r.topic)}</td>
    <td class="px-3 py-2.5 text-slate-800">${_esc(r.name)}</td>
    <td class="px-3 py-2.5 text-slate-500 font-mono text-[12px]">${_esc(r.date || "—")}</td>
    <td class="px-3 py-2.5 text-[12px] truncate max-w-[24rem]">${_mkSrcLink(r.src_name, r.src_url)}</td>
  </tr>`).join("");
  _mkWireSort("mk-news-table", "news", () => _mkRenderNewsTable(byTopic));
  _mkRefreshSortArrows("mk-news-table", "news");
  const cnt = document.getElementById("mk-cnt-news");
  if (cnt) cnt.textContent = `${data.length} items`;
}

// ---- Events ----
function _mkRenderEventsTable(events) {
  const host = document.getElementById("mk-events-tbody");
  if (!host) return;
  const rows = (events?.upcoming || []).concat(events?.live || []).map(e => ({
    name: e.name, date: e.date, location: e.location,
    src_name: e.source_name, src_url: e.source_url,
  }));
  _mkSortRows(rows, mkSort.events.key, mkSort.events.dir);
  host.innerHTML = rows.map(r => `<tr class="hover:bg-slate-50">
    <td class="px-3 py-2.5 text-slate-500 font-mono text-[12px]">${_esc(r.date || "—")}</td>
    <td class="px-3 py-2.5 font-medium text-slate-800">${_esc(r.name)}</td>
    <td class="px-3 py-2.5 text-[12px] text-slate-600">${_esc(r.location || "—")}</td>
    <td class="px-3 py-2.5 text-[12px] truncate max-w-[24rem]">${_mkSrcLink(r.src_name, r.src_url)}</td>
  </tr>`).join("");
  _mkWireSort("mk-events-table", "events", () => _mkRenderEventsTable(events));
  _mkRefreshSortArrows("mk-events-table", "events");
  const cnt = document.getElementById("mk-cnt-events");
  if (cnt) cnt.textContent = `${rows.length} events`;
}

// ---- Build meta footer ----
function _mkRenderBuildMeta(m) {
  const el = document.getElementById("mk-build-meta");
  if (!el) return;
  const bm = m.build_meta || {};
  el.innerHTML = `run · ${_esc(m.build_run_id || "—")} · ${_esc(bm.collectors_run?.join(", ") || "—")} · ${bm.rows_published ?? 0} rows`;
}

// ---- Entry point ----
async function renderMarket() {
  const tabEl = document.getElementById("tab-market");
  if (!tabEl) return;
  setupSourceLabels(tabEl);
  let m;
  try {
    m = await loadJson("market.json");
  } catch (e) {
    tabEl.insertAdjacentHTML("beforeend",
      `<div class="m-4">${errorState(`market.json 로드 실패: ${e.message}`)}</div>`);
    return;
  }
  const rw = document.getElementById("mk-report-week");
  const asof = document.getElementById("mk-asof");
  if (rw)   rw.textContent = m.report_week ? `· ${m.report_week}` : "";
  if (asof) asof.textContent = `as of ${m.checked_date || m.last_updated || "—"}`;

  _mkRenderIndicesSectors(m.international_freight?.indices || []);
  _mkRenderIndicesChart(m.international_freight?.indices || []);
  _mkRenderScrapMatrix(m.international_freight?.scrap_dry_bulk, m.international_freight?.scrap_tanker);
  _mkRenderFuelTable(m.domestic_fuel_scrap || {});
  _mkRenderVesselTable(m.domestic_vessel_pricing?.markets || []);
  _mkRenderSpTable(m.international_freight?.sale_purchase_bulk || []);
  _mkRenderNewsTable(m.commodity_news || {});
  _mkRenderEventsTable(m.events || {});
  _mkRenderBuildMeta(m);
}


boot().catch(e => {
  console.error(e);
  document.body.insertAdjacentHTML("afterbegin",
    `<div class="m-4">${errorState(`초기 데이터 로드 실패: ${e.message}`)}</div>`);
});
