#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IDX XBRL 기반 인도네시아 해운사 재무 수집기.

Bursa Efek Indonesia(IDX)가 상장사별로 공시하는 감사받은(audit) 연차
재무제표 XBRL 인스턴스(``instance.zip``)를 받아 핵심 재무 개념을 추출하고,
보고 통화가 제각각(USD/IDR)인 점을 USD 백만 단위로 환산해 비교 가능한
형태로 정규화한다.

흐름:
  1. GetFinancialReport API 로 (ticker, year, audit) 첨부파일 목록 조회
  2. 그중 ``instance.zip`` 을 내려받아 ``instance.xbrl`` 파싱
  3. idx-cor / idx-dei 개념을 정규식으로 추출 (당해연도 컨텍스트만)
  4. 보고 통화·반올림 단위 인식 → native 값 + USD 환산값 동시 산출
  5. 파생 비율(순이익률·ROE·ROA·DER·유동비율 등) 계산
  6. data/idx_financials.json (정본) + docs/data/companies_financials.json (배포본)

XBRL 인스턴스는 연 1회 갱신되므로 ``data/idx_xbrl_cache/`` 에 zip 을 캐시하여
재실행 시 네트워크를 건너뛴다. ``--refresh`` 로 캐시 무시 가능.

사용:
  python scripts/fetch_idx_financials.py            # 캐시 활용 수집
  python scripts/fetch_idx_financials.py --refresh  # 전체 재다운로드
  python scripts/fetch_idx_financials.py --only SMDR BULL   # 일부만
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import random
import re
import subprocess
import sys
import time
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

log = logging.getLogger("idx_financials")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "idx_xbrl_cache"
OUT_SOURCE = PROJECT_ROOT / "data" / "idx_financials.json"
OUT_DEPLOY = PROJECT_ROOT / "docs" / "data" / "companies_financials.json"

IDX_BASE = "https://www.idx.co.id"
REPORT_API = IDX_BASE + "/primary/ListedCompany/GetFinancialReport"
PROFILE_API = IDX_BASE + "/primary/ListedCompany/GetCompanyProfiles"

# IDX 는 Cloudflare 가 Python requests 의 TLS 지문을 차단(403)하므로 curl 로 우회.
# Windows 10+ 는 curl.exe 가 기본 포함되어 별도 설치 불필요.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REFERER = IDX_BASE + "/en/listed-companies/financial-statements-and-annual-report"

# 수집 대상 연도 (최신 → 과거). 각 audit 인스턴스에서 당해연도 값만 취한다.
YEARS = ["2025", "2024", "2023", "2022", "2021"]

# IDR → USD 연도별 평균 환율 (Bank Indonesia 참조환율 근사치).
# USD 비교용 정규화에만 사용하며, native 값은 보고 통화 원본을 그대로 보존한다.
FX_IDR_PER_USD = {
    "2021": 14308.0,
    "2022": 14849.0,
    "2023": 15237.0,
    "2024": 15848.0,
    "2025": 16400.0,
}

