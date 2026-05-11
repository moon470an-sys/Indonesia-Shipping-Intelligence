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

(다음 사이클 진입 시 본 섹션 아래에 Cycle 2 entry 추가.)
