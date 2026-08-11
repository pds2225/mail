# 핵심 공고 필드 학습 루프

대상은 기업마당, K-Startup, NIPA, KITA다. 기존 커버리지 게이트가 건수,
제목, 링크, 날짜만 확인해 상세본문과 지원대상 누락을 정상으로 통과시키던
빈틈을 별도 계측으로 막는다.

## 실행 흐름

1. `scripts/monitor_runtime.py`가 현재 K-Startup DOM 호환 어댑터를 설치한 뒤
   기존 `monitor.py` CLI를 그대로 실행한다.
2. 실행이 끝나면 각 핵심 소스의 최신 3건만 읽기 전용으로 다시 표본검사한다.
3. 제목, 본문, 날짜, 신청기간, 지원대상의 읽기 성공률과 값 존재율을 분리한다.
   원문에 신청기간·대상이 없다는 `NOT_SPECIFIED`는 읽기 성공이지만 값 존재는
   0으로 남는다. 제목·날짜는 실제 값이 있어야 읽기 성공이다.
4. 비율과 실패 fingerprint만
   `var/state/source_field_quality_history.json`에 최대 30회 저장한다. 원문과
   오류 전문은 저장하지 않는다. fingerprint가 발생한 필드의 실행값은 정상
   기준선 계산에서 제외해 지속 장애가 새 정상으로 학습되지 않게 한다.
5. 기업마당·K-Startup은 첫 실패부터 P0다. NIPA·KITA는 같은 fingerprint가
   2회 연속이면 P1에서 P0로 승격한다. 정상 이력 3회 이후 중앙값보다 20%p
   이상 급락해도 회귀 결함으로 기록한다.
6. 최신 결과는 `var/logs/source_field_quality_latest.{json,md}` 아티팩트로
   보존한다. P0는 digest 발송을 실패시키지 않으면서 GitHub Actions 오류 주석과
   `NTFY_TOPIC` 긴급 폰 알림으로 즉시 노출한다.

## 검증

```powershell
.venv\Scripts\python.exe scripts/source_field_quality_gate.py --offline
.venv\Scripts\python.exe scripts/source_field_quality_gate.py --live --json
.venv\Scripts\python.exe scripts/loop_verify.py --quick
```

`--live`는 실제 사이트와 기업마당 API 키가 필요하지만 메일 발송과 seen 상태
저장은 하지 않는다. 운영 계측 실패도 본 수집·발송을 실패시키지 않는다.
