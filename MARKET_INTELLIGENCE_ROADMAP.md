# Market Intelligence 전환 로드맵 — PDF 의존 → 웹 검색 기반

> **목적**: 현재 SBS Weekly Report(비공개 PDF)에 의존해 작성된 Market 탭
> (`docs/data/market.json`)을, 공개 웹 + 인도네시아 로컬 SNS·중개망 검색 기반의
> 자립적 market intelligence 로 단계적으로 전환한다.
>
> **운영 방식**: `/loop` dynamic mode 로 무한 반복. 깨우기마다 **이 파일을 읽고
> 다음 미완료 iteration 1개를 수행** → `market.json` 보강 → lint → commit/push →
> 아래 진행표 갱신 → 다음 깨우기 예약. `Stop` 지시가 있을 때까지 계속한다.
>
> **준수 절차서**: `MARKET_REFRESH_PLAYBOOK.md` §2(출처 규칙)·§3(섹션 절차)·
> §4(스키마)·§6(검증·커밋)을 그대로 따른다. **추정 금지·출처 필수·가치 판단 금지.**

---

## 핵심 원칙 (로드맵 iteration 전용)

1. **§1.3 7일 가드는 로드맵 iteration 에 적용하지 않는다.** §1.3 은 *주간 스냅샷
   중복 실행* 방지용이다. 로드맵 iteration 은 주간 스냅샷 갱신이 아니라 *출처
   보강·구조 전환* 작업이므로 7일 가드 무관하게 진행한다.
2. **메타 필드(`checked_date`/`report_week`/`build_run_id`)는 로드맵 iteration
   에서 건드리지 않는다.** 이 필드들은 주간 `/market-refresh` 스냅샷의 소유다.
   로드맵 iteration 은 `sources[]` 추가·`status` 상향·신규 행 추가만 한다.
   단 `build_meta.collectors_run` 에 `"roadmap_iter"` 1회 추가는 허용.
3. **PDF 출처 행을 삭제하지 않는다.** 웹/SNS 출처를 `sources[]` 에 *추가*하고
   2-source 충족 시 `status` 를 `verified` 로 올린다 (플레이북 §3-C).
4. **iteration 당 1개 타깃**만. 변경이 없으면 commit 하지 않고 진행표만 갱신.
5. 매 iteration 끝에 이 파일의 진행표 + "마지막 실행 로그"를 갱신해 commit 에 포함.

---

## 진행표

| # | 타깃 | 단계 | 상태 | 마지막 실행 | 비고 |
|---|------|------|------|-------------|------|
| 1 | `domestic_vessel_pricing` — Tug & Barge (Domestic Coal/General) 웹·SNS 보강 | Phase 1 | ✅ done | 2026-05-14 | kapal.co.id 매물·용선 페이지로 SHB 300ft 2-source 보강 + 230ft·180ft 행 추가, 웹 cross-check 5행 재판독 |
| 2 | `domestic_vessel_pricing` — CPO Market (Tug & Oil Barge / SPOB) 웹·SNS 보강 | Phase 1 | ⬜ todo | — | "jual SPOB", "oil barge charter" |
| 3 | `domestic_vessel_pricing` — Oil Tanker (Domestic) 웹·SNS 보강 | Phase 1 | ⬜ todo | — | "jual kapal tanker bekas" |
| 4 | `domestic_vessel_pricing` — LCT (Landing Craft Tank) 웹·SNS 보강 | Phase 1 | ⬜ todo | — | "jual/charter LCT" |
| 5 | `domestic_fuel_scrap` — solar B40 / HFO 180 (PDF 동결값 대체) | Phase 2 | ⬜ todo | — | Pertamina Patra Niaga 산업용 고시가 |
| 6 | `domestic_fuel_scrap` — scrap_domestic (Kelas A/B/C) 웹 보강 | Phase 2 | ⬜ todo | — | 인니 고철 시세 보도 |
| 7 | `international_freight.indices` — 지수 확장 + 변화율(WoW/1M/3M) 채우기 | Phase 2 | ⬜ todo | — | 이미 웹 기반, 깊이 보강 |
| 8 | `international_freight.scrap_*` / `sale_purchase` — S&P 실거래 사례 확보 | Phase 2 | ⬜ todo | — | GMS/Allied 주간, "No data acquired" 해소 |
| 9 | `commodity_news` + `overview` — 토픽별 최신 보도 심화 | Phase 2 | ⬜ todo | — | coal/nickel/cpo/power/shipping |
| 10 | `events` — 인니 해운·석탄·CPO 컨퍼런스 일정 검증·확장 | Phase 2 | ⬜ todo | — | INAMARINE/ICEE/PALMEX 등 |
| 11 | 구조 — "출처 구성 / PDF 의존도" 커버리지 지표 추가 | Phase 3 | ⬜ todo | — | meta 필드 + Vessel Pricing 섹션 소형 UI |
| 12 | 구조 — Market 탭에 "웹/SNS 출처 vs PDF" 범례·필터 노출 | Phase 3 | ⬜ todo | — | 기존 tier 필터 확장 |

### Phase 4 — 유지 모드 (12번 완료 후 무한 순환)

12번까지 끝나면 iteration 은 **유지 모드**로 전환: 매 깨우기마다 `sources[]` 의
가장 오래된(`as_of`/`url` 기준 stale) 섹션 1개를 골라 재검색·재검증한다. PDF 단독
출처로 남은 행을 우선 타깃. 이 단계부터 사실상 무한 루프.

---

## 마지막 실행 로그

### iter 1 — 2026-05-14 — Tug & Barge (Domestic Coal/General)
- **출처**: kapal.co.id 2개 페이지 (용선 호가 2025-06-13 / 매물 호가 2025-03-11), tier=media
- **SHB 카테고리**: `300ft various` 행에 kapal.co.id 매물 호가를 2nd source 로 추가
  (2-source 충족, 단 SBS 상단 35,000 vs 웹 상단 45,000 가 15% 초과 → status indicative 유지).
  신규 행 `230ft (set)` 14,000–20,000 추가 (웹 단독).
- **Web Cross-Check 카테고리**: 출처 페이지 재판독으로 270ft 655→655–670,
  300ft 825→770–900, 330ft 925→965 갱신. 신규 행 180ft(215–235)·230ft(420) 추가.
- **No data acquired / withheld_jump**: 없음. SBS TC 분기평균 카테고리는 §3-C 에 따라
  listing 호가와 직접 비교 불가하므로 미변경.
- **검증**: JSON 유효 · `lint_language.py` 0건 통과. build_meta 행 수 88 로 동기화.
- **다음**: iter 2 — CPO Market (Tug & Oil Barge / SPOB).
