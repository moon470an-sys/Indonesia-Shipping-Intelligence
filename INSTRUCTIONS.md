# Indonesia Shipping Intelligence — 직관성 강화 리뉴얼 지시문

> **이전 INSTRUCTIONS.md (overnight v1) 대체**: 5-PR overnight 빌드는 이미 완료됨 (deb7dea ~ da1b00d). 본 문서는 v2 리뉴얼 스펙.

## 0. 현재 사이트 진단

대상: `https://moon470an-sys.github.io/Indonesia-Shipping-Intelligence/`

현재 사이트는 데이터는 풍부하지만 **누구를 위한, 어떤 질문에 답하는 사이트인지 불분명**하다. 점검 결과 6가지 문제가 있다.

1. **차트 과다**: 한 탭에 10개 이상, 우선순위 없음
2. **항만 위젯 과다**: 시장 전체 흐름을 봐야 하는데 항구별 분석에 치우침
3. **필터 복잡도**: 건조연도·GT·LOA·Width·Depth 슬라이더는 운영 도구 수준
4. **로우 데이터 노출**: `code`, `IMO`, `call sign`, `vessel_key` 등 무의미한 컬럼
5. **평면적 시각화**: 단순 막대·라인 위주
6. **지도 단조로움**: 라인만 표시, 거점·흐름 직관 부족

본 리뉴얼은 **불필요한 항만 분석 위젯을 과감히 제거**하고 시장 흐름을 직관적으로 보여주는 **소수의 강력한 시각화**로 재구성한다.

## 1. 절대 원칙 (변경 없음)

1. 특정 회사·티커·항구를 "유망/추천/기회"로 지칭하지 않는다.
2. 가치 판단 표현 금지 — 블랙리스트 lint 유지 (`scripts/lint_language.py`).
3. 모든 차트·표·KPI에 출처 라벨 필수.
4. 면책 푸터 유지.

## 2. 신규 정보 구조 (탭 8개 → 5개)

```
🏠 Home              (시장 한눈에 보기, 기본 진입)  data-tab="overview"
🛢️ Tanker Sector     (탱커 시장 심화)                data-tab="tanker-sector"
📊 Cargo & Fleet     (Cargo + Fleet 통합)            data-tab="cargo-fleet"
💼 Listed Operators  (재무, 단순화)                   data-tab="financials"
📚 About             (Glossary + 면책 + 데이터 출처)  data-tab="about"
```

기존 **Trends·Changes 탭은 삭제**. 핵심 정보만 Home·Tanker Sector에 통합.

## 3. 삭제할 위젯 (PR-1)

### 3.1 항만 관련
- ❌ "Top 항구 (총 LK3 행수)"
- ❌ "주요 항구 톤수 TOP 20"
- ❌ "항구별 톤수 상세" 표
- ❌ "항구 × 화물 종류 히트맵"
- ❌ "port × period 행수 히트맵"
- ❌ "결측 키" 표
- ❌ "Top 양하 항구" / "Top 적재 항구"
- ❌ "항구별 Bongkar/Muat 균형" 산점도
- ❌ "항구 × Subclass 히트맵"

### 3.2 운영 도구성 필터
- ❌ Vessel Type (raw label) 필터
- ❌ Exclude mode 토글
- ❌ 선박명 검색 (간소화)
- ❌ 건조 연도/GT/LOA/Width/Depth 슬라이더
- ❌ "Vessel Type TOP 15" 차트
- ❌ "Gross Tonnage 분포 (log)" 차트
- ❌ "선박 목록" 표의 raw 컬럼

### 3.3 중복·저가치 차트
- ❌ "월별 LK3 행수 (data month)"
- ❌ "Sector별 calls 추이"
- ❌ "선박 Class별 월 추이"
- ❌ "화물 품목 상세 (Top 200)" 표
- ❌ Changes 탭 전체
- ❌ Trends 탭 전체

### 3.4 정리 후 위젯 수
- Home: 6 (KPI 4 + 지도 1 + 시계열 1)
- Tanker Sector: 5
- Cargo & Fleet: 4
- Listed Operators: 3
- About: 정적

**총 50+ → 18개로 축소.**

## 4. Home 탭

