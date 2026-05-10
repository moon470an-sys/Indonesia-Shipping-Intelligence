# Indonesia Shipping Intelligence — Overnight Upgrade 지시문

## 0. 목표 (한 줄)

기존 정적 사이트를 보존한 채 **사실 기반 정보 레퍼런스**로 업그레이드한다. Overnight 1회 빌드로 PR 5개를 병렬 생성·머지한다.

- 저장소: `https://github.com/moon470an-sys/Indonesia-Shipping-Intelligence`
- 배포: GitHub Pages (정적, 단일 `index.html` + `docs/derived/*.json`)
- 백엔드 추가 금지, 차트 라이브러리 교체 금지, 번들 크기 증가 최소화

## 1. 절대 원칙 (Hard Rules)

1. 특정 회사·티커·항구를 "유망/추천/기회"로 지칭하지 않는다.
2. 가치 판단 표현 금지: `Sweet Spot`, `Watchlist`, `투자 테제`, `Hot`, `Top Pick`, `주목할 만한`, `공급 부족`, `수요 충격`, `주의 요망`, `Risk Alert`.
3. 대신 사실 표현만: `성장률 상위`, `선령 평균 높음`, `MoM 변동 ±X% 초과`, `Top N (기준: GT)`, `Recent Events`.
4. 모든 차트·표·KPI에 **출처 라벨** 필수.
5. 모든 페이지 푸터에 면책 문구 고정:
   > 본 사이트는 공개 데이터를 가공한 정보 레퍼런스이며, 투자 권유나 자문이 아닙니다. 데이터의 정확성·최신성은 보장되지 않습니다.

## 2. 작업 분해 (5개 PR, 병렬 가능)

각 PR은 **독립 브랜치**에서 동시 작업 가능하도록 파일 충돌이 없게 분리했다.

| PR | 브랜치 | 주요 산출물 | 의존성 |
|---|---|---|---|
| **PR-A: Data** | `feat/derived-json` | `docs/derived/*.json` 6종 + 빌드 스크립트 | 없음 (먼저 시작) |
| **PR-B: IA & Footer** | `feat/ia-footer` | 탭 라벨 변경, 면책 푸터, 출처 라벨 컴포넌트 | 없음 |
| **PR-C: Market Overview** | `feat/market-overview` | 신규 탭 (KPI 6 + 산점도 + 사실 카드 3 + Top 20 표) | PR-A |
| **PR-D: Tanker Sector** | `feat/tanker-sector` | 신규 최상위 탭 (subclass 필터 + 사실 카드 + 항로 산점도) | PR-A |
| **PR-E: Events & Glossary** | `feat/events-glossary` | Recent Events 패널 + Glossary 탭 + 블랙리스트 lint | PR-A |

**병렬 전략**: PR-A를 먼저 시작 → mock JSON push 후 PR-B/C/D/E 동시 진행. 머지 순서는 A → B → (C, D, E 동시).

## 3. PR-A: Data Pipeline (`feat/derived-json`)

기존 Python 추출 단계 마지막에 다음 6개 JSON을 생성한다. 한 스크립트(`scripts/build_derived.py`)에 묶어 1회 실행으로 끝낸다.

```
docs/derived/meta.json              # latest_lk3_month, latest_vessel_snapshot_date, build_at
docs/derived/subclass_facts.json    # subclass별 CAGR, 평균선령, HHI, calls/vessel, 운영사 수
docs/derived/route_facts.json       # Top 60 항로의 변화율·선박 수·총 ton
docs/derived/owner_profile.json     # owner별 tankers, GT, subclass mix, top 5 routes, ticker
docs/derived/recent_events.json     # 최근 90일 자동 추출 이벤트
docs/derived/owner_ticker_map.json  # 수동 매핑 (초안 7개, 검증 후 보강)
```

### 추출 룰 (간결)

- **CAGR**: `(latest_12m / prev_12m) ^ (1/2) - 1` (24M 기준 연환산). 데이터 부족 시 `null`.
- **HHI**: 운영사별 GT 점유율 제곱합. 0~10000 스케일.
- **Recent Events 임계값**:
  - 신규 탱커 등록 + GT ≥ 5,000 → `new_registration`
  - 동일 owner 1개월 내 ±3척 변동 → `fleet_change`
  - subclass MoM ton 변화 ±30% → `volume_change`
  - 항구 MoM ton 변화 ±50% → `port_change`
- 이벤트는 사실 한 줄 + `chart_link` 필드만. 결론 텍스트 금지.

### `owner_ticker_map.json` 초안