# 인도네시아 상장 해운/항만 유니버스 (~37개사).
# (ticker, name_short, segment). 정식 사명·홈페이지는 IDX 프로필에서 보강.
UNIVERSE: list[tuple[str, str, str]] = [
    # 컨테이너 / 일반화물 / 라이너
    ("SMDR", "Samudera Indonesia", "Container/General"),
    ("TMAS", "Temas", "Container/General"),
    ("PJHB", "Pelayaran Jaya Hidup Baru", "Container/General"),
    ("MITI", "Mitra Investindo", "Container/General"),
    ("NELY", "Nelly Dwi Putri", "Tug & Barge"),
    # 탱커 (원유/석유제품/케미컬/가스)
    ("BULL", "Buana Lintas Lautan", "Tanker"),
    ("SOCI", "Soechi Lines", "Tanker"),
    ("HITS", "Humpuss Intermoda", "Tanker/Gas"),
    ("HUMI", "Humpuss Maritim Intl", "Tanker/Gas"),
    ("GTSI", "GTS Internasional", "Gas (LNG/LPG)"),
    ("SHIP", "Sillo Maritime Perdana", "Tanker/Offshore"),
    ("BLTA", "Berlian Laju Tanker", "Tanker"),
    # 벌크 / 석탄운반
    ("PSSI", "IMC Pelita Logistik", "Bulk/Coal"),
    ("MBSS", "Mitrabahtera Segara Sejati", "Bulk/Coal"),
    ("HAIS", "Hasnur Internasional Shipping", "Bulk/Coal"),
    ("TCPI", "Transcoal Pacific", "Bulk/Coal"),
    ("TPMA", "Trans Power Marine", "Bulk/Coal"),
    ("BESS", "Batulicin Nusantara Maritim", "Bulk/Coal"),
    ("BSML", "Bintang Samudera Mandiri Lines", "Bulk/Coal"),
    ("PSAT", "Pancaran Samudera Transport", "Bulk/Coal"),
    ("ALII", "Ancara Logistics Indonesia", "Bulk/Coal"),
    ("CBRE", "Cakra Buana Resources Energi", "Bulk/Coal"),
    ("KLAS", "Pelayaran Kurnia Lautan Semesta", "Bulk/Coal"),
    ("HATM", "Habco Trans Maritima", "Bulk/Coal"),
    ("DWGL", "Dwi Guna Laksana", "Bulk/Coal"),
    # 해양지원선 (OSV / 오프쇼어)
    ("WINS", "Wintermar Offshore Marine", "Offshore"),
    ("LEAD", "Logindo Samudramakmur", "Offshore"),
    ("BBRM", "Bina Buana Raya", "Offshore"),
    ("TAMU", "Tamarin Samudra", "Offshore"),
    ("BOAT", "Newport Marine Services", "Offshore"),
    ("CANI", "Capitol Nusantara Indonesia", "Offshore"),
    ("ELPI", "Ekalya Purnamasari", "Offshore"),
    # 항만 / 해양 서비스
    ("IPCM", "Jasa Armada Indonesia", "Port/Services"),
    ("IPCC", "Indonesia Kendaraan Terminal", "Port/Services"),
    ("PORT", "Nusantara Pelabuhan Handal", "Port/Services"),
    ("KARW", "Meratus Jasa Prima", "Port/Services"),
]

# 추출할 XBRL 개념. (필드명 → idx-cor 태그, 컨텍스트 종류)
#   instant   = 재무상태표 (CurrentYearInstant, 기말 시점)
#   duration  = 손익/현금흐름 (CurrentYearDuration, 당기 기간)
CONCEPTS_DURATION = {
    "revenue": "SalesAndRevenue",
    "cogs": "CostOfSalesAndRevenue",
    "gross_profit": "GrossProfit",
    # 영업이익(Laba Usaha) 구성요소 — IDX 택소노미엔 영업이익 단일 태그가 없어
    # gross_profit − 판관비 + 기타영업손익 으로 도출(pretax 와 재무손익·지분법으로
    # 정확히 정합). 아래 4개는 도출용 컴포넌트.
    "selling_expenses": "SellingExpenses",
    "ga_expenses": "GeneralAndAdministrativeExpenses",
    "other_income": "OtherIncome",
    "other_expenses": "OtherExpenses",
    "pretax": "ProfitLossBeforeIncomeTax",
    "net_income": "ProfitLoss",
    "net_income_parent": "ProfitLossAttributableToParentEntity",
    "op_cash_flow": "NetCashFlowsReceivedFromUsedInOperatingActivities",
    "inv_cash_flow": "NetCashFlowsReceivedFromUsedInInvestingActivities",
}
CONCEPTS_INSTANT = {
    "total_assets": "Assets",
    "current_assets": "CurrentAssets",
    "total_liabilities": "Liabilities",
    "current_liabilities": "CurrentLiabilities",
    "equity": "Equity",
    "equity_parent": "EquityAttributableToEquityOwnersOfParentEntity",
}
CTX_DURATION = "CurrentYearDuration"
CTX_INSTANT = "CurrentYearInstant"


