#!/bin/bash
# Claude Code on the web SessionStart 훅 — 웹 세션에서 테스트/수집이 바로 되도록 파이썬 의존성 설치.
# 동기(synchronous) 모드: 세션 시작 전에 설치를 끝내 '테스트가 아직 준비 안 됨' 레이스를 방지한다.
set -euo pipefail

# 웹(원격) 세션에서만 실행 — 로컬 데스크톱은 이미 개발환경이 갖춰져 있으므로 건너뛴다.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# 의존성 설치(멱등·재실행 안전). 컨테이너 상태가 캐시되므로 ci 대신 install 사용.
# 상세 로그는 파일로 빼 SessionStart stdout(세션 컨텍스트로 주입됨)을 오염시키지 않는다.
LOG="${TMPDIR:-/tmp}/session-start-install.log"
if {
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
} > "$LOG" 2>&1; then
  echo "[session-start] 파이썬 의존성 설치 완료 (requirements.txt)"
else
  echo "[session-start] 의존성 설치 실패 — 로그 마지막 20줄:"
  tail -20 "$LOG"
  exit 1
fi
