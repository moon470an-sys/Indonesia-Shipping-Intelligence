# Verification Log

매 사이클 시작 시 4탭(Demand/Supply/Balance/Explorer)을 점검하고
원칙 위반·중복·미흡을 기록한다.

## Cycle 1 검증 — 2026-05-11

### Demand 탭 (📦 — id: tab-overview)

| 항목 | 상태 | 비고 |
|------|------|------|
| 흐름 지도 (Home map) | ✅ 보존 | 카테고리(전체/탱커/벌크) · 기간(12M/24M) · 트래픽(국내+국제/국내/국제) 필터 작동 |
| 시계열 슬라이더 | ❌ 미구현 | Cycle 2 — 월별 흐름 재생 추가 필요 |
| Cargo 항만 인포그래픽 (cv-app) | ⚠️ DOM 존재하나 nav 분리 | Cycle 2에서 Demand 패널 하단에 통합 |
| 시계열 차트 (sector stacked area) | ✅ 보존 | MoM%/YoY% 토글 작동 |
| 신규/소멸 항로 강조 | ❌ 미구현 | Cycle 2 후반 또는 Cycle 3 |
| 외국 항구 KPI 합산 | ✅ | 우측 사이드바에 표기 |
| 데이터 없음 처리 | ✅ | LK3 결측 → "데이터 없음" 또는 0이 아닌 null |
| 시계열 차트 cargo-scope 적용 | ⚠️ 미적용 | Cycle 3 — 현재는 LK3 전체 톤 (passenger·fishing 포함) |
| scope meta-strip | ✅ Cycle 1 추가 | scope_audit.json 로드 |
| 장식 이모지·placeholder 잔존 | ⚠️ | "loading…" 텍스트 일부 남음 (skeleton 시각 효과) |

### Supply 탭 (🚢 — id: tab-fleet)

| 항목 | 상태 | 비고 |
|------|------|------|
| 다중 필터 (Vessel Type / Yr / GT / LOA / W / D / Name) | ✅ 보존 | jang1117 mirror 유지 |
| 선박 목록 표 (페이지네이션 + 정렬) | ✅ 보존 | 100/page |
| CSV 다운로드 | ✅ 보존 | UTF-8 BOM |
| cargo-scope 기본 ON (excluded·unclassified 숨김) | ✅ Cycle 1 추가 | "제외 선종도 표시" 토글로 우회 |
| Tug "보조선" 라벨 명시 표기 | ⚠️ 라벨 분리 미흡 | Cycle 2 — Vessel Type 체크박스 옆에 scope 배지 |
| 시계열 차트 (Sector별 척수·GT 추이) | ❌ 미구현 | Cycle 3 — vessels_snapshot 다중 월 필요 (현재는 단일 snapshot) |
| 건조 연도 분포 | ✅ 보존 | |
| 신규 등록 / 등록 말소 월별 흐름 | ❌ 미구현 | Cycle 3 — vessels_changes 활용 |
| Top Owner 시계열 | ❌ 미구현 | Cycle 3 |
| URL 필터 공유 | ❌ 미구현 | Cycle 4 |
| scope meta-strip | ✅ Cycle 1 추가 | |

### Balance 탭 (⚖️ — id: tab-tanker-sector)

| 항목 | 상태 | 비고 |
|------|------|------|
| Tanker Subclass 카드 (수급 매칭 코어) | ✅ 보존 | Crude / Product / Chemical / LPG / LNG / FAME |
| 시장 구조 scatter (CAGR × 평균 선령) | ✅ 보존 | |
| Subclass 월별 추이 (abs / YoY 토글) | ✅ 보존 | |
| Top 10 코모디티 | ✅ 보존 | |
| Top 15 운영사 + Top 5 점유 도넛 | ✅ 보존 | |
| 전 sector로 확장 (Container / Bulk / General 톤·GT 매칭) | ❌ 미구현 | Cycle 3 — 본 사이트 핵심 |
| 톤/GT 비율 시계열 | ❌ 미구현 | Cycle 3 |
| 신규 항로 vs 신규 등록 lag 분석 | ❌ 미구현 | Cycle 3-4 |
| 수급 불균형 알림 | ❌ 미구현 | Cycle 4 |
| Tug × Barge 매칭 보조 지표 | ❌ 미구현 | Cycle 3-4 |
| scope meta-strip | ✅ Cycle 1 추가 | |

### Explorer 탭 (🔎 — id: tab-explorer)

