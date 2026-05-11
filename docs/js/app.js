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
        ton_24m: r.ton,        // alias for the existing template that reads ton_24m
        vessels: 0,
        calls: r.calls || 0,
        category: null,
      }));
    routeTonField = "ton_24m";
    const mpy = homeState.cargoYearly.months_per_year || {};
    const partial = (mpy[homeState.filterPeriod] || 0) < 12;
    yearLabel = `${homeState.filterPeriod}년${partial ? ` (${mpy[homeState.filterPeriod]}mo, 부분)` : ""}`;
    notes.push(`${yearLabel} 달력연도 cut · 카테고리 분리 없음 (단색)`);
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

  // Category color map (only meaningful in 24M mode; year mode falls back to navy)
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
    // PR-35: navy default in year mode (no per-route category); legacy gray
    // when a 24M route lacks a category.
    const color = categoryColors[r.category] || (isYearMode ? "#1A3A6B" : "#6b7280");
    const pathId = `route-path-${i}`;
    const dimmed = !isYearMode && hi && r.category !== hi;
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
// PR-25: split Cargo & Fleet tab into separate Fleet and Cargo tabs.
//
// Both tabs use the existing `cargo_fleet.json` payload (class_counts,
// age_bins, treemap_categories, top_commodities). Fleet additionally
// pulls `owner_profile.json` for top-owner views; Cargo additionally
// pulls `route_facts.json` for OD lanes and `timeseries.json` for the
// sector trend.
async function renderFleet() {
  setupSourceLabels(document.getElementById("tab-fleet"));
  let cargoFleet, ownerProfile;
  try { cargoFleet = await loadDerived("cargo_fleet.json"); }
  catch (e) {
    const host = document.getElementById("fl-class-donut");
    if (host) host.innerHTML = errorState(`cargo_fleet.json 로드 실패: ${e.message}`);
    return;
  }
  try { ownerProfile = await loadDerived("owner_profile.json"); }
  catch (e) { ownerProfile = { owners: [] }; }

  drawFleetClassDonut(cargoFleet.class_counts || []);
  drawFleetAgeBars(cargoFleet.age_bins?.bins || []);
  drawFleetOwnerBars(ownerProfile.owners || []);
  drawFleetOwnerSubclass(ownerProfile.owners || []);
  fillFleetCaptions(cargoFleet, ownerProfile);
}

async function renderCargo() {
  setupSourceLabels(document.getElementById("tab-cargo"));
  let cargoFleet, routeFacts, timeseries, mapFlow, cargoYearly;
  try { cargoFleet = await loadDerived("cargo_fleet.json"); }
  catch (e) {
    const host = document.getElementById("cg-treemap");
    if (host) host.innerHTML = errorState(`cargo_fleet.json 로드 실패: ${e.message}`);
    return;
  }
  try { routeFacts = await loadDerived("route_facts.json"); }
  catch (e) { routeFacts = { routes: [] }; }
  try { timeseries = await loadDerived("timeseries.json"); }
  catch (e) { timeseries = { periods: [], series: [] }; }
  try { mapFlow = await loadDerived("map_flow.json"); }
  catch (e) { mapFlow = { ports: [], routes_top30: [], categories: [] }; }
  try { cargoYearly = await loadDerived("cargo_yearly.json"); }
  catch (e) { cargoYearly = null; }

  // PR-29: stash the yearly payload on the tab element so the click handler
  // can reach it without re-fetching.
  const tabEl = document.getElementById("tab-cargo");
  if (tabEl && cargoYearly) tabEl._cargoYearly = cargoYearly;

  // Pick the default year: most-recent full (12-month) year if any, else
  // most-recent year present in the payload, else fall back to legacy.
  const defaultYear = _pickDefaultCargoYear(cargoYearly);

  // PR-31: year-aware path renders OD map + routes + STS too. We stash
  // mapFlow + routeFacts on the tab DOM node so pill clicks re-render with
  // the same context without re-fetching.
  if (tabEl) {
    tabEl._cargoMapFlow = mapFlow;
    tabEl._cargoRouteFacts = routeFacts;
  }
  drawCargoYearly(timeseries);
  drawCargoTimeseries(timeseries);
  fillCargoCaptions(cargoFleet, routeFacts, timeseries, mapFlow);

  // Single render call covers treemap + commodities + map + routes + STS
  renderCargoYearlyView(cargoYearly, cargoFleet, defaultYear,
                         { mapFlow, routeFacts });
  buildCargoYearPills(cargoYearly, defaultYear);

  // "Hide self-loop" toggle — when checked, re-render the routes bar from
  // the currently-active dataset (year-cut top_routes or legacy 24M).
  const hideSelf = document.getElementById("cg-routes-hide-self");
  if (hideSelf && !hideSelf.dataset.wired) {
    hideSelf.dataset.wired = "1";
    hideSelf.addEventListener("change", () => {
      const activeYear = (document
        .querySelector("#cg-year-pills button[aria-selected='true']")
        || {}).dataset?.year;
      const cy = tabEl?._cargoYearly;
      const yearSlice = (cy && activeYear && cy.by_year?.[activeYear]) || null;
      if (yearSlice && Array.isArray(yearSlice.top_routes)) {
        const merged = (yearSlice.top_routes || []).concat(
          (yearSlice.top_sts || []).map(s => ({
            origin: s.port, destination: s.port,
            ton: s.ton, calls: s.calls, is_self_loop: true,
          }))
        );
        merged.sort((a, b) => (b.ton || 0) - (a.ton || 0));
        drawCargoRoutes(merged, { xTitle: `ton (${activeYear}년)` });
      } else {
        drawCargoRoutes(routeFacts.routes || [], { xTitle: "ton (24M)" });
      }
    });
  }
}

