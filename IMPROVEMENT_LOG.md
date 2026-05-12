# Improvement Log

본 사이트(Indonesia Shipping Intelligence)를 Cargo × Fleet 수급 시계열
분석에 집중하도록 재구성하는 무한 사이클의 누적 기록.

각 사이클은 **재검증 → 업그레이드 → 커밋**의 순서를 따른다. 사용자가
명시적 Stop을 지시하기 전까지 자체 종료 없이 다음 사이클로 진입한다.

## Cycle 1 — 2026-05-11

**Scope**: 4탭 골격 + cargo scope 분류 도입.

### 변경 사항

1. **docs/cargo_scope_definition.md** — 신규.
   화물선 / Cargo 보조선(Tug) / 제외 / 분류 미정 4분류 규칙을
   명문화. Livestock Carrier를 FISHING → cargo로 재분류. AHTS·PSV·
   Crew Boat는 excluded (Tug만 auxiliary). 분류 함수의 단일 진실 원천.

2. **backend/cargo_scope.py** — 신규.
   `cargo_scope(label, sector, vessel_class, lk3_ton)` 함수 구현.
   `taxonomy.classify_vessel_type` 결과를 입력으로 받아
   `(scope, ui_class)` 튜플 반환. 라이브 DB 92,021척 검증 — cargo
   29,574 / auxiliary 11,561 / excluded 50,580 / unclassified 92 (0.1%).

3. **scripts/build_derived.py** — 수정.
   `build_fleet_vessels` 가 18번째 컬럼으로 `scope` 추가 (schema_version
   5). `totals.by_scope` 집계 + `scope_audit.json` 빌더 추가.
   기존 JSON 컬럼 순서·이름 유지 → 호환성 유지.

4. **docs/index.html** — 수정.
   nav 탭 5→4 재편: Demand / Supply / Balance / Explorer.
   Listed Operators 탭은 nav에서 제거 (DOM은 보존하여 deep-link 호환).
   각 탭 헤더 아래에 scope meta-strip 추가 (화물선 n / 보조선 k / 제외 m /
   분류 미정 u). Explorer 탭 패널 신규 추가 (Cycle 2-3에서 위젯 채움).

5. **docs/js/app.js** — 수정.
   `state.scope` 캐시 + `populateScopeStrips()` 추가. `scopeState.hideExcluded`
   전역 플래그 도입 — `_applyFleetFilters` 가 excluded·unclassified 행을
   기본 숨김. Supply 탭 "제외 선종도 표시" 토글 wiring.
   Explorer 탭 placeholder 렌더러 추가. TAB_TITLES 4탭 라벨 갱신.

6. **docs/css/site.css** — 수정.
   `.scope-strip` + `.scope-chip` 색상 팔레트. cargo=navy, auxiliary=slate,
   excluded=stone, unclassified=red — backend.cargo_scope.SCOPE_PALETTE
   와 시각적 일치.

7. **IMPROVEMENT_LOG.md, verification_log.md** — 신규.
   사이클별 변경 이력 + 페이지별 재검증 결과 누적 기록.

### 검증 결과
- 92,021척 (snapshot 2026-05) cargo_scope 분류 일관성: unclassified
  0.1% (< 1% 임계 통과).
- fleet_vessels.json schema_version 5 빌드 성공.
- scope_audit.json 정상 생성.
- app.js 구문 체크 통과 (node --check).

### 알려진 미해결 / 다음 사이클 후보

- [ ] Cycle 2 — Demand 탭에 Cargo 항만 인포그래픽 통합 (현재 tab-cargo
  panel은 DOM만 보존). 흐름 지도에 시계열 슬라이더 추가.
- [ ] Cycle 2 — Supply 탭 Vessel Type 카운트 라벨에 scope 배지 (Tug
  옆 "보조선" 라벨 명시).
- [ ] Cycle 2 — Explorer 항로 테이블 / 항구 톤수 / 코모디티 raw 위젯
  구현.
- [ ] Cycle 3 — Balance 탭에 톤/GT 비율 시계열 + 신규 항로 lag 분석.
- [ ] Cycle 3 — Demand 탭 시계열 차트가 cargo+auxiliary 만 집계
  (현재는 LK3 전체 톤). cargo-scope 필터 적용.
