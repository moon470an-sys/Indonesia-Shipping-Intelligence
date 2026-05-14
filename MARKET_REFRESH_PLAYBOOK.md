# Market 탭 — 웹 검색 기반 주간 자동 갱신 플레이북

> 이 문서는 **예약된 Claude 에이전트**(주 1회 cron 루틴) 와 수동 `/market-refresh`
> 실행이 **그대로 따르는 단일 절차서**입니다. 갱신 대상은 `docs/data/market.json`
> 하나뿐이며, 백엔드 파이프라인(`backend/`)과는 완전히 독립적으로 동작합니다.
>
> 핵심 원칙은 `README.md` §"Market 탭" 와 동일합니다 — **출처 검증·추정 금지·
> 가치 판단 표현 금지**. 웹 검색으로 출처를 못 찾은 수치는 **절대 만들어내지 않습니다.**

---

## 0. 한 줄 요약

매주, 공개 웹 + 인도네시아 로컬 SNS 를 검색해 `market.json` 의 가격·지수·뉴스
필드를 출처와 함께 갱신하고, lint 통과 후 commit/push 한다. GitHub Pages 가 자동 배포한다.

---

## 1. 사전 점검 (Pre-flight)

1. `docs/data/market.json` 을 읽고 현재 `checked_date`, `report_week`,
   `build_run_id` 를 확인한다.
2. 오늘 날짜를 확인한다. `report_week` 는 "Nth Week of <Month> <Year>" 형식으로
   ISO 주차에 맞춰 갱신한다 (예: 5월 셋째 주 → `"3rd Week of May 2026 (...)"`).
3. 직전 갱신 이후 7일 미만이면 — cron 중복 실행 — 변경 없이 종료한다.

---

## 2. 출처 규칙 (모든 섹션 공통, 위반 시 그 행을 버린다)

| 규칙 | 내용 |
|------|------|
| **출처 필수** | 모든 행/카드에 `source_name` + `source_url` (또는 `sources[]`) + 날짜. URL 없으면 `source_url: null` 허용하되 `source_name` 은 반드시 구체적으로. |
| **추정 금지** | 검색으로 못 찾은 수치는 입력하지 않는다. 행을 통째로 빼거나 `status: "No data acquired"`, `value_low/high: null` 로 둔다. 직전 값을 그대로 복사하지 않는다(stale 위장 금지). |
| **tier 분류** | `official` = 거래소·정부·협회 1차 자료 / `media` = 언론 보도 / `broker` = 선박 중개·브로커 리포트 / `sns` = LinkedIn·X·Instagram·Facebook 그룹 등 로컬 SNS 게시물. |
| **status 값** | `verified` = 1차 출처에서 직접 확인 / `indicative` = 차트 판독·SNS·단일 브로커 등 참고치 / `No data acquired` = 미확보 / `withheld_jump` = 직전 대비 30% 초과 급변으로 보류. |
| **가치 판단 금지** | "유망/매력적/기회/추천/공급 부족/투자 테제" 등 금지어 사용 금지. `python scripts/lint_language.py` 가 강제한다. |
| **해석 인용 형태** | 외부 분석·예측은 출처 기관을 명시한 인용으로만. Claude 자체 전망 서술 금지. |
| **언어** | 한국어 본문 + 영문 고유명사. 기존 행 톤을 그대로 따른다. |

---

## 3. 섹션별 갱신 절차

각 섹션은 **기존 스키마를 그대로 유지**한다(§4 참조). 행을 추가/교체/삭제할 수
있으나 키 이름·중첩 구조는 바꾸지 않는다.

### 3-A. `international_freight.indices` — 국제 운임 지수 (웹검색 신뢰도 높음)

검색 대상: **BDI, BCI, Baltic Panamax/Supramax 5TC**.

권장 검색어 / 출처:
- `Baltic Dry Index today` / `BDI` → HandyBulk (`handybulk.com/baltic-dry-index`),
  Trading Economics, The DCN "Baltic Exchange Weekly Report".