function _pickDefaultCargoYear(cargoYearly) {
  if (!cargoYearly || !cargoYearly.years || !cargoYearly.years.length) return null;
  const mpy = cargoYearly.months_per_year || {};
  const fullYears = cargoYearly.years.filter(y => mpy[y] === 12);
  if (fullYears.length) return fullYears[fullYears.length - 1];   // most-recent full year
  return cargoYearly.years[cargoYearly.years.length - 1];          // else latest available
}

function buildCargoYearPills(cargoYearly, activeYear) {
  const host = document.getElementById("cg-year-pills");
  const banner = document.getElementById("cg-year-banner");
  if (!host) return;
  if (!cargoYearly || !cargoYearly.years || !cargoYearly.years.length) {
    host.innerHTML = `<button class="px-2 py-1 bg-slate-100 text-slate-400 text-xs" disabled>데이터 없음</button>`;
    if (banner) banner.textContent = "";
    return;
  }
  const mpy = cargoYearly.months_per_year || {};
  host.innerHTML = cargoYearly.years.map(y => {
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
      const tabEl = document.getElementById("tab-cargo");
      const cy = (tabEl && tabEl._cargoYearly) || cargoYearly;
      renderCargoYearlyView(cy, null, y, {
        mapFlow: tabEl?._cargoMapFlow,
        routeFacts: tabEl?._cargoRouteFacts,
      });
      buildCargoYearPills(cy, y);
    });
  });

  if (banner) {
    const isPartial = (mpy[activeYear] || 0) < 12;
    banner.textContent = isPartial
      ? `⚠️ ${activeYear}년은 부분 연도 (${mpy[activeYear]}개월) — 다른 연도와 단순 비교 시 주의.`
      : `${activeYear}년 (12개월 전체).`;
  }
}

