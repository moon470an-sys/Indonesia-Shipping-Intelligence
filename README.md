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