### 4.1 헤더 KPI 4개 (데스크톱 한 줄, 모바일 2×2)
| # | 지표 | 표시 |
|---|---|---|
| 1 | 인도네시아 12M 총 물동량 | 큰 숫자 + YoY 화살표 |
| 2 | 탱커 12M 물동량 | 큰 숫자 + YoY 화살표 |
| 3 | 탱커 등록 척수 | 큰 숫자 + 평균 선령 |
| 4 | 데이터 기준일 | YYYY-MM |

KPI 메인 숫자 36~48px.

### 4.2 메인 지도: 인도네시아 화물 흐름 (대표 시각화)

§10 참조. 디자인 원칙:
- 회색조 베이스맵
- 항구 = navy 원, 크기 ∝ 24M ton
- 항로 = 곡선, Top 30, 두께 ∝ ton, 색상 = 화물 카테고리 5색
- 흐름 애니메이션 (origin → destination 방향 파티클)
- 상단 컨트롤 3개: 카테고리 / 기간 / 트래픽 종류
- 우측 사이드바: 외국 항구 Top 10 막대
- 하단 인사이트 박스: 자동 생성 사실 3줄

### 4.3 시계열 차트 1개

"인도네시아 전체 24개월 추이" — sector 5종 stacked area. 토글: 절대값 / YoY%.

## 5. Tanker Sector 탭

### 5.1 Subclass 비교 카드 (6개)

각 subclass 카드:
- 12M ton (큰 숫자) + YoY%
- 평균 선령
- 운영사 수
- 주요 항로

호버 시 24M 스파크라인. 클릭 시 탭 전체 필터링.

### 5.2 Subclass 시장 구조 산점도 (영역 라벨 없음)
- x: 24M ton CAGR
- y: 평균 선령
- 크기: 12M ton
- 색상: subclass

### 5.3 Subclass 월별 추이
stacked area, 24M. 토글: 절대값 / YoY%.

### 5.4 Top 코모디티 가로 막대 (Top 10)
y: 코모디티명, x: 12M ton, 색상: subclass.

### 5.5 Top 운영사 가로 막대 + 도넛 (Top 15)
- 가로 막대: Sum GT
- 도넛: 상위 5 vs 그 외
- ticker 배지 → Listed Operators 탭 링크

규제 정보 박스 (PR-D에서 추가)는 탭 상단 접기형으로 유지.

## 6. Cargo & Fleet 탭

### 6.1 Cargo 트리맵 (Top 15 카테고리)
사각형 크기 = ton, 색상 = sector.

### 6.2 Cargo 품목 Top 10 가로 막대

### 6.3 Fleet Class 도넛
Container / Bulk / Tanker / General / Other 비율.

### 6.4 Fleet 선령 분포 막대
5년 단위, 25년 이상 강조.

선박 목록 14컬럼 표 **삭제**.

## 7. Listed Operators 탭

### 7.1 KPI 4개
- 총 매출 / 평균 순이익률 / 평균 부채비율 / 합산 선대 GT

### 7.2 매출/순이익률 산점도 (영역 라벨 금지)
- x: 매출 (log) / y: 순이익률 / 크기: 선대 GT

### 7.3 재무 비교 표 (간소화)
| ticker | name | 매출 | 순이익률 | ROA | 부채비율 | 선대 GT |

기존 매출 추이 라인 + 별도 산점도는 **삭제**.

## 8. About 탭

기존 Glossary 유지 + 다음 추가:
- Vessel Class·Tanker Subclass 정의 표
- 용어집 (Bongkar, Muat, GT, DWT, CAGR, HHI)
- 데이터 한계
- 면책 (전용 섹션)

규제 정보(카보타지/SIUPAL/IBC/MARPOL)는 Tanker Sector 상단 접기 박스로 이동.

## 9. 디자인 가이드

### 9.1 시각 위계
- KPI 메인 숫자: 36~48px
- 한 행에 차트 2개 이상 금지 (모바일 1개)
- 차트 간 여백 32px+

### 9.2 색상
- 베이스: dark navy `#1A3A6B` + sky blue `#56C0E0` + 회색조 3단계
- 양/음: 파랑/빨강
- Sector 5색: ColorBrewer Set2 또는 등가
- 신호등(녹/황/적) 금지

### 9.3 타이포
- Header: bold sans-serif
- Body: 16px 기본, 데스크톱 18px
- 한·영 혼용 line-height 1.6+