function renderCargoYearlyView(cargoYearly, fallbackCargoFleet, year, ctx) {
  // ctx = { mapFlow, routeFacts } — passed through from renderCargo so the
  // map/routes/STS charts can swap to year-cut data when a year is picked.
  ctx = ctx || {};

  let treemap = [];
  let commodities = [];
  let yearLabel = "24M";
  let yearSlice = null;
  if (cargoYearly && year && cargoYearly.by_year && cargoYearly.by_year[year]) {
    yearSlice = cargoYearly.by_year[year];
    treemap = yearSlice.treemap_categories || [];
    commodities = yearSlice.top_commodities || [];
    const mpy = (cargoYearly.months_per_year || {})[year] || 0;
    yearLabel = `${year}년${mpy < 12 ? ` (${mpy}mo)` : ""}`;
  } else if (fallbackCargoFleet) {
    treemap = fallbackCargoFleet.treemap_categories || [];
    commodities = fallbackCargoFleet.top_commodities || [];
  }

  // ---- Card title swaps ----
  const tt = document.getElementById("cg-treemap-title");
  if (tt) tt.textContent = `화물 카테고리 트리맵 — ${yearLabel} (Top ${treemap.length})`;
  const ct = document.getElementById("cg-commodity-title");
  if (ct) ct.textContent = `화물 품목 Top 10 — ${yearLabel}`;
  const mt = document.getElementById("cg-od-map-title");
  if (mt) mt.textContent = `🗺️ OD 흐름 지도 — ${yearLabel} (Top 30 항로)`;
  const rt = document.getElementById("cg-routes-title");
  if (rt) rt.textContent = `Top 항로 (OD) — ${yearLabel}`;
  const st = document.getElementById("cg-sts-title");
  if (st) st.textContent = `Top STS / 자체 환적 (origin = destination) — ${yearLabel}`;

  // ---- Treemap + commodities ----
  drawCargoTreemap(treemap);
  drawCargoCommodityBars(commodities);

  // ---- OD map + STS + routes (year-cut when available) ----
  if (yearSlice && Array.isArray(yearSlice.top_routes)) {
    drawCargoODMapYear(yearSlice.top_routes, ctx.mapFlow?.ports || [], yearLabel);
    drawCargoRoutes(yearSlice.top_routes, { xTitle: `ton (${yearLabel})` });
    // Year-cut routes already exclude STS; but provide an STS-aware
    // overlay with top_sts so the routes bar can show both when the
    // "hide self-loop" toggle is off. Use top_routes augmented with STS.
    const merged = (yearSlice.top_routes || []).concat(
      (yearSlice.top_sts || []).map(s => ({
        origin: s.port, destination: s.port,
        ton: s.ton, calls: s.calls, is_self_loop: true,
      }))
    );
    // Re-sort merged so STS hubs interleave by ton
    merged.sort((a, b) => (b.ton || 0) - (a.ton || 0));
    // The hide-self toggle in drawCargoRoutes uses `isSelf` after
    // normalization; pass the merged list.
    drawCargoRoutes(merged, { xTitle: `ton (${yearLabel})` });
    drawCargoSTS(yearSlice.top_sts || [],
                  { yearCut: true, xTitle: `ton (${yearLabel}, self-loop)` });
  } else {
    // Legacy 24M view via map_flow + route_facts
    if (ctx.mapFlow) drawCargoODMap(ctx.mapFlow);
    if (ctx.routeFacts) {
      drawCargoRoutes(ctx.routeFacts.routes || [], { xTitle: "ton (24M)" });
      drawCargoSTS(ctx.routeFacts.routes || [],
                    { yearCut: false, xTitle: "ton (24M, self-loop)" });
    }
  }

  // ---- Captions ----
  const cap1 = document.getElementById("cg-treemap-caption");
  if (cap1) {
    const cats = treemap.slice().sort((a, b) => b.ton_total - a.ton_total);
    const total = cats.reduce((s, r) => s + (r.ton_total || 0), 0);
    const top3 = cats.slice(0, 3).reduce((s, r) => s + r.ton_total, 0);
    cap1.textContent = total > 0
      ? `${yearLabel} — 상위 3개 카테고리(${cats.slice(0, 3).map(c => c.category).join(" · ")})가 전체 ${cats.length}개의 ${(top3 / total * 100).toFixed(1)}%.`
      : "데이터 없음";
  }
  const cap2 = document.getElementById("cg-commodity-caption");
  if (cap2 && commodities[0]) {
    const totC = commodities.reduce((s, r) => s + (r.ton_total || 0), 0);
    cap2.textContent = totC > 0
      ? `${yearLabel} — ${commodities[0].name} 단일 품목이 Top 10 누적의 ${(commodities[0].ton_total / totC * 100).toFixed(1)}%.`
      : "데이터 없음";
  }

  // Routes + STS captions
  const capR = document.getElementById("cg-routes-caption");
  if (capR) {
    if (yearSlice && Array.isArray(yearSlice.top_routes) && yearSlice.top_routes[0]) {
      const r = yearSlice.top_routes[0];
      capR.textContent = `${yearLabel} 최대 항로: ${r.origin} → ${r.destination} (${fmtTon(r.ton)}, ${(r.calls || 0).toLocaleString()}회).`;
    }
    // else: leave the legacy 24M caption populated by fillCargoCaptions
  }
  const capS = document.getElementById("cg-sts-caption");
  if (capS) {
    if (yearSlice && Array.isArray(yearSlice.top_sts) && yearSlice.top_sts[0]) {
      const s = yearSlice.top_sts[0];
      const total = (yearSlice.top_sts || []).reduce((sum, r) => sum + (r.ton || 0), 0);
      capS.textContent = `${yearLabel} — STS Top1: ${s.port} ${fmtTon(s.ton)} · 상위 15개 합계 ${fmtTon(total)}.`;
    }
  }

  // Map caption
  const capM = document.getElementById("cg-od-map-caption");
  if (capM) {
    if (yearSlice && Array.isArray(yearSlice.top_routes)) {
      const mappable = yearSlice.top_routes.filter(r => r.mappable !== false
        && r.lat_o != null && r.lon_o != null).length;
      capM.textContent = `${yearLabel} — Top ${yearSlice.top_routes.length} 항로 중 ${mappable}개 좌표 매핑.`;
    }
  }
}

function fillFleetCaptions(cargoFleet, ownerProfile) {
  // Class donut — share of largest class
  const classes = (cargoFleet.class_counts || []).slice().sort((a, b) => b.count - a.count);
  const totCls = classes.reduce((s, r) => s + (r.count || 0), 0);
  const cap1 = document.getElementById("fl-class-caption");
  if (cap1 && classes[0]) {
    cap1.textContent = totCls > 0
      ? `${classes[0]["class"]}이(가) 등록 화물선 ${fmtCount(totCls)}척 중 ${(classes[0].count / totCls * 100).toFixed(1)}%로 가장 큰 비중입니다.`
      : "데이터 없음";
  }

  // Age bars — % of fleet that is 25+
  const bins = (cargoFleet.age_bins?.bins || []);
  const totAge = bins.reduce((s, b) => s + (b.count || 0), 0);
  const olderCount = bins.filter(b => b.older).reduce((s, b) => s + (b.count || 0), 0);
  const cap2 = document.getElementById("fl-age-caption");
  if (cap2) {
    cap2.textContent = totAge > 0
      ? `등록 화물선의 ${(olderCount / totAge * 100).toFixed(1)}%가 25년 이상 (${fmtCount(olderCount)}척 / ${fmtCount(totAge)}척).`
      : "데이터 없음";
  }

  // Owner bars — Tbk count + Top-3 share of all listed owner tankers
  const owners = (ownerProfile.owners || []).slice();
  const totOwners = owners.length;
  const tbkCount = owners.filter(o => o.ticker || /TBK\b/i.test(o.owner || "")).length;
  const top3 = owners.slice().sort((a, b) => b.tankers - a.tankers).slice(0, 3);
  const cap3 = document.getElementById("fl-owner-caption");
  if (cap3 && top3[0]) {
    cap3.textContent = `상위 ${totOwners}개 선주 중 IDX 상장(Tbk)은 ${tbkCount}개. Top-1 = ${top3[0].owner} (${top3[0].tankers}척).`;
  }
}