- [ ] Cycle 4 — URL 파라미터 필터 공유 / 프리셋 저장.
- [ ] Cycle 4 — 시계열 윈도우 24개월 → 36개월 확장 가능성 점검.

---

## Cycle 2 — 2026-05-11 (사용자 Stop 지시로 중도 종료)

**Scope**: Demand·Supply·Explorer 강화. Cycle 2-1, 2-2, 2-3 완료
후 commit 직전 Stop. 2-4 (commit + 로그) 본 entry 작성으로 완료.

### 변경 사항

1. **Demand 탭에 Cargo 항만 인포그래픽 통합** (C2-1)
   - tab-cargo 의 cv-app 전체 (헤더 + commodity 패널 + Leaflet 지도 +
     항만 순위 사이드바)를 tab-overview (Demand) 하단으로 이관.
   - CSS 셀렉터 `#tab-cargo .cv-*` → `.cv-*` 로 un-scope (74곳). cv-*
     클래스는 본 위젯 외 사용처 없어 leakage 위험 0.
   - 기존 tab-cargo 패널은 deep-link 호환용 안내 카드로 축소
     (`<button data-jump-tab="overview">` 으로 Demand 로 이동).
   - `boot()` 에 전역 `[data-jump-tab]` 클릭 핸들러 추가.
   - `ensureLoaded("overview")` 가 `renderCargo()` 를 호출하도록 변경
     — Demand 진입 시 인포그래픽 자동 활성.

2. **Supply 탭 Vessel Type 리스트에 scope 배지** (C2-2)
   - `_renderFleetJenisList` 가 각 jenis 행에 1글자 scope 배지를 표시:
     auxiliary = "보조" / excluded = "제외" / unclassified = "미정".
     scope=cargo 는 무배지 (기본).
   - excluded 행은 `hideExcluded=true` 일 때 opacity 50% 로 muted.
   - fleet_vessels.json totals.by_jenis 의 `scope` 메타 활용
     (build_derived 가 Cycle 1 에서 추가).

3. **Explorer 항로 테이블 + 항구 raw 위젯 + 자동 인사이트** (C2-3)
   - `map_flow.json` 의 routes_top30 → 정렬·검색 가능한 30행 항로
     테이블 (Origin / Destination / Category / Ton 24M / Calls /
     Vessels). 헤더 클릭 정렬, 텍스트 검색 (origin·destination·
     category 매치).
   - `map_flow.json` 의 ports → 정렬·검색 가능한 60행 항구 톤수 표.
   - `map_flow.json` 의 insights → 자동 산출 사실 5건 리스트.
   - homeState.mapData 캐시 재활용 — Demand 렌더 후 Explorer 클릭 시
     중복 fetch 회피.

### 검증 결과
- node --check docs/js/app.js 통과.
- _esc / fmtTon / fmtCount 기존 헬퍼 재사용 → 신규 의존 0.
- Cycle 1 의 scope_audit / fleet_vessels schema v5 데이터 그대로 사용.

### 다음 사이클 후보 (Cycle 3 진입 시점)
- [ ] Demand 흐름 지도에 시계열 슬라이더 (월별 재생)
- [ ] Demand 시계열 차트에 cargo-scope 적용 (현재 LK3 전체 톤)
- [ ] Balance 탭을 전 sector 로 확장 — Container/Bulk/General 톤·GT 매칭
- [ ] Balance 톤/GT 비율 시계열 (가동 강도 대리지표)
- [ ] Supply 시계열 차트 (vessels_snapshot 다중 월 필요)
- [ ] Explorer 화물 품목 raw / 결측 키 추적 / 변경 이력 검색
- [ ] URL 파라미터 필터 공유

---

## Cycle 3 — 2026-05-12

**Scope**: 사용자 요청 4건 중 ①(선박 등록 KPI 삭제) + ②부분(d3 흐름
지도 삭제 — cv-app은 이미 통합됨) + ④(시계열 CARGO 카테고리화).
②의 기간 필터 추가, ③(cv-app 동그라미 → 흐름 라인 + 입자)는 데이터
빌더 보강이 필요해 Cycle 4 로 분리.

### 변경 사항

