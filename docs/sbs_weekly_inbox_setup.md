# SBS Weekly Marketing Report — 자동 인입 셋업 (Phase 1)

> 목표: `yoonseok.moon@sticorp.co.kr` 으로 도착하는 **제목이 `SBS Weekly Marketing Report` 로 시작하는 메일** 의 PDF 첨부를 OneDrive 의 `data/raw/sbs_weekly/` 폴더에 자동 저장한다.
>
> 이 폴더는 Phase 3 의 `/market-refresh-from-pdf` 스킬이 매주 월요일 09:00 KST 에 스캔하는 입력 디렉터리다. 폴더 내 신규 PDF → `docs/data/market.json` 갱신 → GitHub Pages 자동 배포로 이어진다.

---

## 0. 전제

- 메일 계정: `yoonseok.moon@sticorp.co.kr` (Microsoft 365)
- 저장 경로: `OneDrive - (주) ST International\Projects\인도네시아 해운 BI\data\raw\sbs_weekly\`
- 파일명: SBS 가 보내는 원본명을 유지 (예: `[SBS] Weekly Marketing Report 2026.05.15.pdf`)
- 동일 파일명 재수신 시: Outlook/Power Automate 의 기본 동작은 덮어쓰기 — 그대로 둔다. Phase 3 의 state file (`.processed.json`) 이 sha256 으로 중복 처리를 막는다.

---

## 1. 권장 경로 — Power Automate (클라우드 플로우)

> 데스크톱 Outlook 이 꺼져 있어도 365 클라우드가 처리하므로 가장 안정적이다. sticorp 365 라이선스에 Power Automate 가 포함되어 있어야 한다 (대부분 E3/E5 기본 포함).

### 1-1. 새 자동 클라우드 플로우 생성

1. https://make.powerautomate.com 접속 → 좌측 **만들기** → **자동화된 클라우드 플로우**
2. 플로우 이름: `SBS Weekly PDF → OneDrive`
3. 트리거 선택: **새 메일이 도착할 때 (V3)** — Office 365 Outlook 커넥터
4. **만들기**

### 1-2. 트리거 조건 설정

`새 메일이 도착할 때 (V3)` 트리거 우측 `…` → **고급 옵션 표시**:

| 항목 | 값 |
|---|---|
| 폴더 | `Inbox` |
| 보낸 사람 | (SBS 발신 주소를 알면 입력 — 모르면 비워둠) |
| 받는 사람 | `yoonseok.moon@sticorp.co.kr` |
| 제목 필터 | `SBS Weekly Marketing Report` |
| 첨부 파일 포함 | **예** |
| 첨부 파일만 | **예** |

> 제목 필터는 Outlook 의 "포함" 매칭이라 `SBS Weekly Marketing Report` 가 어디든 들어 있는 메일을 잡는다. "starts with" 가 필요하면 다음 단계의 조건 분기로 한 번 더 거른다 (1-3 참고).

### 1-3. (옵션) 제목 starts-with 엄격 검증

트리거 다음에 **컨트롤 → 조건** 추가:

```
조건식: startsWith(triggerOutputs()?['body/subject'], 'SBS Weekly Marketing Report')
값:    is equal to    true
```

**예** 분기에만 후속 단계를 둔다.

### 1-4. 첨부 루프 + OneDrive 저장

트리거 다음 (조건이면 **예** 분기 안):

1. **각각에 적용** 추가 → 출력 선택: `첨부파일` (`triggerOutputs()?['body/attachments']`)
2. 루프 안에 **컨트롤 → 조건** 추가:
   ```
   endswith(toLower(items('각각에_적용')?['name']), '.pdf')   is equal to   true
   ```
3. **예** 분기에 **OneDrive for Business → 파일 만들기** 액션 추가
4. 액션 설정:
   - 폴더 경로: `/Projects/인도네시아 해운 BI/data/raw/sbs_weekly`
     - (OneDrive 동기화 루트 기준 상대 경로. 사용자 OneDrive 마운트 구조에 따라 `/문서/...` 가 앞에 붙을 수 있으니 폴더 picker 로 직접 선택 권장)
   - 파일 이름: `@{items('각각에_적용')?['name']}`
   - 파일 콘텐츠: `@{items('각각에_적용')?['contentBytes']}`

### 1-5. 저장 + 테스트

- 우측 상단 **저장** → **테스트** → **수동** → SBS 발신 메일 1건이 도착한 상태에서 트리거 재생
- 성공 시 OneDrive 폴더에 PDF 가 떨어진다. 동기화가 끝나면 로컬 PC 의 `data/raw/sbs_weekly/` 에서도 보인다 (OneDrive 클라이언트 동기화 지연 ~수분).

---

## 2. 대안 — 데스크톱 Outlook (Classic) + VBA

> Power Automate 사용이 어렵거나 sticorp IT 정책으로 막혀 있을 때만 사용. **New Outlook for Windows / Outlook on the Web 에서는 동작하지 않음** (VBA 미지원).

### 2-1. Outlook 옵션 — 매크로 활성화

1. **파일 → 옵션 → 보안 센터 → 보안 센터 설정 → 매크로 설정**
2. **알림이 표시된 매크로 사용** 또는 **디지털 서명된 매크로만** 으로 설정
3. Outlook 재시작

### 2-2. VBA 코드 등록

1. `Alt + F11` → VBA 편집기
2. 좌측 트리에서 `Project1 → Microsoft Outlook Objects → ThisOutlookSession` 더블클릭
3. 아래 코드 붙여넣기 (경로는 본인 환경에 맞게 수정 — `Yoonseok` 부분):

```vb
Public Sub SaveSBSAttachment(itm As Outlook.MailItem)
    Const SAVE_DIR As String = _
        "C:\Users\Yoonseok.moon\OneDrive - (주) ST International\Projects\인도네시아 해운 BI\data\raw\sbs_weekly\"
    Dim att As Outlook.Attachment
    Dim fname As String
    For Each att In itm.Attachments
        fname = LCase(att.FileName)
        If Right(fname, 4) = ".pdf" Then
            On Error Resume Next
            att.SaveAsFile SAVE_DIR & att.FileName
            On Error GoTo 0
        End If
    Next att