function fillCargoCaptions(cargoFleet, routeFacts, timeseries, mapFlow) {
  // 0) OD map — top route share + intl/domestic totals
  const capMap = document.getElementById("cg-od-map-caption");
  if (capMap && mapFlow) {
    const routes = (mapFlow.routes_top30 || []);
    const totals = mapFlow.totals || {};
    const dom = totals.domestic_ton || 0;
    const intl = totals.intl_ton || 0;
    const unk = totals.unknown_ton || 0;
    const all = dom + intl + unk;
    const top1 = routes[0];
    if (top1) {
      capMap.textContent = `최대 항로: ${top1.origin} → ${top1.destination} (${fmtTon(top1.ton_24m)}, ${top1.category || ""}). `
        + `전체 24M: 국내 ${fmtTon(dom)} · 국제 ${fmtTon(intl)} (${all > 0 ? (intl / all * 100).toFixed(1) : 0}%).`;
    }
  }


  // 1) Treemap — top-3 category share
  const cats = (cargoFleet.treemap_categories || []).slice().sort((a, b) => b.ton_total - a.ton_total);
  const totCats = cats.reduce((s, r) => s + (r.ton_total || 0), 0);
  const top3 = cats.slice(0, 3).reduce((s, r) => s + r.ton_total, 0);
  const cap1 = document.getElementById("cg-treemap-caption");
  if (cap1) {
    cap1.textContent = totCats > 0
      ? `상위 3개 카테고리(${cats.slice(0, 3).map(c => c.category).join(" · ")})가 전체 ${cats.length}개의 ${(top3 / totCats * 100).toFixed(1)}%를 차지합니다.`
      : "데이터 없음";
  }

  // 2) Commodity — top single commodity share of top-10 sum
  const coms = (cargoFleet.top_commodities || []).slice();
  const totC = coms.reduce((s, r) => s + (r.ton_total || 0), 0);
  const cap2 = document.getElementById("cg-commodity-caption");
  if (cap2 && coms[0]) {
    cap2.textContent = totC > 0
      ? `${coms[0].name} 단일 품목이 Top 10 누적 ton의 ${(coms[0].ton_total / totC * 100).toFixed(1)}%를 차지합니다.`
      : "데이터 없음";
  }

  // 3) Timeseries — most-grown sector (last 6 vs prior 6, positional indices)
  const series = (timeseries.series || []);
  const periods = (timeseries.periods || []);
  const cap3 = document.getElementById("cg-timeseries-caption");
  if (cap3 && series.length && periods.length >= 12) {
    const N = periods.length;
    let best = null;
    for (const s of series) {
      let sumR = 0, sumP = 0;
      for (let i = N - 6; i < N; i++) sumR += _seriesTon(s, i);
      for (let i = N - 12; i < N - 6; i++) sumP += _seriesTon(s, i);
      if (sumP <= 0) continue;
      const growth = (sumR - sumP) / sumP * 100;
      if (!best || growth > best.growth) best = { name: s.sector, growth };
    }
    if (best) {
      cap3.textContent = `최근 6개월 vs 이전 6개월 — 최대 성장 sector: ${best.name} (${best.growth >= 0 ? "+" : ""}${best.growth.toFixed(1)}%).`;
    }
  }

  // 3b) Yearly chart — partial-year flag + biggest year-over-year jump
  const capY = document.getElementById("cg-yearly-caption");
  if (capY && series.length && periods.length) {
    const monthsByYear = {};
    for (const p of periods) monthsByYear[p.slice(0, 4)] = (monthsByYear[p.slice(0, 4)] || 0) + 1;
    const ys = Object.keys(monthsByYear).sort();
    const cargo = series.find(s => s.sector === "CARGO");
    if (cargo && ys.length >= 2) {
      const byYear = {};
      for (let i = 0; i < periods.length; i++) {
        const y = periods[i].slice(0, 4);
        byYear[y] = (byYear[y] || 0) + _seriesTon(cargo, i);
      }
      // pick the two most-complete adjacent years for the YoY note
      const fullYears = ys.filter(y => monthsByYear[y] === 12);
      const refYear = fullYears[0] || ys[ys.length - 2] || ys[0];
      const prevYear = ys[ys.indexOf(refYear) - 1];
      const noteParts = [];
      ys.forEach(y => {
        const mark = monthsByYear[y] === 12 ? "(full)" : `(${monthsByYear[y]}mo, 부분)`;
        noteParts.push(`${y} ${mark}: ${fmtTon(byYear[y] || 0)}`);
      });
      capY.textContent = `CARGO 부문 연도별 합계 — ${noteParts.join(" · ")}.`;
    }
  }

  // 4) Routes caption — share of top-1 OD vs all routes
  const routes = (routeFacts.routes || []);
  const cap4 = document.getElementById("cg-routes-caption");
  if (cap4 && routes.length) {
    const nonSelf = routes.filter(r => !r.is_self_loop);
    const totalTon = nonSelf.reduce((s, r) => s + (r.ton_24m || 0), 0);
    const top1 = nonSelf[0];
    if (top1 && totalTon > 0) {
      cap4.textContent = `최대 항로: ${top1.origin} → ${top1.destination} — Top ${nonSelf.length}개 self-loop 제외 항로 중 ${(top1.ton_24m / totalTon * 100).toFixed(1)}% 점유.`;
    }
  }

  // 5) STS caption
  const sts = routes.filter(r => r.is_self_loop);
  const cap5 = document.getElementById("cg-sts-caption");
  if (cap5) {
    const stsTotal = sts.reduce((s, r) => s + (r.ton_24m || 0), 0);
    cap5.textContent = sts.length
      ? `자체 환적 (STS) 허브 ${sts.length}개 — 24개월 합계 ${fmtTon(stsTotal)}.`
      : "데이터 없음";
  }
}