1. **KPI 카드 정비 (요청 ①)**
   - `tanker_fleet` 카드 (선박 등록 척수) → "국내 vs 국제 화물 비중"
     으로 대체. `map_flow.json.totals` 의 domestic_ton / intl_ton 으로
     합성. 24M 누계 기준 백분율 + 절대값 모두 표기.
   - `total_12m_ton` 라벨 "총 물동량 (인도네시아)" → "총 화물 물동량
     (LK3)" 로 변경. LK3 자체가 화물 데이터이지만 명시.
   - `tanker_12m_ton` 라벨 "탱커 물동량" → "탱커 화물 물동량".
   - `data_freshness` 서브라벨에 "LK3" 명시.

2. **d3 흐름 지도 블록 제거 (요청 ②부분)**
   - `#home-map-svg`, 카테고리/기간/트래픽 필터, 우측 사이드바 (sector
     비중 + 국제 항로 + 자동 요약) 통째 삭제.
   - `<script src=".../d3@7">`, `<script src=".../topojson-client@3">`
     CDN 의존성 제거. 페이지 로드 가벼워짐.
   - `renderHome()` 단순화: drawHomeMap / fillSectorStrip /
     fillForeignSidebar / fillMapInsights / _injectHomeMapYearButtons /
     bindMapControls / _refreshHomeMapPeriodLabel / fetch(TOPO_URL) 모두
     제거. 함수 정의는 보존 (호출되지 않음 — Cycle 4에서 정리 가능).
   - `homeState.mapData` 는 cv-app 라우트 오버레이용으로 유지.

3. **home-timeseries: CARGO 카테고리별 stacked area (요청 ④)**
   - 데이터 소스 변경: `timeseries.json` (sector 시리즈) →
     `cargo_sector_monthly.json` (CARGO sector × vessel_class × period +
     tanker subclass × period). PASSENGER/FISHING 등 비화물 sector 제거.
   - `_buildCargoCategorySeries(cm)` — Tanker vessel_class 행은 제거하고
     tanker_subclass_rows로 대체해 더 세분화 (Crude/Product/Chemical/
     LPG/LNG/FAME/Water/UNKNOWN). 비탱커는 Container/Bulk Carrier/
     General Cargo/Other Cargo.
   - `CARGO_CATEGORY_PALETTE` 11개 색상. Tanker subclass는 기존
     SUBCLASS_PALETTE와 일치 유지.
   - 차트 헤더 변경: "전체 물동량 24개월 추이 (sector stacked)" →
     "화물(Cargo) 물동량 24개월 추이 — 카테고리별 stacked". 하단에
     포함 카테고리 명시 + 제외 sector 명시.
   - 누계 검증: 24M 합 5.85B 톤. 분해 결과 — Other 2.3B, Bulk 2.0B,
     Product 0.55B, Container 0.49B, General 0.29B, Chemical 0.12B,
     LPG 0.06B, LNG 0.04B, FAME 0.01B.

### 검증 결과
- node --check docs/js/app.js 통과.
- 카테고리 합산 검증 — 24M total 5.85B tons (LK3 CARGO 한정).
- d3/topojson CDN 제거로 외부 의존 -2개.

### 다음 사이클 (Cycle 4)
- 사용자 요청 ②기간 필터 + ③흐름 라인/입자/동그라미 제거
- cv-app 에 기간(24M/12M/연도별) 필터 — `build_derived.py` 에
  `cargo_ports_periods.json` 빌더 추가 필요 (port × commodity ×
  period). 기존 cargo_ports.json 은 24M 누계만 있음.
- cv-app 항만 동그라미 마커 → O→D polyline + Canvas/SVG 입자 애니메이션.
  map_flow.json 의 routes_top30 (24M only) → 기간별 routes 확장 필요.

## Cycle 4 — 2026-05-12

**Scope**: 사용자 요청 ② (기간별 필터) + ③ (동그라미 제거, 흐름 라인 +
입자 애니메이션) 처리. Cargo flows 기간 확장은 차후 미루고 routes_top30
(24M)을 흐름 라인 데이터로 재사용.

### 변경 사항

