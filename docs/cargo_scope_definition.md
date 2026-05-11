# Cargo Scope Definition

본 사이트(Indonesia Shipping Intelligence)는 **상업용 화물 운송(Cargo
Shipping)** 의 수급 분석을 목적으로 한다. raw 데이터(vessels_snapshot,
LK3 cargo_snapshot)에는 모든 선종이 보존되지만, **표시 단계**에서는 본
문서의 분류 규칙에 따라 4분류 중 하나로 매핑하고, 메인 차트·KPI·필터·
지도에는 `cargo` + `auxiliary` 만 노출한다.

## 4-classes

| scope         | 의미                                  | 메인 차트 노출 |
| ------------- | ------------------------------------- | -------------- |
| `cargo`       | 상업용 화물선                          | ✅ 포함        |
| `auxiliary`   | 화물선 보조선 (Tug/Tugboat)            | ✅ 포함 (라벨 구분) |
| `excluded`    | 화물 운송과 무관한 선종 (Passenger·Fishing·Patrol·Yacht·Dredger 등) | ❌ 메인 차트 미표시 (Explorer 토글로만 접근) |
| `unclassified`| 분류 규칙으로 매핑 불가 + LK3 화물 운반 실적 없음 | ❌ 메인 차트 미표시, "분류 미정" 메타로 별도 집계 |

## 분류 규칙

분류는 `backend.taxonomy.classify_vessel_type(label)` 결과인
`(sector, vessel_class)` 튜플을 1차 키로 사용하고, 필요 시 raw 라벨
(`JenisDetailKet` / `JENIS KAPAL`) 키워드와 LK3 화물 운반 실적을
교차 검증한다. 분류 결과는 `backend.cargo_scope.cargo_scope()` 함수로
일원화한다.

### scope = `cargo`
- `sector == CARGO`, 즉 다음 `vessel_class`:
  - `Container` (Container Ship, Peti Kemas)
  - `Bulk Carrier` (Dry Bulk, Cement Carrier, OBO, Car Carrier, Wood Chip)
  - `Tanker` — subclass: Crude / Product / Chemical / LPG / LNG / FAME-Vegetable Oil / Water
    - SPOB (Self-Propelled Oil Barge), Oil Barge, Chemical Barge 포함
  - `General Cargo` (General Cargo, Multi-Purpose, Layar Motor)
  - `Other Cargo` — Barge / Tongkang / Pontoon / Landing Craft / LCT / Ro-Ro Cargo / Reefer / Heavy Lift / Project Cargo / MPV
- **Livestock Carrier (Ternak)**: 현재 `backend.taxonomy`는 FISHING으로
  분류하나 본 spec에서는 cargo (livestock = 가축 운반)로 재분류한다.
  `backend.cargo_scope` 단계에서 sector를 CARGO로 오버라이드.
- **Reefer / Refrigerated Cargo**: "REFRIGERATED FISH"·"FISH REEFER" 등
  *fish*가 명시된 경우만 excluded. 그 외 reefer (예: 일반 냉동화물)는
  cargo (Other Cargo).

### scope = `auxiliary`
- `vessel_class == Tug/OSV/AHTS` (= sector `OFFSHORE_SUPPORT`) 중
  **Tug / Tugboat / Tunda / Pusher** 계열만 auxiliary로 분류.
- AHTS / PSV / Supply / Crew Boat 등 *offshore platform* 지원선은
  본 spec의 "화물 운영의 보조선" 정의에서 벗어나므로 `excluded`.
  (석유 시추선 보조 — 해운 화물 운송이 아닌 OSV 시장)
- auxiliary는 메인 sector·class 집계에 **포함**하되, 차트 라벨에서
  "Cargo 보조선" 으로 명시 표기.
- 주력 공급 지표(예: Tanker GT, Bulk GT)에는 합산하지 **않음**.
- Barge·Tanker 보조 운영 분석 (예: Barge GT 대비 Tug 척수)에서만
  공급 변수로 사용.

### scope = `excluded`
- `sector in {PASSENGER, FISHING, NON_COMMERCIAL}` 전체
- `vessel_class == Dredger/Special` (Dredger 단독 — 항만 인프라 작업)
- `vessel_class == Tug/OSV/AHTS` 중 Tug 계열이 아닌 것 (AHTS·PSV·
  Supply·Crew Boat 등 OSV)
- Pilot / Mooring / Patrol / Coast Guard / Navy / Yacht /
  Research / Survey / SAR / Rescue / Pleasure / Training

### scope = `unclassified`
- `sector == UNMAPPED` 이고 LK3 화물 운반 실적이 0 인 선박.
- `sector == UNMAPPED` 이면서 LK3 화물 운반 실적이 있는 선박은
  scope = `cargo` 로 승격하되 vessel_class = `Other Cargo`,
  meta `_promoted_from_unmapped = true` 로 표기.

## Tier-3 라벨 (UI 표시용)

`auxiliary`는 메인 차트에서 별도 색·라벨로 구분되어야 한다. UI 라벨:

- `cargo` → vessel_class 그대로 표시 (Container / Bulk Carrier /
  Tanker / General Cargo / Other Cargo)
- `auxiliary` → "Cargo 보조선 (Tug)" 단일 라벨
- `excluded` → 메인 차트 미표시
- `unclassified` → "분류 미정" (Explorer 메타에만)

## KPI 메타 표기

모든 4탭 (Demand/Supply/Balance/Explorer) 상단의 결과 카운트 칩은
다음 포맷을 따른다:

> 화물선 **{cargo_n}**척 / 보조선 **{aux_n}**척 / 제외 {excluded_n}척
> (분류 미정 {unclassified_n}척)

## 정합성 점검 (사이클마다)

1. `backend/cargo_scope.py` 의 분류 함수 결과를 vessels_snapshot 전체에
   대해 집계해서 `docs/derived/scope_audit.json` 으로 출력.
2. `unclassified` 비율 > 1% 이면 verification_log.md 에 경고 기록.
3. `excluded` 비율 변동 (직전 사이클 대비 ±0.5% 초과) 시 라벨 변경
   가능성 점검.
4. LK3 화물 운반 실적이 있는데 scope == excluded 인 선박이 5척 이상
   발견되면 분류 규칙 검토 후 본 문서 업데이트.

## 변경 이력
- 2026-05-11 (Cycle 1) — 초안. taxonomy `FISHING/Livestock` → `cargo`
  로 재분류. OSV(AHTS·PSV·Supply·Crew Boat)는 excluded.
