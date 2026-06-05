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
| `python -m backend.main monthly --auto` | 전체 무인 실행 (수집→diff→리포트→**빌드→배포**) |
| `python -m backend.main monthly --resume` | 누락분만 보충 |
| `python -m backend.main monthly --no-deploy` | 빌드까지만, 자동 커밋·푸시 생략 |
| `python -m backend.main build` | 사이트 JSON 재빌드 (build_static + build_derived) |
| `python -m backend.main deploy` | docs/ 변경분만 커밋·푸시 → GitHub Pages 배포 |
| `python -m backend.resume_run` | 코드 단위 누락 + diff + 리포트 |
| `python -m backend.build_static` | 정적 사이트 JSON 빌드 (docs/data) |
| `python scripts/fetch_idx_financials.py` | IDX XBRL 해운사 재무 수집 (💼 Financials 탭) |
| `python -m backend.scheduler` | APScheduler 실행 |

## 변경 탐지 의미

- **ADDED / REMOVED**: 새로 등록되거나 사라진 선박/항구-월 키
- **MODIFIED**: 동일 선박 키의 필드가 바뀜 (선명/선사/GT/선종 등)
- **REVISED**: 동일 항구·월·구분의 LK3 행수·총합 변동 (delta % 임계 초과)

## 화물 데이터 품질 가드

LK3 원천에는 단일 항차 화물량이 선박 적재능력을 초과하는 입력 오류가
존재합니다(전체의 ~10–12%). `backend/cargo_quality.capped_ton_sql` 가
`ton > GT × 3`(선박 GT 기준 물리적 상한, 보수적) 인 행을 0 처리하며,
`build_static`·`build_derived` 의 모든 화물 톤 집계에 적용됩니다. 따라서
`monthly` 실행이 끝나면 **사이트 빌드 단계에서 자동으로** 이상치가 제거된
수치가 생성됩니다 — 별도 수동 보정 불필요.

## 💼 Financials 탭 — 상장 해운사 재무 (IDX XBRL)

인도네시아 증권거래소(IDX)가 상장사별로 공시하는 **감사받은 연차 재무제표
XBRL 인스턴스**(`instance.zip`)를 자동 수집해, 해운/항만 ~37개사의 매출·순이익·
자산·부채·자본 및 파생 비율(순이익률·ROE·ROA·DER·유동비율)을 표시합니다.

**수집기**: `scripts/fetch_idx_financials.py`

```bash
python scripts/fetch_idx_financials.py                 # 캐시 활용 수집
python scripts/fetch_idx_financials.py --workers 1 --delay 1.2   # throttle 회피(정중)
python scripts/fetch_idx_financials.py --refresh       # 전체 재다운로드
python scripts/fetch_idx_financials.py --only SMDR BULL  # 일부만
```

- **출처**: `GetFinancialReport` API → `instance.zip` 내 `instance.xbrl`
  (idx-cor / idx-dei 개념). 값은 항상 전액(full amount) 단위.
- **통화**: 보고통화가 제각각(SMDR·BULL 등 USD, Temas 등 IDR)이라 **USD 백만**으로
  환산 비교(연도별 평균환율)하고, 개별 상세에는 **원 보고통화** 수치를 병기.
- **출력**: `data/idx_financials.json`(정본) + `docs/data/companies_financials.json`(배포).
  `backend.build_static` 는 정본이 있으면 이를 그대로 통과(없으면 레거시 YAML 폴백).
- **캐시**: `data/idx_xbrl_cache/*.zip` (gitignore). XBRL 은 연 1회 갱신이므로 재실행은
  네트워크를 건너뜀. IDX 는 Cloudflare 가 Python TLS 를 차단(403)하므로 `curl` 로 우회.
- **갱신 주기**: 연 1회 감사보고서 제출(통상 3~4월) 이후 1회 실행으로 충분.