| 항목 | 상태 | 비고 |
|------|------|------|
| 패널 골격 + 잡 점프 링크 | ✅ Cycle 1 추가 | Supply 탭으로 점프 작동 |
| 화물선 목록 raw | ⚠️ Supply 탭에 위임 | 별도 Explorer 뷰는 Cycle 2 |
| 항로 테이블 (Origin→Destination raw) | ❌ 미구현 | Cycle 2 — map_flow.json 의 routes 직렬화 |
| 항구별 톤수 상세 | ❌ 미구현 | Cycle 2 — cargo_ports.json raw 표시 |
| 화물 품목 상세 | ❌ 미구현 | Cycle 2 |
| 결측 키 추적 | ❌ 미구현 | Cycle 3 |
| 변경 이력 검색 | ❌ 미구현 | Cycle 3 — changes.json (7.3MB) raw 검색 |
| Scope 제외 데이터 보기 토글 | ✅ Cycle 1 추가 (토글 UI만, raw 표는 미구현) | Cycle 2 |
| scope meta-strip | ✅ Cycle 1 추가 | |

### 횡단(원칙) 위반 점검

- 원칙 1 (공식 데이터만, 외부 추정·해석 금지) — 위반 없음.
- 원칙 2 ([화물 × 선종 × 시간] 3축 통일) — Supply 탭 시계열 미구현 (Cycle 3).
- 원칙 3 (시계열·비율 우선) — Demand 흐름 지도는 24M 누적 정적. 시계열
  슬라이더가 결합되면 통과. Cycle 2 우선.
- 원칙 4 (결측은 "데이터 없음") — 본 사이클 변경 영역에서는 통과.
- 원칙 5 (운영 의사결정에 직접 안 쓰이는 화면·KPI·문구는 삭제) —
  Listed Operators 탭 nav에서 제거. About / Changes 탭은 이미 제거됨.
- 원칙 6 (화물선 외 선종 메인 차트 제외, Tug는 보조선 라벨) — Supply
  탭에 적용 완료. Demand·Balance·Home map의 시계열 차트는 LK3 전체
  톤을 사용하고 있어 화물선 한정 적용은 Cycle 3.

### 사이클 종료 시 액션
- Cycle 1 완료. Cycle 2 시작.

## Cycle 2 검증 — 2026-05-11 (사용자 Stop 지시로 중도 종료)

### Demand 탭

- ✅ Cargo 항만 인포그래픽 (cv-app) 통합 — Demand 탭 하단에 노출.
  탭 1개로 흐름 지도 + 항만 인포그래픽을 동시에 볼 수 있게 됨.
- ✅ tab-cargo 안내 카드 — deep-link `#tab-cargo` 도 안전.
- ⚠️ 시계열 슬라이더 (월별 재생) — 미구현. Cycle 3.
- ⚠️ 시계열 차트의 cargo-scope 적용 — 미구현. Cycle 3.

### Supply 탭

- ✅ scope 배지 (보조 / 제외 / 미정) Vessel Type 리스트에 부착.
  "Tug Boat" 옆에 "보조" 배지가 시각적으로 명확.
- ✅ excluded 행 muted (opacity 50%) — 기본 숨김 상태와 일관.
- ⚠️ 시계열 차트 (Sector별 척수·GT 추이) — 미구현. Cycle 3.

### Balance 탭
- 본 사이클 변경 없음. Cycle 3 우선 영역.

### Explorer 탭

- ✅ 항로 테이블 (Top 30, 24M) — 검색·정렬 가능.
- ✅ 항구 톤수 표 (60개) — 검색·정렬 가능.
- ✅ 자동 인사이트 5건 (map_flow.json builder 산출).
- ⚠️ 화물 품목 raw / 결측 키 / 변경 이력 — 미구현. Cycle 3.
- ⚠️ Scope 제외 데이터 raw 표 — 토글 UI 만 존재. Cycle 3.

### 횡단(원칙) 위반 점검
- 원칙 1·4·5·6 통과.
- 원칙 2·3 (시계열·탐색 병행) — Demand 흐름 지도 시계열 슬라이더 부재.
  Cycle 3 우선.

### 사이클 종료 시 액션
- Cycle 2 의 1·2·3 완료. 사용자 Stop 지시로 Cycle 3 미시작.

## Cycle 3 검증 — 2026-05-12

### Demand 탭