```json
{
  "BLTA": ["PT BERLIAN LAJU TANKER"],
  "BULL": ["PT BUANA LISTYA TAMA"],
  "SMDR": ["PT SAMUDERA INDONESIA"],
  "ELPI": ["PT PELITA SAMUDERA SHIPPING"],
  "SOCI": ["PT SOECHI LINES"],
  "GTSI": ["PT GTS INTERNASIONAL"],
  "HUMI": ["PT HUMPUSS MARITIM INTERNASIONAL"]
}
```

owner 명 표기 차이로 매칭 안 되는 항목은 `unmatched.log`로 출력.

## 4. PR-B: IA & Footer (`feat/ia-footer`)

`index.html`에서 다음만 수정한다 (작은 변경, 충돌 최소).

### 4.1 탭 라벨 변경

```
Overview     → Market Overview      (첫 번째 탭, 기본 진입)
(신규)       → Tanker Sector        (신규 최상위 탭, 콘텐츠는 PR-D)
Cargo        → Cargo
Fleet        → Fleet
Financials   → Listed Operators
Trends       → Trends
Changes      → Changes
About        → Glossary & Methodology
```

### 4.2 면책 푸터 (전역 1회)

`<footer id="global-footer">`에 면책 문구 + 데이터 신선도(`docs/derived/meta.json`) 표시. `@media print`에서도 보이도록 CSS.

### 4.3 출처 라벨 공통 컴포넌트

`<small class="source-label">`로 모든 차트·표·KPI 하단에 배치:

- LK3: `Source: monitoring-inaportnet.dephub.go.id (LK3, YYYY-MM)`
- 선박 등록: `Source: kapal.dephub.go.id (snapshot YYYY-MM-DD)`
- 재무: `Source: IDX disclosure, FY YYYY`

기존 차트마다 라벨을 일괄 주입하는 헬퍼 `addSourceLabel(el, source)` 추가.

## 5. PR-C: Market Overview (`feat/market-overview`)

신규 탭 1개. `docs/derived/subclass_facts.json` + `docs/derived/owner_profile.json` 의존.

### 5.1 헤더 KPI 6개 (한 줄, 모바일 2×3)

| # | 카드 | 데이터 |
|---|---|---|
| 1 | 인도네시아 전체 12M ton | LK3 |
| 2 | 탱커 12M ton | LK3 |
| 3 | 등록 선박 (전체/탱커) | kapal |
| 4 | 탱커 평균 선령 (GT 가중) | kapal |
| 5 | ln vs dn 비중 | LK3 |
| 6 | 데이터 신선도 | meta |

각 카드: 큰 숫자 + 24M 스파크라인 + MoM% 배지 + ⓘ hover 산식.

### 5.2 Subclass 산점도

- x: 24M ton CAGR / y: 평균 선령 / 크기: 12M ton / 색상: subclass
- **영역 라벨링 금지** (`Sweet Spot` 등). hover 시 사실 수치만.
- 캡션: "각 점은 subclass의 24개월 변화율(x)과 평균 선령(y)입니다. 해석은 사용자의 분석 목적에 따라 달라집니다."

### 5.3 사실 요약 카드 3개

룰베이스 1줄 텍스트:

1. "최근 12M 탱커 ton은 직전 12M 대비 {±X}% 변동했습니다."
2. "현재 등록된 탱커 중 선령 25년 이상 비중은 {X}%입니다."
3. "최근 24M 탱커 ton의 상위 5개 항로 누적 비중은 {X}%입니다."

각 카드 하단: "관련 차트 보기 →" + `Heuristic summary based on aggregated public data. Not investment advice.`

### 5.4 Top 20 운영사 표

제목: **"탱커 선대 보유 Top 20 운영사 (등록 GT 기준)"**

| owner | Tankers | Sum GT | Avg GT | subclass mix | 12M ton 점유율 | 상장 여부 |

- 정렬 기본: Sum GT
- 상장사는 Listed Operators 탭으로 링크 (단순 데이터 결합)
- 비상장: `PT (private)`
- 표 캡션에 출처 + 한계 명시

## 6. PR-D: Tanker Sector (`feat/tanker-sector`)

신규 최상위 탭. PR-B가 추가한 빈 placeholder 섹션을 채운다. 다음 4가지 위젯.

### 6.1 글로벌 subclass 필터 통일

탭 상단 토글: `ALL / Crude / Product / Chemical / LPG / LNG / FAME`. 전역 store `tankerSubclassFilter`로 모든 차트가 즉시 반응.

### 6.2 Subclass 사실 카드 (subclass별 1장)

- 24M ton CAGR (%)
- 12M 척당 평균 calls
- 평균 선령 (년)
- 운영사 수 + HHI

카드 하단: `모든 수치는 공개 데이터 집계 결과이며, 시장 전망이나 투자 판단을 의미하지 않습니다.`

### 6.3 항로 분포 산점도