- `Baltic Capesize Index` → 동일.
- 5TC 일당(USD/day): 브로커 주간 리포트 검색 — 못 찾으면 직전 값 유지하지 말고
  `status: "indicative"` 그대로 두되 `as_of` 는 갱신하지 않는다.

행 갱신 시 `value`, `as_of`, `source_name`, `source_url`, `status` 를 모두 맞춘다.
`m1_pct`/`m3_pct`/… 변화율은 출처에 명시된 값만 채우고, 없으면 키를 빼거나 `null`.

### 3-B. `domestic_fuel_scrap` — 연료·스크랩·CPO 지수 (웹검색 부분 가능)

- `cpo_price_index_gapki` → `GAPKI CPO price index` 검색, `gapki.id`, Palm Oil
  Magazine, Bursa Malaysia CPO 선물(참고).
- `solar_b40_hsd`, `hfo_180_mfo` → 인도네시아 Pertamina Patra Niaga 산업용
  연료 고시가, 또는 SBS/브로커 인덱스 보도. 못 찾으면 행 유지 + `as_of` 동결.
- `scrap_domestic` → 인도네시아 고철 시세 보도 (Kelas A/B/C).

### 3-C. `domestic_vessel_pricing` — 도메스틱 선박 가격표 (★ SNS 기반, 핵심)

이 표(Tug & Barge / CPO TB+OB·SPOB / Oil Tanker / LCT 의 TC·SHB·NB)는
원래 SBS Weekly 비공개 PDF 산출물이다. **SBS 자체도 인도네시아 로컬 SNS·중개망에서
정보를 취합**하므로, 동일한 경로를 웹 검색으로 재현한다.

검색 경로 (인도네시아어로도 검색할 것):
- **Facebook 그룹 / Marketplace** — "jual kapal tug boat", "sewa tongkang batubara",
  "jual SPOB", "jual oil barge", "charter LCT", "harga kapal tanker bekas".
