# Indonesia Shipping Intelligence

🌐 **Live dashboard**: https://moon470an-sys.github.io/Indonesia-Shipping-Intelligence/

인도네시아 해사청 선박 등록(`kapal.dephub.go.id`)과 Inaportnet 항만 LK3 물동량(`monitoring-inaportnet.dephub.go.id`) 데이터를 매월 자동 수집하고 변경사항을 추적하는 BI 시스템.

## 컴포넌트

| 폴더 | 역할 |
|------|------|
| `backend/` | Python 수집·DB·diff·리포트 파이프라인 |
| `dashboard/` | Streamlit 인터랙티브 대시보드 (사내용, DB 직결) |
| `docs/` | GitHub Pages 정적 사이트 (대외 공개) |

## 빠른 시작

```bash
# 1. 의존성
pip install -r requirements.txt

# 2. 한 번에 무인 실행 (수집 + diff + 리포트)
python -m backend.main monthly --auto

# 3. 정적 사이트 JSON 갱신
python -m backend.build_static

# 4. (선택) 사내 대시보드
python -m streamlit run dashboard/app.py
```

## 매월 자동 갱신

```bash
python -m backend.scheduler   # 매월 1일 03:00 KST
```

## 데이터 흐름

```
정부 API ─▶ Python 수집 ─▶ SQLite (data/shipping_bi.db)
                              │
                              ├─▶ vessels_changes / cargo_changes (월 단위 diff)
                              ├─▶ reports/changes_YYYY-MM.html / .xlsx
                              ├─▶ Streamlit (사내)
                              └─▶ docs/data/*.json ─▶ GitHub Pages (대외)
```

## CLI 요약

| 명령 | 설명 |
|------|------|
| `python -m backend.main test-fleet`  | 선복량 샘플 테스트 |
| `python -m backend.main test-cargo`  | 물동량 샘플 테스트 |
| `python -m backend.main run-fleet`   | 선복량 전수 수집 |
| `python -m backend.main run-cargo`   | 물동량 전수 수집 |
| `python -m backend.main diff --month YYYY-MM` | 변경 탐지 |
| `python -m backend.main report --month YYYY-MM --html` | 리포트 |
| `python -m backend.main monthly --auto` | 전체 무인 실행 |
| `python -m backend.main monthly --resume` | 누락분만 보충 |
| `python -m backend.resume_run` | 코드 단위 누락 + diff + 리포트 |
| `python -m backend.build_static` | 정적 사이트 JSON 빌드 |
| `python -m backend.scheduler` | APScheduler 실행 |

## 변경 탐지 의미

- **ADDED / REMOVED**: 새로 등록되거나 사라진 선박/항구-월 키
- **MODIFIED**: 동일 선박 키의 필드가 바뀜 (선명/선사/GT/선종 등)
- **REVISED**: 동일 항구·월·구분의 LK3 행수·총합 변동 (delta % 임계 초과)

## Market 탭 — 주간 시장 인텔리전스 갱신

📊 Market 탭은 backend 파이프라인과 별도로 운영되는 **수동 큐레이션 데이터** 입니다.
출처를 검증할 수 있는 외부 공개 정보만 입력합니다.

**데이터 파일**: `docs/data/market.json`

### 갱신 절차 (권장: 주 1회)

1. `docs/data/market.json` 직접 편집
2. `checked_date` 를 오늘 날짜로 업데이트
3. 각 섹션 (`overview`, `freight_indices`, `commodity_prices`, `freight_rates_indicative`, `commodity_news`, `shipping_news`, `events`) 의 항목 추가/교체
4. 모든 항목에 **반드시** `source`, `source_url`, `published_date` (이벤트는 `checked_date`) 포함
5. 검증 안 된 수치는 `"indicative": true` 로 표시
6. `python scripts/lint_language.py` 통과 확인 (가치 판단 표현 금지)
7. `git commit -m "Market <date> 갱신"` + `git push` → GitHub Pages 자동 배포

### 권장 출처

| 카테고리 | 권장 출처 |
|---------|----------|
| BDI / 운임 지수 | The DCN Baltic Exchange Weekly, HandyBulk, Trading Economics |
| 인도네시아 HBA / 석탄 | Mysteel, CoalTradeIndo, Argus Coalindo, Petromindo |
| CPO | Palm Oil Magazine, Bursa Malaysia, GAPKI |
| 니켈 / LME | Mining.com, IDNFinancials, S&P Global |
| 인도네시아 해운 뉴스 | Pelindo, Pertamina PIS, Indonesia Shipping Gazette, Splash247, Bisnis Indonesia |
| 행사 | INAMARINE, GAPKI, Fastmarkets Coaltrans, Petromindo |
| SNS | LinkedIn (Pertamina PIS, Pelindo, GAPKI), X/Twitter, Instagram (@inamarine) |

### 원칙

- **출처 부족** → 해당 항목 제외 또는 별도 `unverified` 섹션 (현재는 미사용)
- **빈 섹션** → "No recent verified data found" 자동 표시
- **가치 판단 표현 금지** — `scripts/lint_language.py` 블랙리스트 (유망/추천/기회/투자 테제 등) 회피
- **추정·해석 금지** — 외부 분석/예측은 출처 기관 명시 후 인용 형태로만 노출