# --------------------------------------------------------------------------
# 네트워크 (curl 서브프로세스 — Cloudflare 우회)
# --------------------------------------------------------------------------
# IDX Cloudflare 는 짧은 시간 다량요청을 throttle(403)하고 수분간 쿨다운을
#건다. 따라서 요청 간 정중한 지연(REQUEST_DELAY)을 두고 직렬/저동시성으로
# 받는 것이 안전하다. main()에서 --delay/--workers 로 조정.
REQUEST_DELAY = 0.0


def _curl(url: str, *, timeout: int = 40, tries: int = 4) -> bytes | None:
    """curl 로 URL 을 받아 raw bytes 반환. 실패 시 None.

    요청 전 REQUEST_DELAY 만큼 대기(+지터)하고, 실패 시 지수 백오프로 재시도.
    """
    args = [
        "curl", "-s", "-f", "--compressed", "-m", str(timeout),
        "-A", USER_AGENT, "-e", REFERER,
        "-H", "Accept: application/json, text/plain, */*",
        url,
    ]
    last = ""
    for i in range(tries):
        if REQUEST_DELAY:
            time.sleep(REQUEST_DELAY + random.uniform(0, REQUEST_DELAY * 0.5))
        try:
            p = subprocess.run(args, capture_output=True, timeout=timeout + 10)
            if p.returncode == 0 and p.stdout:
                return p.stdout
            last = f"rc={p.returncode} {p.stderr[:120]!r}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        log.debug("curl retry %d %s: %s", i + 1, url[:80], last)
        time.sleep((2.0 ** i) + random.uniform(0, 1.0))  # 백오프
    log.debug("curl gave up %s: %s", url[:80], last)
    return None


def _curl_json(url: str):
    raw = _curl(url)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None


def find_instance_url(ticker: str, year: str):
    """(ticker, year, audit) 의 instance.zip 경로 조회.

    반환:
      str  - instance.zip URL
      ""   - API 정상응답, 그러나 해당 보고서/첨부 없음 (진짜 결측 → 캐시 가능)
      None - 요청 자체 실패 (throttle/네트워크 → 일시적, 캐시 금지)
    """
    params = {
        "indexFrom": 0, "pageSize": 5, "year": year, "reportType": "rdf",
        "EmitenType": "s", "periode": "audit", "kodeEmiten": ticker,
        "SortColumn": "KodeEmiten", "SortOrder": "asc",
    }
    d = _curl_json(REPORT_API + "?" + urllib.parse.urlencode(params))
    if d is None:
        return None  # 일시적 실패
    results = d.get("Results") or []
    if not results:
        return ""  # 해당 연도 audit 보고 없음
    for att in results[0].get("Attachments", []):
        if att.get("File_Name") == "instance.zip":
            return IDX_BASE + urllib.parse.quote(att["File_Path"])
    return ""  # 보고는 있으나 XBRL instance 미첨부


