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

  // PR-33: default Tanker Sector to the most-recent FULL year so cards
  // align with the Cargo + Home year selectors.
  if (!tsState.activeYear) tsState.activeYear = _pickTankerSectorYear(tsState.tankerSubclass);
  buildTankerYearPills(tsState.tankerSubclass);

  // PR-34: surface honest period ranges on the chart headers so users see
  // exactly which months/years a 12M or 24M window covers.
  const periods = tsState.tankerSubclass?.monthly?.periods || [];
  const periodRange = periods.length
    ? `(${periods[0]} ~ ${periods[periods.length - 1]}, ${periods.length}개월)`
    : "";
  const scatterPeriodEl = document.getElementById("ts-scatter-period");
  if (scatterPeriodEl) scatterPeriodEl.textContent = periodRange;
  const monthlyPeriodEl = document.getElementById("ts-monthly-period");
  if (monthlyPeriodEl) monthlyPeriodEl.textContent = periodRange;
  // Commodity bar is the trailing 12 months
  const last12 = periods.slice(-12);
  const commodityPeriodEl = document.getElementById("ts-commodity-period");
  if (commodityPeriodEl && last12.length) {
    commodityPeriodEl.textContent =
      `(직전 12개월 ton 기준 · ${last12[0]} ~ ${last12[last12.length - 1]})`;
  }

  drawTankerCards();
  drawTankerScatter();
  drawTankerMonthly();
  drawTankerCommodityBars();
  drawTankerOperatorBars();
  drawTankerOperatorDonut();
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
  // PR-33: year-aware value resolver. When tsState.activeYear is set and
  // the card has ton_by_year, prefer those values; else fall back to the
  // legacy 12M fields. The card label flips accordingly.
  const mpy = tsState.tankerSubclass?.months_per_year || {};
  const activeYear = tsState.activeYear;
  const yearMonths = activeYear ? (mpy[activeYear] || 0) : 12;
  const yearLabel = activeYear
    ? `${activeYear}년${yearMonths < 12 ? ` (${yearMonths}mo)` : ""}`
    : "12M";
  host.innerHTML = cards.map(c => {
    const color = SUBCLASS_PALETTE[c.subclass] || "#64748b";
    let tonVal = c.ton_last_12m;
    let yoy = c.yoy_pct;
    if (activeYear && c.ton_by_year && activeYear in c.ton_by_year) {
      tonVal = c.ton_by_year[activeYear];
      // Suppress YoY on partial years (misleading vs full 12 months)
      yoy = yearMonths === 12 ? (c.yoy_by_year || {})[activeYear] : null;
    }
    const tonStr = fmtTon(tonVal);
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
          <span class="text-xs text-slate-500">tons (${yearLabel})</span>
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
  "fleet":         "Fleet",
  "cargo":         "Cargo",
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
    if (tab === "fleet" && !state.loaded.has("fleet")) {
      await renderFleet();
      state.loaded.add("fleet");
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

  // Parallel: KPI hero, timeseries, map data, world topology, year cuts.
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
  // PR-35: cargo_yearly.json is optional — Home map year buttons gracefully
  // disappear if it failed to load. The other tabs already handle absence.
  try { homeState.cargoYearly = await loadDerived("cargo_yearly.json"); }
  catch (e) { homeState.cargoYearly = null; }
  homeState.timeseries = ts;   // PR-35: needed by _refreshHomeMapPeriodLabel re-renders

  renderHomeKpi(kpis);
  renderHomeTimeseries(ts);
  // PR-35: inject year buttons into the period control BEFORE binding
  // so a single bindMapControls() pass wires them all.
  _injectHomeMapYearButtons();
  bindMapControls();
  drawHomeMap();
  fillSectorStrip(kpis?.sector_breakdown || []);
  // PR-34/35: surface the active period on the map title. Re-evaluated on
  // each drawHomeMap() because the period button can switch between rolling
  // 24M and a calendar year.
  _refreshHomeMapPeriodLabel(ts);
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
      renderHomeKpi(payload);
      _buildHomeYearPills(payload, y);
    });
  });
  if (banner) {
    const isPartial = (mpy[activeYear] || 0) < 12;
    banner.textContent = isPartial
      ? `⚠️ ${activeYear}년은 부분 연도 (${mpy[activeYear]}mo) — YoY 비교 시 주의.`
      : `${activeYear}년 (12개월).`;
  }
}

