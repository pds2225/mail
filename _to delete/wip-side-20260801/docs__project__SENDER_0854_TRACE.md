# 08:54 발송처 추적 (TASK-02 / TASK-G02)

> 조사만. 외부 발송을 실제로 삭제·정지하지 않는다. 끄기 절차만 기록.

## 결론 (갱신 2026-08-01 실측)

**확정 아님 — 유력 후보가 둘로 갈린다.** Gmail 원본 헤더로만 최종 확정 가능.

| 후보 | 근거 | 상태 |
|------|------|------|
| **A. repo 밖(Apps Script/구클론/타PC)** | 본문 지문 `소스: 기업마당 API + 마이페어 + K-Startup`이 **이 저장소 생성 코드에 없음**(MDR-003). 공식 digest는 `수집일시:` + `재조회범위:`. 08:54에 맞는 GHA run 없음. 이 PC `monitor.py` 작업스케줄러 없음 | **유력 (7/30 실측 메일 기준)** |
| **B. 지연된 GHA monitor** | Actions schedule 혼잡 지연으로 수신이 08:50~09:00대로 흔들릴 수 있음. 공식 cron은 현재 **07:30 / 18:30 KST** | 가능하나, **지문 문구가 다르면 동일 파이프라인으로 볼 수 없음** |

### 2026-08-01 git/로컬/GHA 재검증
- 브랜치 당시: `main` / `main-sync` 계열, #216/#218 ancestor OK
- `rg`/`git grep`: `기업마당 API + 마이페어` → **발송 본문 생성 코드 0건** (MDR·rules 문서만)
- 로컬: `monitor.py` Task **없음**. `work-cockpit-briefing-mail`(07:00)은 별도 브리핑
- GHA 아침 run 예: 8/1 **08:31** 시작 → 수집완료 ~**09:55** → 공식 메일 ≈10시대
- 7/28·7/29: skip로 **2m44s/2m45s** success(과거 사고) — 발송 주체 이슈와는 별개

## 공식 파이프라인 (이 저장소)

| 항목 | 값 |
|------|-----|
| 워크플로 | `.github/workflows/monitor.yml` (`수출지원 모니터링 자동 실행`) |
| cron | `30 22 * * *`(07:30 KST), `30 9 * * *`(18:30 KST) |
| 명령 | `python scripts/monitor_runtime.py --send --persist-seen --coverage-alert` |
| 본문 마커 | `수집일시:` + `재조회범위:` (`monitor.py`) |
| 동시성 | `concurrency.group: monitor-daily-send` |

## Gmail 원본 체크리스트 (사용자)

1. `Received` / 첫 SMTP 호스트·시각(KST)
2. `X-Google-AppScript` / `X-Mailer` / `Message-Id` / `List-Id`
3. From/Reply-To가 GHA `GMAIL_ADDRESS`와 동일 여부
4. 본문에 `수집일시:`·`재조회범위:` **유무** vs `소스: 기업마당 API + 마이페어 + K-Startup`
5. [script.google.com](https://script.google.com) 트리거·GmailApp 목록

## 끄기 절차 (실행하지 말 것 — 참고만)

### 후보 A가 확정되면
1. Apps Script 트리거 중지 또는 구버전/타PC cron 비활성
2. 공식은 GHA만 유지(07:30/18:30 KST)
3. 수신 메일에 공식 마커 없으면 비공식으로 폐기

### 후보 B(공식 GHA)만 남기려면
1. **일시 중지:** Actions → 해당 워크플로 → Disable workflow
2. **dry-run만:** `--send` → `--dry-run` (PR+사람 승인)
3. Secret 제거로 끄기 금지(`GMAIL_*` 삭제는 추적만 어렵게 함)

⚠️ 이 세션에서는 위 끄기 절차를 **실행하지 않았다**.

## 운영 규칙
- **유일한 실발송:** GHA `monitor.yml`
- 로컬/스케줄러/Apps Script는 dry-run·초안만
- 정확도 개선은 이 파이프라인에만 넣는다(외부 발송이 살아 있으면 사용자에게 구버전이 도착)
- 일일 검수: `python scripts/mail_daily_review.py --json` (MDR-003)