def fetch_instance_xml(ticker: str, year: str, refresh: bool = False) -> str | None:
    """instance.xbrl 텍스트를 반환 (zip 은 캐시). 일시적 실패는 캐시하지 않음."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{ticker}_{year}.zip"
    miss = CACHE_DIR / f"{ticker}_{year}.miss"
    if not refresh and cache.exists():
        data = cache.read_bytes()
    elif not refresh and miss.exists():
        return None
    else:
        url = find_instance_url(ticker, year)
        if url is None:
            return None  # throttle/네트워크 → 다음 실행 때 재시도 (miss 안 남김)
        if url == "":
            miss.write_text("no audited XBRL filed", encoding="utf-8")
            return None  # 진짜 결측만 캐시
        data = _curl(url, timeout=60)
        if not data or data[:2] != b"PK":  # zip 매직넘버 확인
            log.warning("%s %s download failed (will retry)", ticker, year)
            return None  # 다운로드 실패도 일시적 취급 → 재시도
        cache.write_bytes(data)
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            name = next((n for n in z.namelist() if n.endswith(".xbrl")), None)
            if not name:
                return None
            return z.read(name).decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        log.warning("%s %s unzip failed: %s", ticker, year, e)
        return None


# --------------------------------------------------------------------------
# XBRL 파싱
# --------------------------------------------------------------------------
def _detect_currency(xml: str) -> str:
    """보고 통화 코드(USD/IDR 등). 단위 정의를 우선, dei 설명을 보조로."""
    # Revenue/Assets 가 참조하는 unit 의 iso4217 코드 우선
    units = dict(re.findall(
        r'<unit id="([^"]+)">\s*<measure>iso4217:([A-Z]{3})</measure>', xml))
    m = re.search(r'<idx-cor:(?:SalesAndRevenue|Assets)\b[^>]*unitRef="([^"]+)"', xml)
    if m and m.group(1) in units:
        return units[m.group(1)]
    # fallback: dei 설명 텍스트
    m = re.search(
        r'<idx-dei:DescriptionOfPresentationCurrency[^>]*>(.*?)</idx-dei:', xml)
    txt = (m.group(1) if m else "").upper()
    if "USD" in txt or "DOLLAR" in txt:
        return "USD"
    if "IDR" in txt or "RUPIAH" in txt:
        return "IDR"
    # 마지막 fallback: 등장 빈도
    return "USD" if xml.count("iso4217:USD") > xml.count("iso4217:IDR") else "IDR"


def _rounding_label(xml: str) -> str:
    """PDF 표기상의 반올림 단위 라벨(참고용). XBRL 인스턴스 값 자체는 항상
    전액(full amount)으로 저장되므로 스케일링에는 쓰지 않는다."""
    m = re.search(
        r'<idx-dei:LevelOfRoundingUsedInFinancialStatements[^>]*>(.*?)</idx-dei:',
        xml)
    return (m.group(1).strip() if m else "")


def _fact(xml: str, tag: str, ctx: str) -> float | None:
    """idx-cor:tag @ contextRef=ctx 값(float). nil/빈값/비숫자는 None."""
    m = re.search(
        r'<idx-cor:' + tag + r'\b[^>]*contextRef="' + ctx + r'"[^>]*>([^<]*)</idx-cor:'
        + tag + r'>', xml)
    if not m:
        # 속성 순서가 다른 경우(contextRef 가 뒤) 대비
        m = re.search(
            r'<idx-cor:' + tag + r'\b(?=[^>]*contextRef="' + ctx + r'")[^>]*>([^<]*)</idx-cor:'
            + tag + r'>', xml)
    if not m:
        return None
    raw = m.group(1).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_year(xml: str) -> dict:
    """단일 인스턴스(당해연도)에서 재무 값 추출. XBRL 값은 항상 전액 단위."""
    currency = _detect_currency(xml)
    vals: dict[str, float | None] = {"currency": currency}
    for field, tag in CONCEPTS_DURATION.items():
        vals[field] = _fact(xml, tag, CTX_DURATION)
    for field, tag in CONCEPTS_INSTANT.items():
        vals[field] = _fact(xml, tag, CTX_INSTANT)
    return vals


# --------------------------------------------------------------------------
# 정규화 + 파생지표
# --------------------------------------------------------------------------
_METRIC_FIELDS = (
    list(CONCEPTS_DURATION.keys()) + list(CONCEPTS_INSTANT.keys())
)


def _ratio(num, den):
    if num is None or den in (None, 0):
        return None
    return num / den


def build_row(ticker: str, year: str, native: dict) -> dict:
    """native 값 → USD 백만 환산 + 비율. 차트/표가 쓰는 정본 row."""
    cur = native.get("currency", "IDR")
    fx = FX_IDR_PER_USD.get(year, FX_IDR_PER_USD["2024"])
    # USD full → USD; IDR full → / fx
    to_usd = (lambda v: v) if cur == "USD" else (lambda v: (v / fx) if v is not None else None)

    usd_m: dict[str, float | None] = {}
    nat_m: dict[str, float | None] = {}
    for f in _METRIC_FIELDS:
        v = native.get(f)
        usd_m[f] = round(to_usd(v) / 1e6, 3) if v is not None else None
        nat_m[f] = round(v / 1e6, 3) if v is not None else None  # native 백만

    # gross_profit 결측 시 revenue-cogs 로 보강
    if usd_m.get("gross_profit") is None and native.get("revenue") is not None \
            and native.get("cogs") is not None:
        gp = native["revenue"] - native["cogs"]
        usd_m["gross_profit"] = round(to_usd(gp) / 1e6, 3)
        nat_m["gross_profit"] = round(gp / 1e6, 3)

    rev = native.get("revenue")
    ni = native.get("net_income")
    nip = native.get("net_income_parent")
    eq = native.get("equity")
    eqp = native.get("equity_parent")
    ta = native.get("total_assets")
    tl = native.get("total_liabilities")
    ca = native.get("current_assets")
    cl = native.get("current_liabilities")
    gp = native.get("gross_profit")
    if gp is None and rev is not None and native.get("cogs") is not None:
        gp = rev - native["cogs"]

    # 영업이익(Laba Usaha) = 매출총이익 − 판매비 − 일반관리비 + 기타영업수익 − 기타영업비용
    # (재무손익·지분법손익은 비영업으로 제외 → pretax 와 정합 확인됨)
    op_profit = None
    if gp is not None:
        op_profit = (gp
                     - (native.get("selling_expenses") or 0.0)
                     - (native.get("ga_expenses") or 0.0)
                     + (native.get("other_income") or 0.0)
                     - (native.get("other_expenses") or 0.0))
    usd_m["operating_profit"] = round(to_usd(op_profit) / 1e6, 3) if op_profit is not None else None
    nat_m["operating_profit"] = round(op_profit / 1e6, 3) if op_profit is not None else None

    row = {
        "ticker": ticker,
        "year": year,
        "currency": cur,
        "fx_idr_per_usd": fx if cur == "IDR" else None,
        # USD 백만 (비교 정본)
        **usd_m,
        # native 백만 (상세용)
        "native": {k: nat_m[k] for k in ("revenue", "operating_profit", "net_income",
                                          "total_assets", "total_liabilities", "equity")},
        # 비율 (통화 무관)
        "operating_margin": _pct(_ratio(op_profit, rev)),
        "net_margin": _pct(_ratio(ni, rev)),
        "gross_margin": _pct(_ratio(gp, rev)),
        "roe": _pct(_ratio(nip if nip is not None else ni, eqp if eqp is not None else eq)),
        "roa": _pct(_ratio(ni, ta)),
        "der": _round(_ratio(tl, eq)),
        "debt_to_assets": _pct(_ratio(tl, ta)),
        "current_ratio": _round(_ratio(ca, cl)),
    }
    return row


def _pct(x):
    return round(x * 100.0, 2) if x is not None else None


def _round(x, n=3):
    return round(x, n) if x is not None else None


# --------------------------------------------------------------------------
# 프로필 (정식 사명 / 홈페이지)
# --------------------------------------------------------------------------
def load_profiles() -> dict:
    url = PROFILE_API + "?" + urllib.parse.urlencode(
        {"start": 0, "length": 9999, "language": "en-us"})
    d = _curl_json(url)
    if not d:
        log.warning("profile fetch failed")
        return {}
    out = {}
    for r in d.get("data", []):
        out[r.get("KodeEmiten")] = {
            "name": r.get("NamaEmiten") or "",
            "homepage": (r.get("Website") or "").strip(),
            "listing_date": (r.get("TanggalPencatatan") or "")[:10],
        }
    return out


# --------------------------------------------------------------------------
# 메인
# --------------------------------------------------------------------------
def collect(only: list[str] | None, refresh: bool, workers: int = 4) -> dict:
    profiles = load_profiles()
    universe = [u for u in UNIVERSE if not only or u[0] in only]

    # (ticker, year) 작업 목록
    jobs = [(t, y) for (t, _, _) in universe for y in YEARS]
    parsed: dict[tuple[str, str], dict] = {}

    def work(job):
        t, y = job
        xml = fetch_instance_xml(t, y, refresh=refresh)
        if not xml:
            return job, None
        return job, parse_year(xml)

    if workers <= 1:
        # 직렬 모드 — throttle 회피용 (정중한 지연은 REQUEST_DELAY 가 담당)
        for n, j in enumerate(jobs, 1):
            job, res = work(j)
            if res:
                parsed[job] = res
            if n % 10 == 0:
                log.info("  ... %d/%d fetched (have %d)", n, len(jobs), len(parsed))
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(work, j): j for j in jobs}
            done = 0
            for fut in as_completed(futs):
                job, res = fut.result()
                done += 1
                if res:
                    parsed[job] = res
                if done % 20 == 0:
                    log.info("  ... %d/%d fetched", done, len(jobs))

    companies = []
    rows = []
    for ticker, name_short, segment in universe:
        yrs_have = [y for y in YEARS if (ticker, y) in parsed]
        if not yrs_have:
            log.warning("%s: no XBRL data (skipped)", ticker)
            continue
        yrs_sorted = sorted(yrs_have)
        prof = profiles.get(ticker, {})
        # 통화: 가장 최근 연도 기준
        latest = yrs_sorted[-1]
        currency = parsed[(ticker, latest)].get("currency", "IDR")
        for y in yrs_sorted:
            rows.append(build_row(ticker, y, parsed[(ticker, y)]))
        companies.append({
            "ticker": ticker,
            "name": prof.get("name") or name_short,
            "name_short": name_short,
            "segment": segment,
            "currency": currency,
            "homepage": prof.get("homepage", ""),
            "listing_date": prof.get("listing_date", ""),
            "years": yrs_sorted,
            "latest_year": latest,
            "data_quality": "idx_xbrl_audited",
        })

    companies.sort(key=lambda c: c["ticker"])
    rows.sort(key=lambda r: (r["ticker"], r["year"]))

    payload = {
        "metadata": {
            "source": "IDX XBRL (instance.zip, periode=audit)",
            "source_url": "https://www.idx.co.id/en/listed-companies/financial-statements-and-annual-report",
            "report_type": "Audited annual financial statements",
            "fetched_at": _dt.date.today().isoformat(),
            "comparison_currency": "USD",
            "comparison_unit": "million",
            "native_unit": "million (in reporting currency)",
            "years": YEARS[::-1],
            "fx_idr_per_usd": FX_IDR_PER_USD,
            "fx_note": "IDR 보고사는 USD 비교를 위해 연도별 평균환율(Bank Indonesia 참조환율 근사치)로 환산. native 값은 보고 통화 원본 보존.",
            "concepts": {**CONCEPTS_DURATION, **CONCEPTS_INSTANT},
            "company_count": len(companies),
            "notes": "IDX 감사 재무제표 XBRL 자동 수집. 일부 신규상장사·미제출사는 연도가 비어있을 수 있음.",
        },
        "companies": companies,
        "rows": rows,
    }
    return payload


def main(argv=None) -> int:
    global REQUEST_DELAY
    ap = argparse.ArgumentParser(description="IDX XBRL 해운사 재무 수집기")
    ap.add_argument("--only", nargs="*", help="특정 ticker 만 수집")
    ap.add_argument("--refresh", action="store_true", help="캐시 무시 후 재다운로드")
    ap.add_argument("--workers", type=int, default=4,
                    help="동시 요청 수 (1=직렬, throttle 회피). 기본 4")
    ap.add_argument("--delay", type=float, default=0.0,
                    help="요청 간 정중한 지연(초). throttle 발생 시 1~2 권장")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s")
    REQUEST_DELAY = args.delay

    log.info("=== IDX XBRL 해운사 재무 수집 시작 (years=%s, workers=%d, delay=%.1fs) ===",
             ",".join(YEARS), args.workers, args.delay)
    payload = collect(args.only, args.refresh, workers=args.workers)

    cov = sum(len(c["years"]) for c in payload["companies"])
    log.info("수집 완료: %d개사 / %d (company-year) rows",
             payload["metadata"]["company_count"], len(payload["rows"]))

    OUT_SOURCE.parent.mkdir(parents=True, exist_ok=True)
    OUT_SOURCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    OUT_DEPLOY.parent.mkdir(parents=True, exist_ok=True)
    OUT_DEPLOY.write_text(json.dumps(payload, ensure_ascii=False,
                                     separators=(",", ":")),
                          encoding="utf-8")
    log.info("wrote %s", OUT_SOURCE)
    log.info("wrote %s", OUT_DEPLOY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
