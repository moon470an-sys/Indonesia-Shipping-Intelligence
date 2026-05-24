# Indonesia Shipping Intelligence

🌐 **Live dashboard**: https://moon470an-sys.github.io/Indonesia-Shipping-Intelligence/

인도네시아 해사청 선박 등록(`kapal.dephub.go.id`)과 Inaportnet 항만 LK3 물동량(`monitoring-inaportnet.dephub.go.id`) 데이터를 매월 자동 수집하고 변경사항을 추적하는 BI 시스템.

## 컴포넌트

| 폴더 | 역할 |
|------|------|
| `backend/` | Python 수집·DB·diff·리포트 파이프라인 |
| `dashboard/` | Streamlit 인터랙티브 대시보드 (사내용, DB 직결) |
| `docs/` | GitHub Pages 정적 사이트 (대외 공개) |

## 빠른 시작

```bash
# 1. 의존성
pip install -r requirements.txt

# 2. 한 번에 무인 실행 (수집 + diff + 리포트)
python -m backend.main monthly --auto

# 3. 정적 사이트 JSON 갱신
python -m backend.build_static

# 4. (선택) 사내 대시보드
python -m streamlit run dashboard/app.py
```

## 매월 자동 갱신

```bash
python -m backend.scheduler   # 매월 1일 03:00 KST
```

## 데이터 흐름

```
정부 API ─▶ Python 수집 ─▶ SQLite (data/shipping_bi.db)
                              │
                              ├─▶ vessels_changes / cargo_changes (월 단위 diff)
                              ├─▶ reports/changes_YYYY-MM.html / .xlsx
                              ├─▶ Streamlit (사내)
                              └─▶ docs/data/*.json ─▶ GitHub Pages (대외)
```

## CLI 요약

| 명령 | 설명 |
|------|------|
| `python -m backend.main test-fleet`  | 선복량 샘플 테스트 |
| `python -m backend.main test-cargo`  | 물동량 샘플 테스트 |
| `python -m backend.main run-fleet`   | 선복량 전수 수집 |
| `python -m backend.main run-cargo`   | 물동량 전수 수집 |
| `python -m backend.main diff --month YYYY-MM` | 변경 탐지 |
| `python -m backend.main report --month YYYY-MM --html` | 리포트 |
| `python -m backend.main monthly --auto` | 전체 무인 실행 |
| `python -m backend.main monthly --resume` | 누락분만 보충 |
| `python -m backend.resume_run` | 코드 단위 누락 + diff + 리포트 |
| `python -m backend.build_static` | 정적 사이트 JSON 빌드 |
| `python scripts/fetch_idx_financials.py` | IDX XBRL 해운사 재무 수집 (💼 Financials 탭) |
| `python -m backend.scheduler` | APScheduler 실행 |

## 변경 탐지 의미

- **ADDED / REMOVED**: 새로 등록되거나 사라진 선박/항구-월 키
- **MODIFIED**: 동일 선박 키의 필드가 바뀜 (선명/선사/GT/선종 등)
- **REVISED**: 동일 항구·월·구분의 LK3 행수·총합 변동 (delta % 임계 초과)

## Market 탭 — 주간 시장 인텔리전스 갱신

📊 Market 탭은 backend 파이프라인과 별도로 운영되는 **큐레이션 데이터** 입니다.
출처를 검증할 수 있는 외부 공개 정보만 입력합니다.

**데이터 파일**: `docs/data/market.json`

### 웹 검색 기반 자동 갱신 (주 1회)

가격·지수·뉴스 필드는 **예약된 Claude 에이전트**가 매주 웹 검색 + 인도네시아 로컬
SNS 큐레이션으로 자동 갱신하고 commit/push 합니다. GitHub Pages 가 자동 배포합니다.

- **절차서**: [`MARKET_REFRESH_PLAYBOOK.md`](MARKET_REFRESH_PLAYBOOK.md) — 자동
  에이전트와 수동 실행이 공통으로 따르는 단일 SOP