End Sub
```

4. `Ctrl + S` 로 저장. Outlook 재시작.

### 2-3. 규칙 만들기

1. **홈 → 규칙 → 규칙 만들기 → 고급 옵션**
2. 조건: `제목이 SBS Weekly Marketing Report 단어를 포함하는 경우` + `첨부 파일이 있는 경우`
3. 동작: **스크립트 실행 → SaveSBSAttachment 선택**
   - 스크립트 옵션이 안 보이면 레지스트리 패치 필요: `HKEY_CURRENT_USER\Software\Microsoft\Office\16.0\Outlook` 아래 `EnableUnsafeClientMailRules` (DWORD) = 1 추가 후 Outlook 재시작
4. 예외 없음 → 규칙 이름: `SBS Weekly → sbs_weekly folder` → 마침

---

## 3. 동작 검증

규칙/플로우 설정 후, 다음 SBS Weekly 메일이 도착하면:

- 5분 내 OneDrive 폴더 (`data/raw/sbs_weekly/`) 에 `[SBS] Weekly Marketing Report YYYY.MM.DD.pdf` 가 추가된다
- 로컬 PC 의 OneDrive 동기화도 이어서 반영된다

처음 1~2주는 도착 직후 폴더를 직접 확인해 누락 여부 점검.

---

## 4. 5/15 PDF 회수 (Phase 6 검증용)

위 규칙은 **설정 시점 이후** 도착 메일에만 적용된다. 5/15 메일은 이미 도착한 메일이므로 다음 중 하나로 폴더에 배치한다.

### 4-1. (가장 간단) 수동 저장

1. Outlook 에서 5/15 SBS 메일 열기
2. 첨부 PDF 우클릭 → **다른 이름으로 저장** → 위 폴더 선택 → 원본 파일명 유지

### 4-2. (Power Automate 사용 시) 플로우 수동 재실행

1. https://make.powerautomate.com → 본인 플로우 → **실행 기록**
2. 5/15 메일이 트리거 재생 대상이 아니라면 → "수동" 트리거 변형으로 일회용 플로우를 만들어 5/15 메일 ID 를 직접 입력해 첨부 다운로드

### 4-3. (Outlook VBA 사용 시) 규칙 즉시 적용

1. **홈 → 규칙 → 규칙 및 알림 관리 → 지금 규칙 실행**
2. `SBS Weekly → sbs_weekly folder` 선택 → **받은 편지함** 폴더 → **실행**
3. 5/15 메일에도 규칙이 적용되어 PDF 가 폴더에 떨어진다

---

## 5. 설정 완료 체크리스트

- [ ] OneDrive 폴더 `data/raw/sbs_weekly/` 존재 (이미 생성됨 ✓)
- [ ] 시드 파일 `[SBS] Weekly Marketing Report 2026.05.07.pdf` 폴더 안에 있음 (이미 복사됨 ✓)
- [ ] Power Automate 플로우 OR Outlook VBA 규칙 활성화
- [ ] 5/15 PDF 가 폴더에 들어옴 (Phase 6 검증 입력)
- [ ] 다음 SBS 메일 (보통 매주 수~목) 1건이 자동 저장되는지 직접 확인

체크리스트 모두 통과하면 → Phase 2 (PDF 파서) 로 진입한다.
