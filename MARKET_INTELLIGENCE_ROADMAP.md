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
| 2 | `domestic_vessel_pricing` — CPO Market (Tug & Oil Barge / SPOB) 웹·SNS 보강 | Phase 1 | ✅ done | 2026-05-14 | BSI Vessel SPOB 매물 2행 추가. SPOB/oil barge 매물 多이나 가격 미표기 — 추가 검색 필요 |
| 3 | `domestic_vessel_pricing` — Oil Tanker (Domestic) 웹·SNS 보강 | Phase 1 | ✅ done | 2026-05-14 | kapal.co.id 매물 3행 추가 (376KL·500KL·3200DWT). TC 호가는 너무 broad — 미반영 |
| 4 | `domestic_vessel_pricing` — LCT (Landing Craft Tank) 웹·SNS 보강 | Phase 1 | ✅ done | 2026-05-14 | kapal.co.id LCT 용선료 6행 → Web Cross-Check 마켓에 신규 카테고리. PDF LCT TC 와 큰 격차 발견 |
| 5 | `domestic_fuel_scrap` — solar B40 / HFO 180 (PDF 동결값 대체) | Phase 2 | ✅ done | 2026-05-14 | solarindustri.com B40·MFO 실가격으로 PDF 동결값 교체, solar 2→3행 |
| 6 | `domestic_fuel_scrap` — scrap_domestic (Kelas A/B/C) 웹 보강 | Phase 2 | ✅ done | 2026-05-14 | digitaleksplorasi.com 이 PDF Kelas A/B/C 값 정확히 확인 → 웹 출처로 교체 |
| 7 | `international_freight.indices` — 지수 확장 + 변화율(WoW/1M/3M) 채우기 | Phase 2 | ✅ done | 2026-05-14 | BDI/BCI/BPI 2026-05-14 최신값 + wow_pct 보강. BSI·5TC 는 신규 데이터 없어 동결 |
| 8 | `international_freight.scrap_*` / `sale_purchase` — S&P 실거래 사례 확보 | Phase 2 | ✅ done | 2026-05-14 | S&P "No data acquired" → Capesize Bulk Joyance $33M 실거래. 스크랩 LDT는 GMS W14가 기존값 확인 |
| 9 | `commodity_news` + `overview` — 토픽별 최신 보도 심화 | Phase 2 | ✅ done | 2026-05-14 | CPO 뉴스 2건 추가(수출 기준가·KPBN), overview[0] BDI 3,189 동기화 |
| 10 | `events` — 인니 해운·석탄·CPO 컨퍼런스 일정 검증·확장 | Phase 2 | ✅ done | 2026-05-14 | ICEE 종료 제거, Mining Indonesia 신규, INAMARINE PDF→웹 출처 |
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

### iter 2 — 2026-05-14 — CPO Market (Tug & Oil Barge / SPOB)
- **출처**: BSI Vessel (bsivessel.com) SPOB 매물 페이지, tier=broker.
- **2nd SPOB — SHB Price** 카테고리: 신규 행 `200KL (2003)` 3,000 · `300KL (2016)` 3,700
  추가 (BSI Vessel 중개 호가, IDR 3.0B·3.7B). **listing 시점이 2023-05 로 stale** 하므로
  source_name·note 에 시점을 명시하고 status indicative.
- **미확보**: SPOB/oil barge **charter rate**, NB SPOB **galangan 가격**,
  kapal.co.id 의 oil barge/SPOB 매물(capacity 만 표기, 가격 미표기) — 모두 값 미입력.
  Ratson 등 galangan 은 capacity 라인업만 공개, 단가 비공개. → §3-C 추정 금지로 행 미추가.
- **검증**: JSON 유효 · `lint_language.py` 0건 통과. build_meta 90 행 동기화.
- **다음**: iter 3 — Oil Tanker (Domestic). kapal.co.id 에서 Mini Tanker 376KL·500KL,
  Tanker 3200DWT 매물 호가 이미 확인 — iter 3 에서 반영 예정.

