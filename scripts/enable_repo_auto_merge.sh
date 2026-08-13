#!/usr/bin/env bash
# GitHub 저장소에서 Allow auto-merge 를 켠다 (관리자 권한 필요).
# 실패 시 UI 경로를 안내한다.
set -euo pipefail

REPO="${1:-pds2225/mail}"

echo "==> ${REPO} allow_auto_merge 활성화 시도..."
if gh api -X PATCH "repos/${REPO}" -f allow_auto_merge=true \
  --jq '{allow_auto_merge, message: "ok"}'; then
  echo "완료: GitHub PR 페이지에서 Enable auto-merge 사용 가능"
  exit 0
fi

echo ""
echo "API 권한 부족(403). 저장소 Owner/Admin 계정으로 아래를 실행하세요:"
echo ""
echo "  gh api -X PATCH repos/${REPO} -f allow_auto_merge=true"
echo ""
echo "또는 GitHub UI:"
echo "  Settings → General → Pull Requests → Allow auto-merge 체크"
echo ""
echo "브랜치 보호(선택): Settings → Branches → main → Require status checks (test)"
