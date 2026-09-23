#!/bin/bash
RUN_ID=35867382667
while true; do
  status=$(gh run view "$RUN_ID" --json status -q '.status' 2>/dev/null)
  if [ "$status" = "completed" ]; then
    gh run view "$RUN_ID" --json status,conclusion -q '"status=\(.status) conclusion=\(.conclusion)"'
    break
  fi
  echo "$(date -u +%H:%M:%S) still $status"
  sleep 60
done