### iter 3 — 2026-05-14 — Oil Tanker (Domestic)
- **출처**: kapal.co.id 매물 페이지 (2025-03-11), tier=media.
- **2nd Oil Tanker — SHB Price** 카테고리: 신규 행 3개 — `376KL Mini Tanker (2006)` 3,000 ·
  `500KL Mini Tanker` 5,500 · `3200 DWT (2006)` 30,000. PDF 단독이던 카테고리에 첫 웹 출처.
- **미반영**: 도메스틱 오일탱커 time charter 호가는 "Rp 1–3 miliar/월" 식 broad range
  뿐 — size 별 분해 불가, §2 추정 금지로 미입력. NB Oil Tanker 는 여전히 No data acquired.
- **검증**: JSON 유효 · `lint_language.py` 0건 통과. build_meta 93 행 동기화.
- **다음**: iter 4 — LCT (Landing Craft Tank).

### iter 4 — 2026-05-14 — LCT (Landing Craft Tank)
- **출처**: kapal.co.id "Sewa Kapal LCT Indonesia" (2025-03-10), tier=media.
- **Domestic Charter Rates — Web Cross-Check** 마켓에 신규 카테고리
  `LCT TC — Web Listing (kapal.co.id)` 추가 — LCT 500~2000 DWT 6행 (월 80~350 millions IDR).
- **⚠ 발견**: PDF `LCT — Time Charter` 행(smaller 1,100 / larger 1,200)과 웹 호가
  (80~350)가 10배 이상 격차. 단위·선급 기준 차이 의심 — **iter 11/유지모드에서 PDF
  LCT TC 행의 단위 정합성 재검증 필요**. §3-C 에 따라 PDF 행은 미변경.
- **미확보**: LCT 매물(SHB) 가격 — indonetwork/OLX 매물 多이나 가격 미표기.
- **검증**: JSON 유효 · `lint_language.py` 0건 통과. build_meta 99 행 동기화.
- **다음**: iter 5 — domestic_fuel_scrap (solar B40 / HFO 180).

### iter 5 — 2026-05-14 — domestic_fuel_scrap (solar B40 / HFO 180)
- **출처**: solarindustri.com "Harga Solar Industri B40 & MFO 15–31 Mar 2026" (upd 2026-03-24),
  tier=media. 보조 확인: bbmindustri.com (1–14 Mar 2026).
- **solar_b40_hsd**: PDF p.1 동결값(22,000 / 22,500)을 웹 출처로 **교체**. B40 Wilayah I+II
  23,050 · Wilayah III 23,150 · Wilayah IV 23,300 (excl. PPn/PPH/PBBKB — PDF 와 동일 면세 기준).
  기존 'III+IV avg' 행을 지역별 실값으로 분리해 2→3행.
- **hfo_180_mfo**: PDF p.1 동결값(14,500)을 solarindustri.com MFO 16,850 (all regions)으로 교체.
  bbmindustri 의 등급별 구분(Low Sulphur 15,450 / HS 180 13,500–13,850)은 note 에 병기.
- **검증**: JSON 유효 · `lint_language.py` 0건 통과. build_meta fuel_scrap 9 행 동기화.
- **남은 PDF 의존**: domestic_fuel_scrap 에서 PDF 단독은 이제 scrap_domestic(Kelas A/B/C)만.
- **다음**: iter 6 — scrap_domestic (Kelas A/B/C) 웹 보강.

### iter 6 — 2026-05-14 — scrap_domestic (Kelas A/B/C)
- **출처**: digitaleksplorasi.com "Harga Besi Bekas 2026" (article 2026-03-01), tier=media.
  steelindonesia.com scrap-price 페이지는 403 으로 미접근.
- **결과**: 웹 출처가 PDF p.1 값을 **정확히 확인** — Kelas A 5,600 동일, Kelas B 5,425 는
  웹 range 5,350–5,500 중앙값, Kelas C 4,700 은 웹 range 4,500–4,900 중앙값. 3행 모두
  source 를 PDF → 웹으로 교체 (값·as_of 유지, tier media, status indicative).
- **부가**: 동 출처 'besi kapal'(선체 고철) 4,600–5,100/kg 을 Kelas A note 에 병기.
- **검증**: JSON 유효 · `lint_language.py` 0건 통과. 행 수 변동 없음(3행).
- **Phase 2 진행**: domestic_fuel_scrap 전체가 이제 웹 출처 (PDF 단독 의존 0).
- **다음**: iter 7 — international_freight.indices 변화율 보강.