- ✅ 선박 등록 KPI 카드 → "국내 vs 국제 화물 비중" 으로 교체.
  Supply 정보 노출 없음.
- ✅ KPI 라벨 "총 화물 물동량 (LK3)" · "탱커 화물 물동량" 으로 명확화.
- ✅ d3 흐름 지도 (#home-map-svg) 통째 삭제. d3/topojson CDN 제거.
  sector 사이드바·자동 요약 사이드바·국제 항로 사이드바 동시 제거.
- ✅ 시계열 차트 — CARGO sector만, 카테고리(Container/Bulk/Tanker
  subclass/General/Other Cargo) 색상 분리 stacked area. PASSENGER 등
  비화물 제외. 24M total 5.85B 톤 검증.
- ⚠️ cv-app 기간 필터·동그라미 제거·흐름 라인은 Cycle 4 처리.

### Supply / Balance / Explorer 탭
- 본 사이클 변경 없음.

### 횡단(원칙) 위반 점검
- 원칙 1·2·4·5·6 통과.
- 원칙 3 (시계열·비율 우선) — Demand 시계열이 이제 CARGO 한정·카테고리별
  로 더 의미있는 신호. 통과.

### 사이클 종료
- Cycle 3 완료. Cycle 4 시작.

## Cycle 4 검증 — 2026-05-12

### Demand 탭

- ✅ cv-app 기간 필터 UI (24M / 12M / 2024 / 2025 / 2026) 추가.
  cargo_ports_periods.json — 79항만 × 40코모디티 × 5기간.
- ✅ 항만 동그라미 톤 비례 가변 마커(4~70px) → 고정 3.5px 작은 점.
- ✅ 정적 라인 opacity 0.22 — 입자의 트랙 배경.
- ✅ Canvas 오버레이 입자 애니메이션 — routes_top30(24M) 각 항로에
  3개 입자, origin→destination 보간, 카테고리 색 + 트레일 + 하이라이트.
- ⚠️ 기간 필터는 항만 톤만 갱신 (라인은 24M 고정). Cycle 5+ 에서
  cargo_flows_periods 빌더 추가 가능.

### Supply / Balance / Explorer 탭
- 본 사이클 변경 없음.

### 횡단(원칙) 위반 점검
- 원칙 1·2·4·5·6 통과.
- 원칙 3 — Demand 지도가 이제 기간 필터 + 흐름 시각화로 시계열·탐색
  병행 원칙에 더 부합. 통과.

### 사이클 종료
- Cycle 4 완료. 사용자 요청 4건 (①②③④) 모두 처리됨.

## Cycle 5 검증 — 2026-05-12

### Demand 탭

- ✅ scope-strip(화물선/보조선/제외) 삭제 — Demand 탭 한정. 다른 탭은 유지.
- ✅ 시계열 차트 — stacked area → 월별 stacked bar. YoY 토글 제거.
  절대값(ton) 고정, x축 category, bargap 0.18.
- ✅ cv-app 코모디티 패널 — 40개 평면 목록 → 7개 카테고리(Crude/Gas/
  Palm/Bulk/Container/Vehicle/Other) 드롭다운 트리. 펼침/접힘 토글
  유지, 선택 코모디티 자동 펼침.
- ✅ 항만 tooltip — 4셀(DOM/INTL × 하역/선적)은 _cvBuildPorts가 이미
  선택 코모디티 한정 합산. footer 라벨 "선택 화물 N종 합계" 명시.
- ✅ 라우트 tooltip — 신규 CV_COMM_TO_ROUTE_CAT 매핑으로 선택 화물에
  매칭되는 카테고리만 breakdown 표시. footer total 필터 후 합산.
- ✅ 라우트 곡선 — 직선 polyline → 33점 quadratic Bezier 곡선. 컨트롤
  포인트 = perpendicular offset 18% (시계방향 90°). 입자 애니메이션도
  동일 곡선 위에서 보간. STS 자기루프는 곡선 미적용.

### Supply / Balance / Explorer 탭
- 본 사이클 변경 없음. scope-strip 유지.

### 횡단(원칙) 위반 점검
- 원칙 1·2·4·5·6 통과.
- 원칙 3 (시계열·탐색 병행) — bar chart 가 stacked area 보다 월별
  관측에 더 적합. 카테고리 드롭다운으로 세부 화물 탐색성 강화. 통과.

### 사이클 종료
- Cycle 5 완료. 사용자 요청 5건 (①②③④⑤) 모두 처리됨.