1. **빌더 신규: `build_cargo_ports_periods` (요청 ②)**
   - cargo_snapshot 을 (data_year, data_month) 별로 GROUP BY 한 뒤
     Python 측에서 period 버킷(24m / 12m / 각 calendar year) 으로 binning.
   - 출력 schema (per-period):
     `{ label, months, month_list, commodities, ports }` — ports 의
     내부 구조는 기존 cargo_ports.json 과 동일하여 cv-app 렌더 함수
     재사용 가능.
   - bucket 분류기 + port 좌표 lookup 은 기존 `build_cargo_ports` 와
     공유. 코드 중복 일부 있으나 향후 리팩터 가능.
   - cargo_flows_periods 빌더는 보류 — 흐름 라인 데이터는 기존
     map_flow.routes_top30 (24M) 을 재사용. 입자가 항로 구조를
     보여주는 게 목적이라 기간별 정확성 < 시각적 일관성.

2. **cv-app 기간 필터 UI**
   - cv-app 헤더 우측에 `#cv-period-pills` 추가 — 24M / 12M / 2024 /
     2025 / 2026 버튼. 클릭 시 `_cvState.period` 갱신 + `_cvState.DATA`
     swap + 선택 코모디티 set 정리(새 기간의 commodity 목록과 교집합).
   - `_cvState.PERIODS` 에 모든 period 객체 캐시. fetch 1회.

3. **항만 동그라미 → 흐름 입자 (요청 ③)**
   - `_cvRenderCircles` 변경: 톤 비례 가변 마커(반경 4~70px) →
     **고정 3.5px 작은 점**. 클릭 타겟 + 위치 표시 역할만.
   - `_cvRenderLines` 변경: opacity 0.55 → 0.22 (흐름 라인은 입자의
     "트랙" 배경 역할). 라인 두께는 톤 비례 유지.
   - **신규: Canvas 오버레이 입자 애니메이션** (`_cvStartFlowAnimation`).
     - Leaflet map container 위에 `<canvas class="cv-flow-canvas">`
       오버레이. pointer-events:none 으로 Leaflet 인터랙션 통과.
     - 각 항로(routes_top30, 24M)에 3개씩 입자 분포. t=[0,1] 파라미터
       로 직선 보간. 속도 _CV_FLOW_SPEED (≈ 한 항로 2.2초 통과).
     - 입자: 카테고리 색 점 + 후행 그라데이션 트레일 + 흰색 하이라이트.
     - 크기 ∝ √(ton/maxTon) — 큰 항로는 더 큰 입자.
     - `map.on('resize zoom move')` 에서 canvas size 재계산. 입자
       위치는 매 프레임 latLngToContainerPoint 재호출이라 별도 처리
       불필요.

### 다음 사이클 후보 (Cycle 6+)
- [ ] cargo_flows_periods 빌더 — 기간별 정확한 O→D 데이터
- [ ] document.hidden 시 flow animation 일시정지 (battery 절약)
- [ ] 입자도 선택 화물에 따라 표시/숨김 (현재는 모든 항로 입자 동시 흐름)
- [ ] Balance 탭 전 sector 확장 (Container/Bulk/General 톤·GT 매칭)
- [ ] Supply 시계열 (vessels_snapshot 다중 월)

## Cycle 5 — 2026-05-12

**Scope**: 사용자 추가 요청 5건 처리 (시계열 stacked area→stacked bar,
scope-strip 제거, 카테고리 드롭다운, 선택 화물 한정 tooltip, 곡선 라우트).

### 변경 사항

1. **Demand 탭 scope-strip 제거 (요청 ①)**
   - `#scope-meta-strip` HTML 제거 (Demand 한정). populateScopeStrips
     에서 scope-n-* keys 누락. 다른 탭(Supply/Balance/Explorer)의 strip
     은 유지.

2. **시계열 stacked area → 월별 stacked bar (요청 ②)**
   - `drawHomeTimeseries` trace type을 `scatter+stackgroup` →
     `bar+barmode=stack`. `xaxis.type="category"`, `bargap=0.18`.
   - 절대값 고정 — `renderHomeTimeseries` 에서 YoY 토글 wiring 제거,
     `home-ts-toggle` 컨테이너 제거.
   - y축 라벨 "ton (CARGO 카테고리 stacked)" 유지.

3. **카테고리 → 세부 화물 드롭다운 (요청 ③)**
   - cv-app 좌측 commodity 패널을 7개 카테고리 그룹 트리로 재구성:
     Crude/정제유 · Gas · Palm/식용유 · Dry Bulk · Container/General ·
     차량 · 기타. `CV_CATEGORY_GROUPS` 매핑.
   - 각 카테고리 헤더(이름 + 합계 + ▼/▶ 토글) 클릭 시 펼침/접힘.
     `_cvState.openCategories` Set 상태 보존. 선택된 코모디티가 있는
     카테고리는 자동 펼침.
   - 카테고리 내 코모디티는 톤 desc 정렬, 기존 체크박스 선택 동작 유지.
   - 신규 CSS — `.cv-cat-head`, `.cv-cat-caret`, `.cv-cat-dot`,
     `.cv-comm-row-nested`.