- **수동 실행**: Claude Code 에서 `/market-refresh` (절차서를 그대로 수행)
- **스케줄 변경**: `/schedule` skill 로 루틴 cadence/시각 수정
- 도메스틱 선박 가격표(`domestic_vessel_pricing`)는 공개 표가 없으므로 Facebook
  Marketplace·LinkedIn·OLX·로컬 브로커 게시물에서 매물/용선 사례를 검색해 보강하며,
  근거 못 찾은 행은 추정 없이 그대로 둡니다.

### 수동 직접 편집 (예외 시)

1. `docs/data/market.json` 직접 편집 — 스키마는 `MARKET_REFRESH_PLAYBOOK.md` §4 참조
2. `checked_date`·`last_updated`·`next_scheduled`·`report_week` 갱신
3. 모든 항목에 **반드시** 출처(`source_name`/`sources[]`)·URL·날짜 포함
4. 검증 안 된 수치는 `"status": "indicative"` 로 표시
5. `python scripts/lint_language.py` 통과 확인 (가치 판단 표현 금지)
6. `git commit -m "Market <date> 갱신"` + `git push` → GitHub Pages 자동 배포

### 권장 출처

| 카테고리 | 권장 출처 |
|---------|----------|
| BDI / 운임 지수 | The DCN Baltic Exchange Weekly, HandyBulk, Trading Economics |
| 인도네시아 HBA / 석탄 | Mysteel, CoalTradeIndo, Argus Coalindo, Petromindo |
| CPO | Palm Oil Magazine, Bursa Malaysia, GAPKI |
| 니켈 / LME | Mining.com, IDNFinancials, S&P Global |
| 인도네시아 해운 뉴스 | Pelindo, Pertamina PIS, Indonesia Shipping Gazette, Splash247, Bisnis Indonesia |
| 행사 | INAMARINE, GAPKI, Fastmarkets Coaltrans, Petromindo |
| SNS | LinkedIn (Pertamina PIS, Pelindo, GAPKI), X/Twitter, Instagram (@inamarine) |

### 원칙

- **출처 부족** → 해당 항목 제외 또는 별도 `unverified` 섹션 (현재는 미사용)
- **빈 섹션** → "No recent verified data found" 자동 표시
- **가치 판단 표현 금지** — `scripts/lint_language.py` 블랙리스트 (유망/추천/기회/투자 테제 등) 회피
- **추정·해석 금지** — 외부 분석/예측은 출처 기관 명시 후 인용 형태로만 노출

## 💼 Financials 탭 — 상장 해운사 재무 (IDX XBRL)

인도네시아 증권거래소(IDX)가 상장사별로 공시하는 **감사받은 연차 재무제표
XBRL 인스턴스**(`instance.zip`)를 자동 수집해, 해운/항만 ~37개사의 매출·순이익·
자산·부채·자본 및 파생 비율(순이익률·ROE·ROA·DER·유동비율)을 표시합니다.

**수집기**: `scripts/fetch_idx_financials.py`

```bash
python scripts/fetch_idx_financials.py                 # 캐시 활용 수집
python scripts/fetch_idx_financials.py --workers 1 --delay 1.2   # throttle 회피(정중)
python scripts/fetch_idx_financials.py --refresh       # 전체 재다운로드
python scripts/fetch_idx_financials.py --only SMDR BULL  # 일부만
```

- **출처**: `GetFinancialReport` API → `instance.zip` 내 `instance.xbrl`
  (idx-cor / idx-dei 개념). 값은 항상 전액(full amount) 단위.
- **통화**: 보고통화가 제각각(SMDR·BULL 등 USD, Temas 등 IDR)이라 **USD 백만**으로
  환산 비교(연도별 평균환율)하고, 개별 상세에는 **원 보고통화** 수치를 병기.
- **출력**: `data/idx_financials.json`(정본) + `docs/data/companies_financials.json`(배포).
  `backend.build_static` 는 정본이 있으면 이를 그대로 통과(없으면 레거시 YAML 폴백).
- **캐시**: `data/idx_xbrl_cache/*.zip` (gitignore). XBRL 은 연 1회 갱신이므로 재실행은
  네트워크를 건너뜀. IDX 는 Cloudflare 가 Python TLS 를 차단(403)하므로 `curl` 로 우회.
- **갱신 주기**: 연 1회 감사보고서 제출(통상 3~4월) 이후 1회 실행으로 충분.
