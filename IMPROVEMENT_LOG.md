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