- x: 항로 24M ton 변화율 / y: 활동 선박 수 / 크기: 24M ton
- Top 60 항로
- **영역 라벨링 금지**, hover 시 사실 수치만

### 6.4 규제·기술 정보 박스 (정적, 접기 가능)

`data/regulatory_notes.md` 1개 파일에 다음 사실만 정리해서 빌드 시 주입:

- 카보타지 원칙 (UU No.17/2008)
- SIUPAL 개요
- IBC Code Type 1/2/3
- IBC 2G vs IGC 2G 차이
- MARPOL Annex I vs II 차이
- PT PMA 일반 절차

각 항목에 법령 번호·IMO 문서 번호 출처. 권유 표현 금지.

## 7. PR-E: Events & Glossary (`feat/events-glossary`)

### 7.1 Recent Events 패널 (Changes 탭 상단)

`docs/derived/recent_events.json`을 시간 역순으로 표시. 사실 한 줄 + 차트 링크. **"Signal/Alert" 명칭 금지.**

| 날짜 | 유형 | 설명 (사실) | 관련 차트 |

### 7.2 Glossary & Methodology 탭

기존 About 흡수 + 다음 4개 섹션:

1. **데이터 출처**: kapal / Inaportnet / IDX 공시, 수집 주기
2. **정의·분류 기준**: Vessel Class, Tanker Subclass 매핑 표, Bongkar/Muat, HHI·CAGR 산식
3. **한계·주의사항**: owner 명 모호성, LK3 신고 기반, 재신고 가능성
4. **면책 (전용 섹션)**

### 7.3 블랙리스트 lint (CI)

`scripts/lint_language.py`로 다음 단어 등장 시 빌드 실패:

```
Sweet Spot, Watchlist, 투자 테제, Investment Thesis, Hot Sector, Top Pick,
유망, 매력적, 기회, 추천, 주목할 만한, 놓치지 말아야, 공급 부족, 수요 충격,
주의 요망, Risk Alert, Investor Signal
```

대상: `docs/index.html`, `docs/derived/*.json`, `data/*.md`, `i18n/*.json`. (이 `INSTRUCTIONS.md`는 룰 정의이므로 lint 대상 제외.)

## 8. 디자인 가이드 (최소)

- 액센트: dark navy `#1A3A6B`, sky blue `#56C0E0`
- 양/음 변화: 파랑/빨강 (방향만, 가치 신호등 금지)
- 모바일: KPI 카드 2×3 reflow
- `@media print`: 차트 한 페이지 + 면책 자동 포함
- i18n: KO/EN 토글, 데이터 라벨은 영문 유지 (기본 EN, 토글 시 KO 적용)

## 9. Overnight 실행 타임라인

```
T+0:00  PR-A 시작 (스크립트 + mock JSON 30분 내 push)
T+0:30  PR-B, PR-E lint 동시 시작 (mock JSON 사용)
T+1:00  PR-A 완료 → 실제 derived JSON 머지
T+1:00  PR-C, PR-D 동시 시작
T+3:00  PR-B, PR-E 머지
T+5:00  PR-C, PR-D 머지
T+5:30  최종 빌드 + GitHub Pages 배포
T+6:00  검증 체크리스트 (10장)
```

각 PR 완료 시 자동 검증:
- 블랙리스트 lint 통과
- 출처 라벨 누락 0
- 면책 푸터 노출
- 데이터 부족 시 `Insufficient data` 표시 (빈 차트 금지)

## 10. 최종 검증 체크리스트

- [ ] 면책 푸터 모든 페이지 노출 (인쇄 포함)
- [ ] 블랙리스트 lint 0건
- [ ] 모든 차트·표·KPI 출처 라벨
- [ ] 자동 텍스트가 사실 진술까지만 (결론·권유 없음)
- [ ] Market Overview 산점도에 영역 라벨 없음
- [ ] `docs/derived/*.json` 파일명에 평가 어휘 없음
- [ ] 모바일 2×3 reflow
- [ ] KO/EN 토글 동작
- [ ] 빌드 시간 기존 대비 +20% 이내

## 11. 작업 시작 명령 (Claude Code에 그대로 전달)

```
저장소 루트에 INSTRUCTIONS.md로 본 문서 커밋 후, 5개 브랜치 병렬 생성:
  feat/derived-json, feat/ia-footer, feat/market-overview,
  feat/tanker-sector, feat/events-glossary

PR-A 먼저 시작, mock JSON을 30분 내 push하여 PR-B/C/D/E가
의존성 없이 시작할 수 있도록 한다. 머지 순서는 A → B → (C, D, E 동시).

각 PR 본문에 변경된 탭, 신규 derived JSON, 블랙리스트 lint 결과를 명시.
모든 PR은 본 INSTRUCTIONS.md를 참조한다.
```