### 9.4 인터랙션
- Hover 툴팁 (사실 수치만)
- 클릭 → 탭 내 다른 위젯 연동 필터링
- 로딩: skeleton UI

### 9.5 모바일
- KPI 2×2
- 차트 풀폭 1개씩
- 지도 항로 Top 15로 자동 축소

## 10. 지도 재설계 상세

### 10.1 기술 스택
- 우선순위: 기존 Plotly 활용 (scattergeo + scatter 레이어 조합)
- 부담 시: D3 + TopoJSON CDN
- 라이브러리 추가 부담되면 SVG 직접 그리기

### 10.2 레이어
1. 베이스맵 (회색조, 행정구역 옅게)
2. 항구 원 (navy, 크기 ∝ ton, opacity 0.7)
3. 항로 곡선 (베지어, 두께 ∝ ton, 색상 = 카테고리)
4. 흐름 애니메이션 (파티클 origin→destination, 5초 루프)
5. 라벨 (Top 5만 상시, 나머지 hover)

### 10.3 인터랙션
- 항구 클릭 → 해당 항구 in/out 항로 하이라이트
- 항로 hover → 툴팁 (origin/dest/ton/vessels/category)
- 카테고리 토글 색상 필터

### 10.4 외국 항구
지도 우측 사이드바: 외국 항구 Top 10 가로 막대.

### 10.5 fallback
지도 라이브러리 로드 실패 시 정적 SVG 이미지 또는 표.

## 11. 데이터 단순화 (derived 재구성)

```
docs/derived/
  meta.json              # 데이터 신선도 (유지)
  home_kpi.json          # Home KPI 4
  map_flow.json          # 지도용 (항구 + Top 30 항로 + 외국항구 Top 10)
  timeseries.json        # 24M sector stacked
  tanker_subclass.json   # subclass 6 카드 + 추이
  tanker_top.json        # Top 10 코모디티 + Top 15 운영사
  cargo_fleet.json       # 트리맵 + 선령 분포 + class 도넛
  operators.json         # 상장사 KPI + 산점도 + 표
  owner_ticker_map.json  # 운영사-티커 매핑 (유지)
  regulatory_notes.html  # 규제 박스 (유지)
```

기존 항만 상세·결측 키 derived 파일은 **삭제** (있으면).

## 12. 작업 순서 (병렬 4개 PR)

| PR | 브랜치 | 산출물 | 의존성 |
|---|---|---|---|
| **PR-1: Cleanup** | `feat/cleanup` | 위젯 삭제, 탭 통합, derived JSON 정리 | 없음 |
| **PR-2: New Map** | `feat/new-map` | 지도 재설계 (애니메이션 + 컨트롤) | PR-1 |
| **PR-3: Home & Cards** | `feat/home-cards` | Home KPI 4 + 시계열 + Subclass 카드 | PR-1 |
| **PR-4: Visual Polish** | `feat/visual-polish` | 트리맵·도넛·가로막대·디자인 폴리싱 | PR-2, PR-3 |

## 13. 검증 체크리스트

- [ ] 탭 5개 (Home / Tanker Sector / Cargo & Fleet / Listed Operators / About)
- [ ] 위젯 18개 이하
- [ ] 항만 상세 위젯 제거
- [ ] 운영성 필터 제거
- [ ] 선박 목록 14컬럼 표 제거
- [ ] Changes / Trends 탭 제거
- [ ] 지도 흐름 애니메이션 동작
- [ ] 지도 컨트롤 3개
- [ ] Home KPI 36px+
- [ ] 한 행 차트 2개 이하
- [ ] 모바일 1열 풀폭
- [ ] 출처 라벨 모든 위젯
- [ ] 면책 푸터 (인쇄 포함)
- [ ] 블랙리스트 lint 0건

## 14. 시작 명령

```
1. PR-1 (feat/cleanup): §3 삭제 목록대로 위젯·필터·표·derived JSON 제거. 탭 8→5 통합.
2. PR-2 (feat/new-map): §10에 따라 지도 재설계, 흐름 애니메이션 + 3-토글 컨트롤.
3. PR-3 (feat/home-cards): Home KPI 4 + 시계열 + Subclass 카드 6 + 가로 막대 + 도넛.
4. PR-4 (feat/visual-polish): 트리맵·도넛 + 디자인 가이드 + 모바일 반응형.
```
