# Cargo 대시보드 업그레이드 — 이어서 할 작업

## 현재 상태 (2026-05-06 08:30 KST)

### 완료
- `backend/build_static.py` — `cargo_payload()` 재작성
  - SQLite `json_extract` + GROUP BY로 6개 SQL 쿼리, Python 메모리 폭주 회피
  - 새 스키마: `jenis_top`, `komoditi_top`, `port_top`, `monthly_ton`, `port_jenis_matrix`, `totals`
- `docs/index.html` — Cargo 섹션 5개 차트로 재구성 (jenis bar, komoditi bar, ports stacked, monthly trend, port×jenis heatmap)
- `docs/js/app.js` — `renderCargo()` 새 데이터 모델로 재작성

### DB 부수 효과 (정리 필요 없음, 그대로 두기)
- `cargo_snapshot` 에 빈 컬럼 6개 추가됨: `jenis_b, ton_b, komoditi_b, jenis_m, ton_m, komoditi_m`
- 백필은 디스크 부족(7GB / DB 5.4GB)으로 실패 → 빈 컬럼 그대로 둠 (사용 안 함)
- `models.py`에는 반영 안 됨. 다음 마이그레이션 시 정리.

### 미완 (이어서 할 것)
1. **`python -m backend.build_static` 실행** — cargo.json 새로 생성. SQL 쿼리 6개 × 60초 ≈ 5-7분 예상
   - 출력 확인: `docs/data/cargo.json` mtime 갱신, size > 1MB 예상
   - 검증: `python -c "import json; d=json.load(open('docs/data/cargo.json')); print(len(d['jenis_top']), len(d['komoditi_top']), len(d['port_top']))"`
2. **로컬 검증** — 브라우저에서 `docs/index.html` 열어 Cargo 탭 차트 확인
3. **커밋 + 푸쉬** — `docs/data/*.json` 포함해서 푸쉬하면 워크플로우가 자동 배포
4. **(선택) cargo_snapshot 빈 컬럼 정리** — 디스크 확보 후 `ALTER TABLE ... DROP COLUMN` 또는 무시

## 디스크 주의
- C: 7.2GB free, DB 5.4GB. SQLite UPDATE/DROP은 임시 디스크가 DB만큼 필요. 큰 작업 전 디스크 확보 필요.

## 실행 환경
- 작업 디렉토리: `C:\Users\yoonseok.moon\OneDrive - (주) ST International\Projects\인도네시아 해운 BI`
- Python: `/c/Python314/python`
- 워크플로우: `.github/workflows/pages.yml` (push to main → GitHub Pages 자동 배포)