// Year-cut OD map: renders cargo_yearly.by_year[Y].top_routes as great-circle
// lines + port bubbles. Falls back gracefully when only a subset of routes
// have mappable coordinates (build-time port-coord lookup limitation).
function drawCargoODMapYear(yearRoutes, mapFlowPorts, yearLabel) {
  const routes = (yearRoutes || []).filter(r => r.mappable !== false
    && r.lat_o != null && r.lon_o != null && r.lat_d != null && r.lon_d != null);
  if (!routes.length) {
    // Show a placeholder explaining why the map is empty for the year
    const host = document.getElementById("cg-od-map");
    if (host) {
      host.innerHTML =
        `<div class="text-sm text-slate-500 p-4">${yearLabel || ""} — 좌표 매핑 가능한 항로가 없습니다. ` +
        `(원본 데이터는 Top 항로 표에서 확인 가능)</div>`;
    }
    return;
  }

  // Build port aggregate from routes endpoints
  const portAgg = new Map();
  let maxTon = 0;
  for (const r of routes) {
    const o = r.origin, d = r.destination;
    if (!portAgg.has(o)) portAgg.set(o, { name: o, lat: r.lat_o, lon: r.lon_o, ton: 0 });
    if (!portAgg.has(d)) portAgg.set(d, { name: d, lat: r.lat_d, lon: r.lon_d, ton: 0 });
    portAgg.get(o).ton += r.ton;
    portAgg.get(d).ton += r.ton;
    if (r.ton > maxTon) maxTon = r.ton;
  }
  const ports = [...portAgg.values()];
  const portMaxTon = Math.max(...ports.map(p => p.ton || 0), 1);

  const lineTraces = routes.map(r => {
    const width = 1.0 + 7.0 * Math.sqrt(r.ton / Math.max(maxTon, 1));
    return {
      type: "scattergeo",
      lon: [r.lon_o, r.lon_d],
      lat: [r.lat_o, r.lat_d],
      mode: "lines",
      line: { width, color: "#1A3A6B" },
      opacity: 0.72,
      hoverinfo: "text",
      text: `<b>${r.origin} → ${r.destination}</b><br>${fmtTon(r.ton)}t · ${(r.calls || 0).toLocaleString()}회`,
      name: yearLabel || "year",
      showlegend: false,
    };
  });
  const portTrace = {
    type: "scattergeo",
    lon: ports.map(p => p.lon),
    lat: ports.map(p => p.lat),
    mode: "markers",
    marker: {
      size: ports.map(p => Math.sqrt((p.ton || 0) / portMaxTon) * 26 + 4),
      color: "#0f172a",
      opacity: 0.85,
      line: { width: 0.5, color: "#ffffff" },
    },
    text: ports.map(p => `<b>${p.name}</b><br>${fmtTon(p.ton)}t`),
    hoverinfo: "text",
    name: `항구 (${yearLabel} ton)`,
    showlegend: false,
  };

  Plotly.newPlot("cg-od-map", [...lineTraces, portTrace], {
    margin: { t: 5, b: 5, l: 5, r: 5 },
    geo: {
      scope: "asia", projection: { type: "natural earth" },
      showcountries: true, showcoastlines: true, showland: true,
      showocean: true, oceancolor: "#f1f5f9",
      landcolor: "#fefefe", countrycolor: "#cbd5e1",
      coastlinecolor: "#94a3b8",
      lataxis: { range: [-12, 8] },
      lonaxis: { range: [94, 142] },
    },
  }, { displayModeBar: false, responsive: true });
}