### iter 7 — 2026-05-14 — international_freight.indices
- **출처**: Trading Economics / Baltic Exchange — Dry Index (tradingeconomics.com), tier=media.
- **갱신**: BDI 2,978→3,189 (2023-11 이후 최고) · BCI 4,955→5,340 · BPI 2,233→2,454,
  as_of 2026-05-08→2026-05-14. 각 행에 `wow_pct`(직전 스냅샷 대비 +7.1/+7.8/+9.9) 신규.
- **미갱신**: BSI·Capesize/Panamax/Supramax 5TC 는 2026-05-14 시점 공개 수치 미확인 →
  §3-A 에 따라 값·as_of 동결 (직전 값 복사 금지).
- **검증**: JSON 유효 · `lint_language.py` 0건 통과.
- **다음**: iter 8 — international_freight.scrap_* / sale_purchase (S&P 실거래 확보).

### iter 8 — 2026-05-14 — S&P 실거래 + 스크랩 LDT 검증
- **출처**: Lloyd's List S&P report (2026-05-08), tier=media. GMS Week-14 2026 리포트(보조).
- **sale_purchase_bulk**: PDF placeholder `No data acquired` → 웹 실거래로 대체 —
  2012년 건조 Capesize **'Bulk Joyance' $33M** 매각. status indicative (DWT·buyer·seller 미보도).
  build_meta `rows_no_data` 2→1.
- **scrap_dry_bulk / scrap_tanker**: GMS Week-14 2026 리포트가 기존 값(Bangladesh 450/470,
  India 425/445, Pakistan 440/460)을 **정확히 확인** — 값 변동 없음. (container LDT
  480/455/470 은 스키마에 카테고리 없어 미반영.) source_url 보강은 유지모드 과제로 이월.
- **검증**: JSON 유효 · `lint_language.py` 0건 통과.
- **다음**: iter 9 — commodity_news + overview 심화.

### iter 9 — 2026-05-14 — commodity_news + overview
- **출처**: Palm Oil Magazine (palmoilmagazine.com), tier=media.
- **commodity_news.cpo**: 2건 추가 — ① 5월 CPO 수출 기준가 USD 1,049.58/MT·수출세 USD 178
  (2026-05-01) ② KPBN Franco Dumai 15,325 IDR/kg, 3거래일 약세 후 반등 + 바이오디젤 HIP
  14,917 IDR/L (2026-05-12). news 5→7행.
- **overview[0]**: 헤드라인 배너 BDI 값을 iter 7 과 동기화 — 2,978(5/8) → 3,189(5/14),
  Capesize 5,340·Panamax 2,454, 출처 Trading Economics 로 정합.
- **coal/nickel**: 금주 검색분이 기존 5/4·5/5 보도와 동일 — 신규 항목 없음.
- **검증**: JSON 유효 · `lint_language.py` 0건 통과. build_meta news 7행 동기화.
- **다음**: iter 10 — events 일정 검증·확장.

### iter 10 — 2026-05-14 — events
- **출처**: metal.com / inamarine-exhibition.net / mining-indonesia.com, tier=verified(공식).
- **monthly**: ICEE 2026(05-11~13) 종료 → §3-F 에 따라 제거. 현재 진행 중 행사 없음 → `[]`.
- **upcoming**: ① Critical Minerals 웹 재확인(스트림·규모 보강) ② Indonesia Maritime
  Trade Expo → `INAMARINE 2026` 정식 명칭, 장소 JIExpo Kemayoran, **source PDF p.5 →
  공식 웹 교체** ③ `Mining Indonesia 2026`(09-09~12) 신규 행. 총 4행 유지(monthly -1, upcoming +1).
- **잔여 PDF 의존**: events 에서 PALMEX 2026 만 PDF p.5 — 유지모드 재검증 대상.
- **검증**: JSON 유효 · `lint_language.py` 0건 통과.
- **다음**: iter 11 — 구조: PDF 의존도 커버리지 지표.