function renderHomeKpi(payload) {
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

  const cards = payload.kpis.map(k => {
    if (k.id === "total_12m_ton") {
      const v = yearValue(k);
      const partial = v.months < 12 ? `<span class="text-amber-600 text-xs">부분 ${v.months}mo</span>` : "";
      return `<div class="kpi-card-large">
        <div class="kpi-label">${yearLabel} 총 물동량 (인도네시아)</div>
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
        <div class="kpi-label">${yearLabel} 탱커 물동량</div>
        <div>
          <div class="kpi-value-large">${fmtTon(v.ton)}<span class="text-base text-slate-400 ml-1">tons</span></div>
          <div class="kpi-sub-large">${trend(v.yoy)} ${partial}</div>
        </div>
      </div>`;
    }
    if (k.id === "tanker_fleet") {
      const age = k.avg_age_gt_weighted == null ? "—" : `${k.avg_age_gt_weighted.toFixed(1)}년`;
      const subParts = [];
      if (k.cargo_count != null)  subParts.push(`화물 ${fmt(k.cargo_count)}`);
      if (k.tanker_count != null) subParts.push(`탱커 ${fmt(k.tanker_count)}`);
      const subBreakdown = subParts.length
        ? `<span class="text-slate-400">그중 ${subParts.join(" · ")}척</span> · `
        : "";
      return `<div class="kpi-card-large" title="Source: kapal.dephub.go.id/ditkapel_service/data_kapal/">
        <div class="kpi-label">선박 등록 척수 <span class="text-[10px] text-slate-400 font-normal">(kapal.dephub.go.id)</span></div>
        <div>
          <div class="kpi-value-large">${fmt(k.value_count || 0)}<span class="text-base text-slate-400 ml-1">척</span></div>
          <div class="kpi-sub-large">${subBreakdown}<span class="text-slate-600">평균 선령</span> ${age} <span class="text-slate-400">(GT 가중, 탱커 기준)</span></div>
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
    if (homeState.filterCategory === "bulk") {
      notes.push("드라이벌크 OD 분리 미구현 — 탱커 데이터 표시 중");
    }
    if (homeState.filterPeriod === "12m") {
      notes.push("12M OD 미산출 — 24M 누계 표시 중");
    }
    if (homeState.filterTraffic === "ln") {
      notes.push("국제 OD 미분리 — 전체(국내+국제) 표시 중");
    }
    routes = (homeState.mapData.routes_top30 || []).slice();
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

  // jang1117 mirror no longer renders the "Top 25 owners" card, so we
  // only fetch fleet_vessels.json here. fleet_owners.json stays in the
  // bundle for other consumers but is not required for the tab.
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

  // Initial state object — jang1117 parity (no sector/subclass/age/owner/flag).
  if (!tabEl._fleetState) {
    tabEl._fleetState = {
      jenis: new Set(),                // checkbox selection of JenisDetailKet
      jenisQuery: "",                  // search box content
      jenisExclude: false,             // 제외 모드 toggle
      name: "",                        // 선박명 substring
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
  _renderFleetView();
}

function _idxOf(fv, name) { return (fv.cols || []).indexOf(name); }

function _buildFleetFilters(fv) {
  // jang1117 mirror: only build the Vessel Type list + table header.
  // (No sector/subclass/age/flag controls — removed.)
  _renderFleetJenisList(fv);

  const hbadge = document.getElementById("fl-hbadge");
  if (hbadge) hbadge.textContent = `${fv.rows.length.toLocaleString()} rows`;

  // Table header
  const th = document.getElementById("fl-thead-row");
  if (th && !th.dataset.wired) {
    th.dataset.wired = "1";
    const cols = [
      ["nama", "선박명"], ["owner", "선주"],
      ["jenis", "Vessel Type"],
      ["gt", "GT"], ["loa", "LOA (m)"],
      ["lebar", "Width (m)"], ["dalam", "Depth (m)"],
      ["tahun", "건조"], ["age", "선령"],
      ["flag", "국적"],
      ["mesin", "엔진"], ["mesin_type", "엔진 타입"],
      ["imo", "IMO"], ["call_sign", "Call Sign"],
    ];
    th.innerHTML = cols.map(([k, l]) =>
      `<th data-col="${k}" class="px-2 py-1 text-left font-semibold text-slate-600 border-b border-slate-200 cursor-pointer hover:bg-slate-100 select-none">${l} <span class="text-slate-300" data-sort-marker></span></th>`
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

  // jang1117 mirror: single column, just [☑] name (count). No sector chip.
  host.innerHTML = items.map(it => {
    const checked = st.jenis.has(it.name) ? "checked" : "";
    return `<label class="flex items-center gap-1.5 px-1 py-0.5 rounded hover:bg-slate-100 cursor-pointer" title="${_esc(it.name)}">
      <input type="checkbox" data-jenis="${_esc(it.name)}" ${checked} class="cursor-pointer">
      <span class="truncate flex-1">${_esc(it.name)}</span>
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
  let sumGt = 0, nGt = 0, sumAgeGt = 0, sumYrW = 0;
  let sumLoa = 0, nLoa = 0, sumW = 0, nW = 0, sumD = 0, nD = 0;
  const jenisSet = new Set();
  for (const r of rows) {
    const gt = r[I.gt] || 0;
    if (gt > 0) { sumGt += gt; nGt++; }
    const age = r[I.age];
    const yr = r[I.tahun];
    if (gt > 0 && yr) { sumAgeGt += age * gt; sumYrW += yr * gt; }
    if ((r[I.loa] || 0) > 0)   { sumLoa += r[I.loa]; nLoa++; }
    if ((r[I.lebar] || 0) > 0) { sumW   += r[I.lebar]; nW++; }
    if ((r[I.dalam] || 0) > 0) { sumD   += r[I.dalam]; nD++; }
    if (r[I.jenis]) jenisSet.add(r[I.jenis]);
  }
  const avgGt = nGt > 0 ? sumGt / nGt : 0;
  const avgAge = sumGt > 0 ? sumAgeGt / sumGt : null;
  const avgYr = sumGt > 0 ? sumYrW / sumGt : null;
  // jang1117 KPI writes — every setter guarded so a missing element
  // can't kill the render. Existence-checked once at the top to keep
  // hot path lean.
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };
  set("fl-kpi-count", fmtCount(rows.length));
  set("fl-kpi-pct",
    `${fmtCount(rows.length)} / ${fmtCount(totalRows)}` +
    (totalRows > 0 ? ` (${(rows.length / totalRows * 100).toFixed(1)}%)` : ""));
  set("fl-kpi-jenis", fmtCount(jenisSet.size));
  set("fl-kpi-avggt", avgGt ? fmtCount(Math.round(avgGt)) : "—");
  set("fl-kpi-avgyr", avgYr ? `${avgYr.toFixed(0)}` : "—");
  set("fl-kpi-avgage", avgAge != null ? `선령 ${avgAge.toFixed(1)}년` : "선령 —");
  // 평균 제원 (치수 요약) — 4 sub-values
  set("fl-avg-gt",  avgGt ? fmtCount(Math.round(avgGt)) : "—");
  set("fl-avg-loa", nLoa ? (sumLoa / nLoa).toFixed(1) : "—");
  set("fl-avg-w",   nW   ? (sumW   / nW).toFixed(1)   : "—");
  set("fl-avg-d",   nD   ? (sumD   / nD).toFixed(1)   : "—");

  // ---- charts (each guarded — missing target = no-op, no throw) ----
  try { _drawFlChartYear(rows, I); }       catch (e) { console.error("Year chart:", e); }
  try { _drawFlChartType(rows, I); }       catch (e) { console.error("Type chart:", e); }
  try { _drawFlChartEngineType(rows, I); } catch (e) { console.error("EngineType chart:", e); }
  try { _drawFlChartEngineName(rows, I); } catch (e) { console.error("EngineName chart:", e); }
  try { _drawFlChartFlag(rows, I); }       catch (e) { console.error("Flag chart:", e); }
  try { _drawFlChartGtHist(rows, I); }     catch (e) { console.error("GT hist:", e); }

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

  // ---- Sortable + paginated table (jang1117 mirror: 100 per page) ----
  // PR — pagination state lives on _fleetPage; clamp when filter changes.
  if (typeof tabEl._fleetPage !== "number") tabEl._fleetPage = 1;
  const pageSize = 100;
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  if (tabEl._fleetPage > totalPages) tabEl._fleetPage = 1;
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
  document.querySelectorAll("#fl-thead-row th[data-col]").forEach(h => {
    const m = h.querySelector("[data-sort-marker]");
    if (!m) return;
    m.textContent = h.dataset.col === st.sortCol ? (st.sortDir === "asc" ? "▲" : "▼") : "";
  });
}

// Render pagination controls (jang1117 .pgn equivalent).
function _renderFleetPagination(total, page, pageSize, totalPages) {
  const host = document.getElementById("fl-pgn");
  if (!host) return;
  if (total === 0) {
    host.innerHTML = `<span class="text-slate-400">결과 없음</span>`;
    return;
  }
  // Compact pager: ◀ prev | 1 ... [page] ... totalPages | next ▶
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

  const btn = (label, target, disabled, active) =>
    `<button type="button" data-page="${target ?? ""}" ` +
    `class="px-2 py-0.5 rounded border ${active ? "border-blue-500 bg-blue-50 text-blue-700" : "border-slate-200 hover:bg-slate-50"} ${disabled ? "opacity-40 cursor-not-allowed" : ""}" ` +
    `${disabled ? "disabled" : ""}>${label}</button>`;
  host.innerHTML =
    btn("◀", page - 1, page <= 1, false) +
    uniq.map(p => p === "…"
      ? `<span class="px-1 text-slate-400">…</span>`
      : btn(p, p, false, p === page)).join("") +
    btn("▶", page + 1, page >= totalPages, false);
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
  body.innerHTML = top.map(r => {
    const flag = r[I.flag] || "Indonesia";
    return `<tr class="hover:bg-slate-50 border-b border-slate-100">
      <td class="px-2 py-1 font-medium text-slate-800">${_esc(r[I.nama])}</td>
      <td class="px-2 py-1 text-slate-600">${_esc(r[I.owner])}</td>
      <td class="px-2 py-1">${_esc(r[I.jenis])}</td>
      <td class="px-2 py-1 text-right font-mono">${(r[I.gt] || 0).toLocaleString()}</td>
      <td class="px-2 py-1 text-right font-mono">${(r[I.loa] || 0).toFixed(1)}</td>
      <td class="px-2 py-1 text-right font-mono">${(r[I.lebar] || 0).toFixed(1)}</td>
      <td class="px-2 py-1 text-right font-mono">${(r[I.dalam] || 0).toFixed(1)}</td>
      <td class="px-2 py-1 text-right">${r[I.tahun] || "—"}</td>
      <td class="px-2 py-1 text-right">${r[I.age] != null ? r[I.age] : "—"}</td>
      <td class="px-2 py-1 text-[11px] text-slate-500">${_esc(flag)}</td>
      <td class="px-2 py-1 text-[11px] text-slate-500">${_esc(r[I.mesin])}</td>
      <td class="px-2 py-1 text-[11px] text-slate-500">${_esc(r[I.mesin_type])}</td>
      <td class="px-2 py-1 text-[11px] text-slate-500">${_esc(r[I.imo])}</td>
      <td class="px-2 py-1 text-[11px] text-slate-500">${_esc(r[I.call_sign])}</td>
    </tr>`;
  }).join("");
}

function _esc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function _fleetCsvDownload() {
  const tabEl = document.getElementById("tab-fleet");
  const fv = tabEl._fleetVessels;
  if (!fv) return;
  const { rows, I } = _applyFleetFilters();
  const header = ["nama_kapal", "nama_pemilik", "sector", "vessel_class",
                  "jenis_detail_ket", "tanker_subclass",
                  "gt", "loa", "lebar", "dalam",
                  "tahun", "age", "flag",
                  "mesin", "mesin_type",
                  "imo", "call_sign"];
  const lines = [header.join(",")];
  const cidx = header.map(h => {
    const map = {nama_kapal: "nama", nama_pemilik: "owner",
                 sector: "sector", vessel_class: "vc",
                 jenis_detail_ket: "jenis",
                 tanker_subclass: "ts",
                 gt: "gt", loa: "loa", lebar: "lebar", dalam: "dalam",
                 tahun: "tahun", age: "age", flag: "flag",
                 mesin: "mesin", mesin_type: "mesin_type",
                 imo: "imo", call_sign: "call_sign"};
    return I[map[h]];
  });
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
  a.download = `fleet_filtered_${new Date().toISOString().slice(0,10)}.csv`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1500);
}

// ────────────────────────────────────────────────────────────
// PR — jang1117/vessels-style 6-chart grid for the Fleet tab.
// All charts react to the filter; bar charts on Type / Flag are
// click-to-filter (mirrors the reference site UX).
// ────────────────────────────────────────────────────────────
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
    line: { color: "#1f77b4", width: 1.5 },
    fillcolor: "rgba(31,119,180,0.25)",
    hovertemplate: "<b>%{x}</b><br>%{y:,} 척<extra></extra>",
  }], {
    margin: { t: 10, l: 40, r: 10, b: 30 },
    xaxis: { title: { text: "건조 연도", font: { size: 10 } }, tickfont: { size: 10 } },
    yaxis: { title: { text: "척수", font: { size: 10 } }, tickfont: { size: 10 } },
  }, { displayModeBar: false, responsive: true });
}