- **LinkedIn** — 인도네시아 ship broker·선사 담당자 게시물 ("tug & barge time charter
  rate", "second-hand barge sale").
- **OLX Indonesia / kapal marketplace** — 중고선 매물 호가.
- **브로커·중개사 사이트** — Sea Bridge Shipping, 로컬 shipbroker 블로그/공지.
- **언론** — Bisnis Indonesia, Kontan, Petromindo (용선료·선가 관련 보도).
- **X(Twitter), Instagram** — 선사·중개 계정 게시물.

행 처리 원칙:
1. **기존 PDF-출처 행은 함부로 덮어쓰지 않는다.** 웹/SNS 출처에서 값을 확인하면
   그 행의 `sources[]` 에 항목을 **추가**하고(2-source 충족), `status` 를
   `verified` 로 올릴 수 있다.
2. 새 매물·신규 용선 사례를 찾으면 해당 `category.rows[]` 에 행을 **추가**한다.
   `size`, `year_built`, `value_low`, `value_high`, `sources:[{name,tier,url}]`,
   `status` 를 채운다. SNS 단일 출처면 `tier:"sns"`, `status:"indicative"`.
3. 웹·SNS 어디서도 근거를 못 찾은 행은 그대로 두되 값을 손대지 않는다.
   기존 행이 6주 이상 갱신 없이 stale 하면 `status` 는 유지하고 본문에서 언급만 한다.
4. **추정 절대 금지** — "300ft 면 대략 이 정도" 식 보간 입력 금지.

`validation_policy` 의 `min_sources_per_row: 2`, `cross_source_band_pct: 15`,
`jump_block_pct: 30` 를 따른다. 두 출처 값 차이가 15% 초과면 둘 다 `sources[]` 에
남기고 `status:"indicative"`. 직전 대비 30% 초과 급변이면 `status:"withheld_jump"`.

### 3-D. `overview` — 이번 주 핵심 요약 (6장 내외)

`international_freight` 및 `commodity_news` 에서 가장 중요한 가격/정책 변동을
6장 이하로 요약. `overview[0]` 은 사이트 최상단 헤드라인 배너로 쓰이므로 가장
임팩트 있는 운임·가격 변동을 배치한다. 각 카드: `headline`, `detail_ko`,
`source_name`, `source_tier`, `source_url`, `as_of`, `category`
(`Freight`/`Policy`/`Commodity`/`Shipping`).

### 3-E. `commodity_news` — 상품·해운 뉴스

`coal`, `nickel`, `cpo`, `power`, `shipping` 토픽별 최근 1~2주 보도를 검색.
권장 출처: Mysteel·Petromindo·Argus(석탄), Mining.com·S&P Global(니켈),
GAPKI·Palm Oil Magazine(CPO), CNBC Indonesia(전력), Splash247·Bisnis
Indonesia·Pertamina PIS(해운). 각 항목: `title`, `summary_ko`, `source_name`,
`source_tier`, `source_url`, `published_date`, `status`.

### 3-F. `events` — 행사

`monthly`(이번 달 진행) / `upcoming`(예정). 인도네시아 해운·석탄·CPO 컨퍼런스
(INAMARINE, ICEE, PALMEX, Indonesia Miner 등) 일정을 검색해 지난 행사는
제거하고 신규 행사를 추가. 각 항목에 `checked_date` = 오늘.

---

## 4. 스키마 레퍼런스 (절대 깨지 않는다)

`international_freight.indices[]` / `domestic_fuel_scrap.*[]` / `overview[]` /
`commodity_news.*[]` 행은 **flat 키**를 쓴다:
```
"source_name", "source_tier", "source_url", "as_of"(또는 "published_date"), "status"
```

`domestic_vessel_pricing.markets[].categories[].rows[]` 는 **`sources[]` 배열**을 쓴다:
```json
{ "size": "...", "year_built": "...", "value_low": 0, "value_high": 0,
  "sources": [{ "name": "...", "tier": "broker|sns|media|official", "url": null }],
  "status": "indicative" }
```
두 스키마를 섞지 않는다. 편집 후 JSON 이 유효한지(`python -c "import json,sys;
json.load(open('docs/data/market.json',encoding='utf-8'))"`) 반드시 확인한다.

---

## 5. 메타 필드 갱신

매 실행 시 최상위 메타를 갱신한다:

| 필드 | 값 |
|------|-----|
| `checked_date` | 오늘 (YYYY-MM-DD) |
| `last_updated` | 오늘 |
| `next_scheduled` | 오늘 + 7일 |
| `report_week` | 현재 ISO 주차 기준 "Nth Week of <Month> <Year> (범위)" |
| `build_run_id` | `web-<YYYY>w<ISO주차>-auto` (예: `web-2026w20-auto`) |
| `reference_pdf` | 이번 주 PDF 미사용 시 그대로 두거나, 웹 전용 갱신이면 유지 |
| `build_meta` | `collectors_run` 에 `"web_search_auto"` 추가, `rows_published*` 카운트를 실제 행 수로 재계산, `extraction_method` = `"web search + Indonesian local SNS curation"` |

---

## 6. 검증 → 커밋

1. `python scripts/lint_language.py` — 금지어 0건 확인. 걸리면 표현을 고친다.
2. JSON 유효성 확인 (§4).
3. `git add docs/data/market.json` (다른 파일이 의도치 않게 섞이지 않았는지 확인).
4. 커밋 메시지:
   ```
   Market <YYYY-MM-DD> 웹검색 자동 갱신 — <갱신 섹션 요약>

   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
   ```
5. `git push` → GitHub Pages 워크플로(`.github/workflows/pages.yml`)가 자동 배포.
6. 변경이 전혀 없으면 커밋하지 않고 종료한다.

---

## 7. 실행 후 보고 (한국어, 5줄 이내)

- 갱신한 섹션과 행 수
- 새로 찾은 SNS/웹 출처 (도메스틱 선박 가격표 위주)
- `No data acquired` / `withheld_jump` 로 남긴 항목
- lint·JSON 검증 결과
- commit/push 결과 (또는 변경 없음)
