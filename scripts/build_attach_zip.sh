#!/bin/bash
# dist/ 지원사업_공고첨부_받기_설치.zip 재생성 (루트에 cmd·scripts 바로 두기)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d)"
OUT="$ROOT/dist/지원사업_공고첨부_받기_설치.zip"

mkdir -p "$STAGE/scripts"

cp "$ROOT/지원사업 공고첨부_받기.cmd" \
   "$ROOT/처음설치_한번만.cmd" \
   "$ROOT/배포용_압축하기.cmd" \
   "$ROOT/사용방법_공고첨부.txt" \
   "$ROOT/오류해결.txt" \
   "$ROOT/monitor.py" \
   "$STAGE/"

cp "$ROOT/scripts/fetch_notice_attachments.py" \
   "$ROOT/scripts/download_kstartup_targets.py" \
   "$ROOT/scripts/setup_attach_downloader.py" \
   "$ROOT/scripts/requirements-attach.txt" \
   "$ROOT/scripts/pack_attach_downloader.ps1" \
   "$STAGE/scripts/"
printf '{\n  "out_dir": ""\n}\n' > "$STAGE/scripts/notice_download_config.json"

cp -a "$ROOT/mail_core" "$ROOT/config" "$STAGE/"

cat > "$STAGE/여기서_실행하세요.txt" <<'EOF'
★ 이 폴더에서 실행하세요 ★

1. 처음설치_한번만.cmd  (처음 1회)
2. 지원사업 공고첨부_받기.cmd  (평소)

주의: cmd 파일만 바탕화면으로 복사하면 오류 납니다.
      scripts 폴더가 같은 위치에 있어야 합니다.
EOF

find "$STAGE" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
rm -f "$OUT"
(cd "$STAGE" && zip -r -q "$OUT" .)
rm -rf "$STAGE"

mkdir -p "$ROOT/dist"
cp "$ROOT/지원사업 공고첨부_받기.cmd" \
   "$ROOT/처음설치_한번만.cmd" \
   "$ROOT/사용방법_공고첨부.txt" \
   "$ROOT/오류해결.txt" \
   "$ROOT/dist/"
echo "OK: $OUT ($(du -h "$OUT" | cut -f1))"