function _drawFlChartType(rows, I) {
  if (!document.getElementById("fl-ch-type")) return;
  const counts = new Map();
  for (const r of rows) {
    const j = r[I.jenis] || "(blank)";
    counts.set(j, (counts.get(j) || 0) + 1);
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 15);
  const labels = top.map(t => t[0]).reverse();
  const ys = top.map(t => t[1]).reverse();
  Plotly.newPlot("fl-ch-type", [{
    x: ys, y: labels, type: "bar", orientation: "h",
    marker: {
      color: ys,
      colorscale: "Blues", cmin: 0,
      line: { color: "#1e293b", width: 0.3 },
    },
    text: ys.map(v => v.toLocaleString()),
    textposition: "outside",
    cliponaxis: false,
    hovertemplate: "<b>%{y}</b><br>%{x:,} 척<extra>클릭 시 필터</extra>",
  }], {
    margin: { t: 5, l: 140, r: 50, b: 30 },
    xaxis: { tickfont: { size: 10 } },
    yaxis: { tickfont: { size: 10 } },
  }, { displayModeBar: false, responsive: true });
  // Click-to-filter on Vessel Type bars
  const host = document.getElementById("fl-ch-type");
  if (host && !host.dataset.clickBound) {
    host.dataset.clickBound = "1";
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
  Plotly.newPlot("fl-ch-flag", [{
    x: ys, y: labels, type: "bar", orientation: "h",
    marker: {
      color: ys,
      colorscale: "Oranges", cmin: 0,
      line: { color: "#1e293b", width: 0.3 },
    },
    text: ys.map(v => v.toLocaleString()),
    textposition: "outside",
    cliponaxis: false,
    hovertemplate: "<b>%{y}</b><br>%{x:,} 척<extra>클릭 시 필터</extra>",
  }], {
    margin: { t: 5, l: 90, r: 50, b: 30 },
    xaxis: { tickfont: { size: 10 } },
    yaxis: { tickfont: { size: 10 } },
  }, { displayModeBar: false, responsive: true });
  // Flag chart is informational only in the jang1117 mirror (no
  // separate flag filter control on the sidebar). No click handler.
}

function _drawFlChartGtHist(rows, I) {
  if (!document.getElementById("fl-ch-gt-hist")) return;
  const gts = [];
  for (const r of rows) {
    const g = r[I.gt];
    if (g && g > 0) gts.push(g);
  }
  if (!gts.length) {
    Plotly.purge("fl-ch-gt-hist");
    return;
  }
  Plotly.newPlot("fl-ch-gt-hist", [{
    x: gts,
    type: "histogram",
    nbinsx: 50,
    marker: { color: "#6c5ce7", line: { color: "#fff", width: 0.3 } },
    hovertemplate: "GT bin %{x:,.0f}<br>%{y:,} 척<extra></extra>",
  }], {
    margin: { t: 5, l: 40, r: 10, b: 35 },
    xaxis: {
      type: "log", title: { text: "GT (log)", font: { size: 10 } },
      tickfont: { size: 10 },
    },
    yaxis: { title: { text: "척수", font: { size: 10 } }, tickfont: { size: 10 } },
    bargap: 0.02,
  }, { displayModeBar: false, responsive: true });
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
  let payload, routesPayload;
  try {
    payload = await loadDerived("cargo_ports.json");
  } catch (e) {
    const host = document.getElementById("cv-map");
    if (host) host.innerHTML =
      `<div class="cv-empty">cargo_ports.json 로드 실패: ${e.message}</div>`;
    return;
  }
  if (!payload || !payload.commodities || !payload.ports) {
    return;
  }
  // Cargo OD lines reuse map_flow.json (top-30 routes, 8 categories,
  // 24M rolling — same data feeding the home-page map). Not snapshot
  // month and not per-commodity yet, but ships maritime-logistics
  // overlay immediately.
  try { routesPayload = await loadDerived("map_flow.json"); }
  catch (_) { routesPayload = { routes_top30: [], categories: [] }; }

  // Build commodity meta (key/label/color)
  const COMMS = (payload.commodities || []).map((key, i) => ({
    key,
    lbl: key,
    col: _cvColorForIndex(i, payload.commodities.length),
  }));
  const ALL_PORT_DATA = payload.ports;

  if (!_cvState) {
    const cpoKey = COMMS.find(c => c.key === "CPO") ? "CPO" : (COMMS[0] && COMMS[0].key);
    _cvState = {
      mode: "total",                                // total | domestic | international
      sub:  "both",                                 // both | unloading | loading
      multi: false,
      selComms: new Set(cpoKey ? [cpoKey] : []),
      selPort: null,
      map: null,
      circles: [],
      lines: [],
      showLines: true,
      COMMS,
      DATA: ALL_PORT_DATA,
      ROUTES: routesPayload.routes_top30 || [],
      ROUTE_CATS: routesPayload.categories || [],
    };
  } else {
    _cvState.COMMS = COMMS;
    _cvState.DATA = ALL_PORT_DATA;
    _cvState.ROUTES = routesPayload.routes_top30 || _cvState.ROUTES || [];
    _cvState.ROUTE_CATS = routesPayload.categories || _cvState.ROUTE_CATS || [];
  }

  _cvInitMap();
  _cvBuildCommodityList();
  _cvWireControls();
  _cvRebuild();
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

function _cvBuildCommodityList() {
  const list = document.getElementById("cv-comm-list");
  if (!list) return;
  list.innerHTML = "";
  for (const c of _cvState.COMMS) {
    const nat = _cvCommodityTotals(c.key);
    const tot = (nat.dU + nat.dS + nat.iU + nat.iS) / 1e6;
    const on = _cvState.selComms.has(c.key);
    const row = document.createElement("div");
    row.className = "cv-comm-row" + (on ? " selected" : "");
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

function _cvTooltip(p) {
  const selArr = [..._cvState.selComms];
  const tags = selArr.slice(0, 8).map(k => {
    const c = _cvState.COMMS.find(x => x.key === k);
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
    <div class="cv-tt-foot"><span class="cv-tt-fl">선택 화물 전체 합계</span><span class="cv-tt-fv">${_cvFmt(total)} TON</span></div>`;
}

function _cvRenderCircles(PORTS) {
  for (const c of _cvState.circles) c.remove();
  _cvState.circles = [];
  if (!_cvState.map || !PORTS.length) return;
  const maxV = Math.max(...PORTS.map(p => _cvVol(p)), 1);
  [...PORTS].sort((a, b) => _cvVol(a) - _cvVol(b)).forEach(p => {
    const v = _cvVol(p);
    if (v === 0) return;
    const r = 4 + Math.sqrt(v / maxV) * 66;
    const color = _cvColor(p);
    const circle = L.circleMarker([p.lat, p.lng], {
      radius: r, fillColor: color, color: "#fff",
      weight: 1.5, opacity: 0.9, fillOpacity: 0.55,
    });
    circle.bindTooltip(_cvTooltip(p), {
      className: "cv-tt", sticky: true, offset: [14, 0], opacity: 1,
    });
    circle.on("click", () => {
      _cvState.selPort = p.code;
      _cvRenderSidebar(PORTS);
      _cvState.map.setView([p.lat, p.lng], Math.max(_cvState.map.getZoom(), 6), { animate: true });
    });
    circle.addTo(_cvState.map);
    _cvState.circles.push(circle);
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

function _cvRouteTooltip(r) {
  const o = r.origin, d = r.destination;
  const sameOD = o === d;
  const heading = sameOD ? `🔁 ${o} (STS)` : `${o} <span style="color:#7A8FB5">→</span> ${d}`;
  const breakdown = Object.entries(r.category_ton || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([k, v]) => {
      const col = _cvCatColor(k);
      return `<div class="cv-tt-cell"><div class="cv-tt-cl" style="color:${col}">${k}</div><div class="cv-tt-cv">${_cvFmt(v)}</div></div>`;
    }).join("");
  return `<div class="cv-tt-name">${heading}</div>
    <div class="cv-tt-tags">
      <span class="cv-tt-tag" style="background:${_cvCatColor(r.category)}20;color:${_cvCatColor(r.category)};border:1px solid ${_cvCatColor(r.category)}40">${r.category}</span>
    </div>
    <div class="cv-tt-grid">${breakdown}</div>
    <hr class="cv-tt-sep">
    <div class="cv-tt-foot"><span class="cv-tt-fl">24M 합계 · 항해 ${r.calls||0} · 선박 ${r.vessels||0}</span><span class="cv-tt-fv">${_cvFmt(r.ton_24m||0)} TON</span></div>`;
}

function _cvRenderLines() {
  for (const l of _cvState.lines) l.remove();
  _cvState.lines = [];
  if (!_cvState.map || !_cvState.showLines) return;
  const routes = _cvState.ROUTES || [];
  if (!routes.length) return;
  const maxV = Math.max(...routes.map(r => r.ton_24m || 0), 1);
  // Render thickest last so it draws on top
  [...routes].sort((a, b) => (a.ton_24m || 0) - (b.ton_24m || 0)).forEach(r => {
    const v = r.ton_24m || 0;
    if (v <= 0) return;
    const w = 0.8 + Math.sqrt(v / maxV) * 5.5;
    const color = _cvCatColor(r.category);
    if (r.origin === r.destination) {
      const m = L.circleMarker([r.lat_o, r.lon_o], {
        radius: Math.max(4, w * 1.8), fillColor: color, color: color,
        weight: 1.2, opacity: 0.75, fillOpacity: 0,
        dashArray: "3,3",
      });
      m.bindTooltip(_cvRouteTooltip(r), { className: "cv-tt", sticky: true, opacity: 1 });
      m.addTo(_cvState.map);
      _cvState.lines.push(m);
      return;
    }
    const line = L.polyline([[r.lat_o, r.lon_o], [r.lat_d, r.lon_d]], {
      color, weight: w, opacity: 0.55, lineCap: "round",
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

boot().catch(e => {
  console.error(e);
  document.body.insertAdjacentHTML("afterbegin",
    `<div class="m-4">${errorState(`초기 데이터 로드 실패: ${e.message}`)}</div>`);
});
