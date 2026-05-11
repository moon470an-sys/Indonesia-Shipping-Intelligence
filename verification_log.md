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
