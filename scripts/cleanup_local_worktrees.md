# 로컬 worktree 원클릭 정리

Windows(`D:\mail`)에서 옛 Claude/Codex worktree·gone 브랜치를 **질문 없이** 지웁니다.

Cloud 에이전트는 사용자 PC 프로세스에 접근할 수 없으므로, 이 스크립트만 로컬에서 1회 실행하면 됩니다.

## 실행 (한 줄)

PowerShell에서:

```powershell
cd D:\mail
git pull origin main
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\cleanup_local_worktrees.ps1
```

미리보기만:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\cleanup_local_worktrees.ps1 -WhatIf
```

## 하는 일

1. `main` 제외 등록 worktree `git worktree remove --force`
2. `D:\mail-wt-*`, `.claude\worktrees\*` 잔여 폴더 삭제
3. `.git\worktrees\*` 메타 삭제 (잠긴 항목은 스킵)
4. `git worktree prune` — y/n 프롬프트에 자동 `n`
5. gone / 지정 잔여 로컬 브랜치 `-D`

## 건드리지 않음

- `main`, `backup/*`
- Cursor 프로세스 (스크립트가 자기 창을 죽이면 중단되므로 종료하지 않음)
- 원격 브랜치 / open PR

## 실패 시

폴더 잠금(Permission denied)이 남으면 PC 재시작 후 같은 명령을 한 번 더 실행하면 됩니다.
