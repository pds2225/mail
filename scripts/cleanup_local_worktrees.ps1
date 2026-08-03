#Requires -Version 5.1
<#
.SYNOPSIS
  D:\mail 로컬 worktree / gone 브랜치 원클릭 정리 (비대화형).

.DESCRIPTION
  - main 제외 worktree 강제 제거
  - .git/worktrees 메타 + 잔여 폴더 삭제
  - gone / 지정 브랜치 로컬 삭제
  - git worktree prune 의 y/n 프롬프트는 자동으로 n (잠긴 파일은 스킵)
  - Cursor 자체는 종료하지 않음 (이 창이 닫히면 스크립트가 끊김)

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File D:\mail\scripts\cleanup_local_worktrees.ps1
#>
param(
    [string]$RepoRoot = "",
    [switch]$WhatIf
)

$ErrorActionPreference = "Continue"

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Invoke-Git([string[]]$GitArgs) {
    & git @GitArgs
    return $LASTEXITCODE
}

# --- resolve repo root ---
if (-not $RepoRoot) {
    if ($PSScriptRoot) {
        $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    } else {
        $RepoRoot = (Get-Location).Path
    }
}
$RepoRoot = $RepoRoot.TrimEnd('\', '/')
Set-Location $RepoRoot

Write-Host "Repo: $RepoRoot"
$gitTop = (& git rev-parse --show-toplevel 2>$null)
if (-not $gitTop) {
    Write-Error "git 저장소가 아닙니다: $RepoRoot"
    exit 1
}

# prune 대화형 프롬프트 자동 거부
function Invoke-GitPruneQuiet {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "git"
    $psi.Arguments = "worktree prune"
    $psi.WorkingDirectory = $RepoRoot
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    # 잠긴 디렉터리 재시도 질문에 전부 n
    1..80 | ForEach-Object { $p.StandardInput.WriteLine("n") }
    $p.StandardInput.Close()
    $out = $p.StandardOutput.ReadToEnd()
    $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit(120000) | Out-Null
    if ($out) { Write-Host $out }
    if ($err) { Write-Host $err }
}

Write-Step "현재 worktree"
Invoke-Git @("worktree", "list") | Out-Null
& git worktree list

# main / 현재 체크아웃 경로 보호
$mainPath = (Resolve-Path $RepoRoot).Path
$keepPaths = @(
    $mainPath.ToLowerInvariant(),
    ($mainPath -replace '\\', '/').ToLowerInvariant()
)

Write-Step "등록된 worktree 제거 (main 제외)"
$lines = & git worktree list --porcelain
$currentPath = $null
foreach ($line in $lines) {
    if ($line -match '^worktree (.+)$') {
        $currentPath = $Matches[1]
        continue
    }
    if ($line -match '^branch refs/heads/(.+)$' -and $currentPath) {
        $branch = $Matches[1]
        $norm = $currentPath.Replace('/', '\').TrimEnd('\').ToLowerInvariant()
        $normSlash = $currentPath.Replace('\', '/').TrimEnd('/').ToLowerInvariant()
        if ($keepPaths -contains $norm -or $keepPaths -contains $normSlash -or $branch -eq "main") {
            Write-Host "KEEP  $currentPath  [$branch]"
        } else {
            Write-Host "REMOVE $currentPath  [$branch]"
            if (-not $WhatIf) {
                & git worktree remove --force $currentPath 2>$null
                if (Test-Path -LiteralPath $currentPath) {
                    Remove-Item -LiteralPath $currentPath -Recurse -Force -ErrorAction SilentlyContinue
                }
            }
        }
        $currentPath = $null
    }
}

# 알려진 잔여 경로 (등록이 깨진 경우)
$orphanPaths = @(
    "$RepoRoot\.claude\worktrees\branch-cleanup-validation-8ac8f9",
    "$RepoRoot\.claude\worktrees\rm-loan",
    "$RepoRoot\.claude\worktrees\split-monitor",
    "D:\mail-wt-p0b-attachments",
    "D:\mail-wt-p0b-table-structure",
    "D:\mail-wt-p1-accuracy",
    "D:\mail-wt-p0-hardening"
)

Write-Step "잔여 폴더 강제 삭제"
foreach ($p in $orphanPaths) {
    if (Test-Path -LiteralPath $p) {
        Write-Host "RMDIR $p"
        if (-not $WhatIf) {
            # 읽기전용 속성 해제 후 삭제
            Get-ChildItem -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue |
                ForEach-Object { $_.Attributes = 'Normal' }
            Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Step ".git/worktrees 메타 정리 (잠긴 항목은 스킵)"
$metaRoot = Join-Path $RepoRoot ".git\worktrees"
if (Test-Path -LiteralPath $metaRoot) {
    Get-ChildItem -LiteralPath $metaRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "META $($_.FullName)"
        if (-not $WhatIf) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

if (-not $WhatIf) {
    Write-Step "git worktree prune (비대화형)"
    Invoke-GitPruneQuiet
}

Write-Step "gone / 잔여 로컬 브랜치 삭제"
$goneBranches = @(
    "chore/remove-loan",
    "chore/split-monitor",
    "codex/p0-sheet-hardening",
    "codex/p0b-attachment-extraction",
    "codex/p0b-detail-table-structure",
    "codex/p1-accuracy",
    "feat/feedback-act",
    "feat/generic-pagination",
    "feat/listonly-detail-enrich",
    "feat/p0-collection-gap-detection",
    "feat/recall-date",
    "cursor/w3-p0b-field-blank-and-p1-14a0",
    "cursor/filter-trace-sheet-id-14a0",
    "cursor/merge-190-14a0",
    "claude/branch-cleanup-validation-8ac8f9"
)

# porcelain gone 목록도 합치기
$vv = & git branch -vv
foreach ($line in $vv) {
    if ($line -match '^\+?\s*(\S+).*: gone\]') {
        $name = $Matches[1]
        if ($goneBranches -notcontains $name -and $name -ne "main") {
            $goneBranches += $name
        }
    }
}

foreach ($b in $goneBranches) {
    $exists = & git show-ref --verify --quiet "refs/heads/$b"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "BRANCH -D $b"
        if (-not $WhatIf) {
            & git branch -D $b 2>$null
        }
    }
}

Write-Step "최종 상태"
& git worktree list
& git branch -vv
& git status -sb

Write-Host ""
Write-Host "DONE. worktree 가 D:\mail [main] 만 남으면 성공." -ForegroundColor Green
Write-Host "Permission denied 가 남으면 PC 재시작 후 이 스크립트를 한 번 더 실행." -ForegroundColor Yellow
exit 0