function drawCargoODMap(payload) {
  const routes = payload.routes_top30 || [];
  const ports = payload.ports || [];
  const categories = payload.categories || [];
  if (!routes.length || !ports.length) {
    const host = document.getElementById("cg-od-map");
    if (host) host.innerHTML = `<div class="text-sm text-slate-500 p-4">지도 데이터 없음.</div>`;
    return;
  }

  // Build a name -> color map from the provided palette; fallback grey.
  const catColor = {};
  for (const c of categories) catColor[c.name] = c.color || "#64748b";

  // Group routes by category so legend toggling works (one trace per category).
  const byCat = {};
  let maxTon = 0;
  for (const r of routes) {
    const cat = r.category || "Other";
    (byCat[cat] = byCat[cat] || []).push(r);
    if (r.ton_24m > maxTon) maxTon = r.ton_24m;
  }

  const traces = [];

  // One legend entry per category, with all that category's OD pairs drawn as
  // separate `lines` sub-traces (Plotly can't vary line width within one trace).
  for (const cat of Object.keys(byCat)) {
    const color = catColor[cat] || "#64748b";
    let first = true;
    for (const r of byCat[cat]) {
      const width = 1.0 + 7.0 * Math.sqrt(r.ton_24m / Math.max(maxTon, 1));
      traces.push({
        type: "scattergeo",
        lon: [r.lon_o, r.lon_d],
        lat: [r.lat_o, r.lat_d],
        mode: "lines",
        line: { width: width, color: color },
        opacity: 0.75,
        hoverinfo: "text",
        text: `<b>${cat}</b><br>${r.origin} → ${r.destination}<br>`
              + `${fmtTon(r.ton_24m)}t · ${r.vessels || 0}척 · ${r.calls || 0}회`,
        name: cat,
        legendgroup: cat,
        showlegend: first,
      });
      first = false;
    }
  }

  // Port bubbles on top — size by ton, label on hover.
  const portMaxTon = Math.max(...ports.map(p => p.ton_24m || 0), 1);
  traces.push({
    type: "scattergeo",
    lon: ports.map(p => p.lon),
    lat: ports.map(p => p.lat),
    mode: "markers",
    marker: {
      size: ports.map(p => Math.sqrt((p.ton_24m || 0) / portMaxTon) * 26 + 4),
      color: "#0f172a",
      opacity: 0.85,
      line: { width: 0.5, color: "#ffffff" },
    },
    text: ports.map(p => `<b>${p.name}</b><br>${fmtTon(p.ton_24m || 0)}t`),
    hoverinfo: "text",
    name: "항구 (24M ton)",
    showlegend: true,
  });

  Plotly.newPlot("cg-od-map", traces, {
    margin: { t: 5, b: 5, l: 5, r: 5 },
    legend: {
      orientation: "h", y: -0.05, x: 0,
      bgcolor: "rgba(255,255,255,0.9)",
      bordercolor: "#e2e8f0", borderwidth: 1,
      font: { size: 11 },
    },
    geo: {
      scope: "asia",
      projection: { type: "natural earth" },
      showcountries: true, showcoastlines: true, showland: true,
      showocean: true,
      oceancolor: "#f1f5f9",
      landcolor: "#fefefe",
      countrycolor: "#cbd5e1",
      coastlinecolor: "#94a3b8",
      lataxis: { range: [-12, 8] },
      lonaxis: { range: [94, 142] },
    },
  }, { displayModeBar: false, responsive: true });
}

