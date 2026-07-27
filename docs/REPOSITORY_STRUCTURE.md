# 저장소 구조

## 기준 구조

```text
mail/
├── monitor.py
├── streamlit_app.py
├── mail_core/
│   ├── matching/
│   ├── delivery/
│   ├── storage/
│   ├── security/
│   └── operations/
├── config/
│   └── targets/
├── var/
│   ├── state/
│   ├── outbox/
│   ├── logs/
│   ├── reports/
│   └── raw/
├── api/
├── web/
├── scripts/
├── tests/
│   └── fixtures/
├── docs/
│   ├── project/
│   └── works/
├── auto_dev/
├── data/golden/
└── secrets/README.md
```

## 경로 원칙

| 구분 | 기준 경로 | Git 정책 |
|---|---|---|
| 운영 설정 | `config/` | 추적 |
| 핵심 모듈 | `mail_core/` | 추적 |
| 골든 데이터 | `data/golden/` | 추적 |
| 실행 로그·리포트·원문 | `var/logs`, `var/reports`, `var/raw` | 제외 |
| 중복 방지 상태 | `var/state/seen_ids.json` | 추적 |
| 발송 체크포인트 | `var/state/delivery_state.json` | 추적 |
| 암호화 재시도 큐 | `var/outbox/delivery_outbox.enc` | 추적 |

상태 3종은 GitHub Actions가 매 실행 새 컨테이너에서 시작하는 제약 때문에
예외적으로 커밋백한다. 외부 영속 저장소로 전환하기 전에는 제외하면 안 된다.

## 환경별 재지정

- `MAIL_CONFIG_DIR`: 설정 디렉터리 변경
- `MAIL_VAR_DIR`: 런타임 디렉터리 변경

Vercel 함수는 쓰기 가능한 `/tmp/monitor_ws/var`를 `MAIL_VAR_DIR`로 사용한다.