4. **항만·라우트 tooltip — 선택 화물 한정 (요청 ④)**
   - `_cvTooltip` 의 4셀(DOM 하역/선적, INTL 하역/선적)은 이미
     `_cvBuildPorts` 가 선택 코모디티 합산값을 넣어주므로 그대로 정확.
     footer 라벨을 "선택 화물 N종 합계" 로 명시.
   - `_cvRouteTooltip` 신규 `CV_COMM_TO_ROUTE_CAT` 매핑 — cv-app
     commodity (40개) → map_flow 카테고리 (8개). 선택 화물이 매핑되는
     카테고리만 category_ton 에서 필터해 표시. 매칭이 없으면 "선택
     화물과 매칭되는 카테고리 없음" 안내. footer total 도 필터 후 합산.

5. **라우트 곡선 (Quadratic Bezier) (요청 ⑤)**
   - 직선 `L.polyline([o, d])` → 33점 샘플링된 곡선 polyline.
   - `_cvComputeRouteCurve(r)` — 중간점 + perpendicular offset 18%
     으로 컨트롤 포인트. 시계방향 90° 회전으로 일관된 방향(항상 같은
     쪽으로 휨). 결과를 `r._curve` 캐시.
   - `_cvBezierAt(r, t)` — 입자 애니메이션에서 매 프레임 같은
     베지어 공식으로 위치 계산. 트레일도 곡선 따라 보간.
   - STS 자기루프(origin==destination) 는 곡선 처리 없음 — 점선 동심원
     유지.

### 검증
- node --check docs/js/app.js 통과.
- CV_CATEGORY_GROUPS 7개 + CV_COMM_TO_ROUTE_CAT 약 30개 매핑 정의.
- 베지어 샘플 N=33, offset 0.18 — 적당히 휘면서 직관적 방향성 유지.

## Cycle 6 — 2026-05-12

**Scope**: 사용자 요청 4건 처리 (보조 문구 3건 정리 + 카테고리 상세 화물
박스 추가).

### 변경 사항

1. **시계열 차트 보조 문구 3건 삭제 (요청 ①②③)**
   - 제목 "— 카테고리별 stacked bar" 보조 텍스트 제거.
   - y축 라벨 "ton (CARGO 카테고리 stacked)" → "ton".
   - 차트 하단 카테고리 안내 단락(`<p>`) 통째 삭제.

2. **신규 빌더 build_cargo_category_details (요청 ④ 데이터)**
   - cargo_snapshot에서 (JENIS KAPAL, KOMODITI) 별 BONGKAR+MUAT 톤
     집계 → taxonomy로 카테고리(vessel_class + tanker subclass) 분류
     → 카테고리당 Top 12 KOMODITI 선정.
   - 출력 `docs/derived/cargo_category_details.json`:
     `{ order: [...], categories: { <cat>: { ton_total_24m, calls_total_24m,
     commodity_count, top_commodities: [{ name, ton_24m, pct, calls_24m }] } } }`.
   - CARGO sector 외 sector는 제외. order는 시계열 차트의 stack 순서와 일관.

3. **시계열 차트 오른쪽 카테고리 상세 화물 박스 (요청 ④ UI)**
   - 차트 컨테이너를 `grid lg:grid-cols-3`으로 분할: 좌 2/3 차트, 우 1/3
     상세 박스.
   - 우측 박스: 카테고리 드롭다운(`#cat-detail-select`) + 메타 라인
     (24M 누계 톤 / KOMODITI 수 / 항해 수) + Top 12 코모디티 리스트
     (순위, 이름, 톤, 미니 바, 비중·항해 수).
   - 미니 바 색상은 `CARGO_CATEGORY_PALETTE` 사용해 시계열 차트와 일관.
   - 기본 선택 = ton_total_24m 1위 카테고리.

### 검증
- node --check docs/js/app.js 통과.
- build_derived 실행 후 cargo_category_details.json 검증.