function drawCargoTreemap(rows) {
  if (!rows.length) return;
  const labels = rows.map(r => r.category);
  const values = rows.map(r => r.ton_total);
  const palette = ["#1A3A6B", "#0284c7", "#059669", "#d97706", "#7c3aed",
                   "#92400e", "#65a30d", "#475569", "#dc2626", "#0891b2",
                   "#9333ea", "#be185d", "#84cc16", "#ea580c", "#0ea5e9"];
  Plotly.newPlot("cg-treemap", [{
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
  const list = rows.slice().reverse();
  Plotly.newPlot("cg-commodity-bar", [{
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

// ton_by_period is a list aligned positionally with `periods` (NOT a dict).
function _seriesTon(s, periodIndex) {
  const arr = s.ton_by_period;
  if (!arr) return 0;
  if (Array.isArray(arr)) return arr[periodIndex] || 0;
  // legacy: object keyed by period string — left for forward-compat
  return 0;
}

function drawCargoTimeseries(payload) {
  const periods = payload.periods || [];
  const series = payload.series || [];
  if (!periods.length || !series.length) return;
  const traces = series.map(s => ({
    x: periods,
    y: periods.map((_p, i) => _seriesTon(s, i)),
    name: s.sector,
    type: "scatter",
    mode: "lines",
    stackgroup: "one",
    line: { color: s.color || "#94a3b8" },
    hovertemplate: `<b>${s.sector}</b><br>%{x}: %{y:,.0f}t<extra></extra>`,
  }));
  Plotly.newPlot("cg-timeseries", traces, {
    margin: { t: 20, l: 60, r: 20, b: 50 },
    xaxis: { title: "월" },
    yaxis: { title: "톤" },
    legend: { orientation: "h", y: -0.2, font: { size: 10 } },
  }, { displayModeBar: false, responsive: true });
}

// Year-based sector comparison — replaces rolling 12M/24M framing with
// calendar-year cuts (2024 partial / 2025 full / 2026 partial in this
// snapshot). Partial-year bars get a hatched marker pattern + an
// annotation to flag that they're not 12-month totals.
function drawCargoYearly(payload) {
  const periods = payload.periods || [];
  const series = payload.series || [];
  if (!periods.length || !series.length) return;

  // Count months per year so partial-year flag is data-driven.
  const monthsByYear = {};
  for (const p of periods) {
    const y = p.slice(0, 4);
    monthsByYear[y] = (monthsByYear[y] || 0) + 1;
  }
  const years = Object.keys(monthsByYear).sort();

  // Sum per (sector, year).
  const cargoSectors = ["CARGO"];   // primary focus per the user's brief
  const byYear = {};                 // sector -> [yearTon, yearTon, ...]
  for (const s of series) {
    const sums = years.map(_ => 0);
    for (let i = 0; i < periods.length; i++) {
      const yi = years.indexOf(periods[i].slice(0, 4));
      sums[yi] += _seriesTon(s, i);
    }
    byYear[s.sector] = { color: s.color || "#94a3b8", sums };
  }

  // Build one bar trace per sector, x = years.
  const sectorsSorted = Object.keys(byYear).sort((a, b) =>
    byYear[b].sums.reduce((x, y) => x + y, 0)
    - byYear[a].sums.reduce((x, y) => x + y, 0));

  const traces = sectorsSorted.map(sec => {
    const isPartial = years.map(y => monthsByYear[y] < 12);
    return {
      x: years.map(y => `${y}년${monthsByYear[y] < 12 ? ` (${monthsByYear[y]}mo)` : ""}`),
      y: byYear[sec].sums,
      name: sec,
      type: "bar",
      marker: {
        color: byYear[sec].color,
        pattern: { shape: isPartial.map(p => p ? "/" : ""), bgcolor: byYear[sec].color },
        line: { color: "#1e293b", width: 0.4 },
      },
      text: byYear[sec].sums.map(v => fmtTon(v)),
      textposition: "outside",
      cliponaxis: false,
      hovertemplate: `<b>${sec} · %{x}</b><br>%{y:,.0f}t<extra></extra>`,
    };
  });

  Plotly.newPlot("cg-yearly", traces, {
    margin: { t: 30, l: 70, r: 20, b: 60 },
    barmode: "group",
    xaxis: { title: "연도" },
    yaxis: { title: "톤 (합계)" },
    legend: { orientation: "h", y: -0.18, font: { size: 10 } },
    annotations: [{
      x: 0.5, y: 1.12, xref: "paper", yref: "paper",
      text: "<span style='color:#475569'>※ 빗금 = 부분 연도 (12개월 미만)</span>",
      showarrow: false, font: { size: 11 },
    }],
  }, { displayModeBar: false, responsive: true });
}

// drawCargoRoutes accepts EITHER legacy route_facts rows (with ton_24m,
// calls_24m, vessels_seen, buckets, is_self_loop) OR year-cut top_routes
// rows from cargo_yearly (origin, destination, ton, calls). Normalises on
// the fly so a single chart serves both modes.
function drawCargoRoutes(rows, opts = {}) {
  if (!rows.length) {
    const host = document.getElementById("cg-routes-bar");
    if (host) host.innerHTML = `<div class="text-sm text-slate-500 p-4">표시할 항로가 없습니다.</div>`;
    return;
  }

  // Normalize to a common shape
  const normRows = rows.map(r => {
    const ton = r.ton_24m != null ? r.ton_24m : (r.ton || 0);
    const calls = r.calls_24m != null ? r.calls_24m : (r.calls || 0);
    const vessels = r.vessels_seen != null ? r.vessels_seen : (r.vessels || 0);
    const buckets = r.buckets || [];
    const isSelf = r.is_self_loop != null
      ? r.is_self_loop
      : (r.origin && r.destination && r.origin === r.destination);
    return {
      origin: r.origin, destination: r.destination,
      ton, calls, vessels, buckets, isSelf,
    };
  });

  const hideSelf = document.getElementById("cg-routes-hide-self");
  const filtered = (hideSelf && hideSelf.checked)
    ? normRows.filter(r => !r.isSelf)
    : normRows;
  const top = filtered.slice(0, 25).reverse();
  if (!top.length) {
    const host = document.getElementById("cg-routes-bar");
    if (host) host.innerHTML = `<div class="text-sm text-slate-500 p-4">표시할 항로가 없습니다.</div>`;
    return;
  }
  const xTitle = opts.xTitle || "ton";
  Plotly.newPlot("cg-routes-bar", [{
    x: top.map(r => r.ton),
    y: top.map(r => `${r.origin} → ${r.destination}${r.isSelf ? " (STS)" : ""}`),
    type: "bar",
    orientation: "h",
    marker: {
      color: top.map(r => r.isSelf ? "#f59e0b" : "#1A3A6B"),
      line: { color: "#1e293b", width: 0.5 },
    },
    text: top.map(r => fmtTon(r.ton)),
    textposition: "outside",
    cliponaxis: false,
    customdata: top.map(r => [r.calls, r.vessels, (r.buckets || []).slice(0, 3).join(", ")]),
    hovertemplate: "<b>%{y}</b><br>%{x:,.0f} tons<br>항해 %{customdata[0]:,} · 선박 %{customdata[1]:,}<br>주요 화물: %{customdata[2]}<extra></extra>",
  }], {
    margin: { t: 10, l: 220, r: 70, b: 40 },
    xaxis: { title: xTitle },
  }, { displayModeBar: false, responsive: true });
}

// Accepts legacy 24M route_facts rows OR year-cut top_sts items
// (port, ton, calls). When `opts.yearCut === true`, the input is the
// already-filtered top_sts list (no need to filter by is_self_loop).
function drawCargoSTS(rows, opts = {}) {
  let sts;
  if (opts.yearCut) {
    sts = (rows || []).slice(0, 15).reverse().map(r => ({
      port: r.port,
      ton: r.ton,
      calls: r.calls || 0,
      vessels: 0,
      buckets: [],
    }));
  } else {
    sts = (rows || [])
      .filter(r => r.is_self_loop)
      .slice(0, 15)
      .reverse()
      .map(r => ({
        port: r.origin,
        ton: r.ton_24m,
        calls: r.calls_24m || 0,
        vessels: r.vessels_seen || 0,
        buckets: r.buckets || [],
      }));
  }
  if (!sts.length) {
    const host = document.getElementById("cg-sts-bar");
    if (host) host.innerHTML = `<div class="text-sm text-slate-500 p-4">STS 데이터 없음.</div>`;
    return;
  }
  const xTitle = opts.xTitle || "ton (self-loop)";
  Plotly.newPlot("cg-sts-bar", [{
    x: sts.map(r => r.ton),
    y: sts.map(r => r.port),
    type: "bar",
    orientation: "h",
    marker: { color: "#f59e0b", line: { color: "#1e293b", width: 0.5 } },
    text: sts.map(r => fmtTon(r.ton)),
    textposition: "outside",
    cliponaxis: false,
    customdata: sts.map(r => [r.calls, r.vessels, (r.buckets || []).slice(0, 3).join(", ")]),
    hovertemplate: "<b>%{y}</b><br>%{x:,.0f} tons<br>항해 %{customdata[0]:,} · 선박 %{customdata[1]:,}<br>주요 화물: %{customdata[2]}<extra></extra>",
  }], {
    margin: { t: 10, l: 150, r: 70, b: 40 },
    xaxis: { title: xTitle },
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

function drawFleetOwnerBars(owners) {
  if (!owners.length) return;
  const top = owners.slice().sort((a, b) => b.tankers - a.tankers).slice(0, 25);
  // Tbk star marker
  const labels = top.map(o => {
    const isTbk = !!o.ticker || /TBK\b/i.test(o.owner || "");
    return `${isTbk ? "★ " : ""}${o.owner}`;
  }).reverse();
  const counts = top.map(o => o.tankers).reverse();
  const gts = top.map(o => o.sum_gt).reverse();
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
    customdata: gts,
    hovertemplate: "<b>%{y}</b><br>%{x} 척<br>총 GT %{customdata:,.0f}<extra></extra>",
  }], {
    margin: { t: 10, l: 240, r: 70, b: 40 },
    xaxis: { title: "Tanker 척수" },
  }, { displayModeBar: false, responsive: true });
}

function drawFleetOwnerSubclass(owners) {
  if (!owners.length) return;
  // Top 5 owners + subclass mix
  const top5 = owners.slice().sort((a, b) => b.tankers - a.tankers).slice(0, 5);
  // Collect all subclass keys
  const subclassSet = new Set();
  top5.forEach(o => {
    const mix = o.subclass_mix || {};
    Object.keys(mix).forEach(k => subclassSet.add(k));
  });
  const subclasses = Array.from(subclassSet);
  const palette = {
    "Crude Oil": "#0f172a", "Product": "#1e40af", "Chemical": "#7c3aed",
    "LPG": "#f59e0b", "LNG": "#0891b2",
    "FAME / Vegetable Oil": "#16a34a", "Water": "#0ea5e9",
    "UNKNOWN": "#9ca3af",
  };
  const traces = subclasses.map(sub => ({
    x: top5.map(o => o.owner),
    y: top5.map(o => (o.subclass_mix || {})[sub] || 0),
    name: sub,
    type: "bar",
    marker: { color: palette[sub] || "#94a3b8" },
    hovertemplate: `<b>%{x}</b><br>${sub}: %{y} 척<extra></extra>`,
  }));
  Plotly.newPlot("fl-owner-subclass", traces, {
    barmode: "stack",
    margin: { t: 10, l: 60, r: 20, b: 100 },
    xaxis: { tickangle: -25 },
    yaxis: { title: "척수" },
    legend: { orientation: "h", y: -0.4, font: { size: 10 } },
  }, { displayModeBar: false, responsive: true });
}

boot().catch(e => {
  console.error(e);
  document.body.insertAdjacentHTML("afterbegin",
    `<div class="m-4">${errorState(`초기 데이터 로드 실패: ${e.message}`)}</div>`);
});
