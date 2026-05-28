#Requires -Version 5.1
<#
.SYNOPSIS
  D:\auto_mail vs D:\mail (또는 지정 경로) 중 최신 폴더를 판별하고,
  구버전을 최신에 병합한 뒤 구버전 폴더를 삭제하고 git과 동기화합니다.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\sync_local_mail_folders.ps1
  powershell -ExecutionPolicy Bypass -File scripts\sync_local_mail_folders.ps1 -PathA D:\auto_mail -PathB D:\mail -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$PathA = "D:\auto_mail",
    [string]$PathB = "D:\mail",
    [string]$Remote = "origin",
    [string]$Branch = "main",
    [switch]$SkipGitPull,
    [switch]$ForceDelete
)

$ErrorActionPreference = "Stop"

function Test-MailProjectRoot {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $markers = @("monitor.py", "sites.json", "groups.json")
    foreach ($m in $markers) {
        if (-not (Test-Path -LiteralPath (Join-Path $Path $m))) { return $false }
    }
    return $true
}

function Get-ProjectScore {
    param([string]$Path)
    $score = 0
    $details = [ordered]@{}

    if (-not (Test-MailProjectRoot $Path)) {
        return @{ Score = -1; Details = @{ valid = $false } }
    }

    foreach ($f in @("vercel.json", "api\index.py", "api\run.py", "streamlit_app.py", "auto_mail_web.html", "scripts\auto_dev_queue.py")) {
        if (Test-Path -LiteralPath (Join-Path $Path $f)) { $score += 10 }
    }

    $gitDir = Join-Path $Path ".git"
    if (Test-Path -LiteralPath $gitDir) {
        $score += 50
        Push-Location $Path
        try {
            $url = (git remote get-url $Remote 2>$null)
            if ($url -match "pds2225/mail") { $score += 30 }
            $head = (git rev-parse HEAD 2>$null)
            if ($head) {
                $details["git_head"] = $head.Substring(0, [Math]::Min(12, $head.Length))
                $dt = (git log -1 --format="%ct" HEAD 2>$null)
                if ($dt) {
                    $details["git_commit_unix"] = [int64]$dt
                    $score += [int]([int64]$dt / 100000)
                }
            }
        } finally { Pop-Location }
    }

    foreach ($key in @("monitor.py", "streamlit_app.py", "sites.json", "groups.json", "settings.json", "vercel.json")) {
        $fp = Join-Path $Path $key
        if (Test-Path -LiteralPath $fp) {
            $details["mtime_$key"] = (Get-Item -LiteralPath $fp).LastWriteTimeUtc
            $score += [int]($details["mtime_$key"].Subtract([datetime]"1970-01-01").TotalDays)
        }
    }

  if (Test-Path -LiteralPath (Join-Path $Path "seen_ids.json")) { $score += 5 }

    return @{ Score = $score; Details = $details }
}

function Write-CompareReport {
    param($Name, $Path, $Result)
    Write-Host ""
    Write-Host "=== $Name : $Path ===" -ForegroundColor Cyan
    if ($Result.Score -lt 0) {
        Write-Host "  (유효한 Mail 프로젝트 아님 또는 경로 없음)" -ForegroundColor Yellow
        return
    }
    Write-Host ("  점수: {0}" -f $Result.Score)
    foreach ($k in $Result.Details.Keys) {
        Write-Host ("  {0}: {1}" -f $k, $Result.Details[$k])
    }
}

# ── 경로 확인 ─────────────────────────────────────────────────────────────
if (-not (Test-MailProjectRoot $PathA) -and -not (Test-MailProjectRoot $PathB)) {
    Write-Error "두 경로 모두 Mail 프로젝트가 아닙니다. -PathA / -PathB 를 확인하세요.`n  A=$PathA`n  B=$PathB"
}

$scoreA = Get-ProjectScore $PathA
$scoreB = Get-ProjectScore $PathB

Write-CompareReport "A" $PathA $scoreA
Write-CompareReport "B" $PathB $scoreB

if ($scoreA.Score -lt 0 -and $scoreB.Score -ge 0) {
    $keepPath = $PathB; $mergePath = $PathA
} elseif ($scoreB.Score -lt 0 -and $scoreA.Score -ge 0) {
    $keepPath = $PathA; $mergePath = $PathB
} elseif ($scoreA.Score -eq $scoreB.Score) {
    $mtimeA = (Get-Item -LiteralPath (Join-Path $PathA "monitor.py") -ErrorAction SilentlyContinue).LastWriteTimeUtc
    $mtimeB = (Get-Item -LiteralPath (Join-Path $PathB "monitor.py") -ErrorAction SilentlyContinue).LastWriteTimeUtc
    if ($mtimeA -ge $mtimeB) { $keepPath = $PathA; $mergePath = $PathB }
    else { $keepPath = $PathB; $mergePath = $PathA }
    Write-Host "`n점수 동점 → monitor.py 수정시각으로 판별" -ForegroundColor Yellow
} elseif ($scoreA.Score -gt $scoreB.Score) {
    $keepPath = $PathA; $mergePath = $PathB
} else {
    $keepPath = $PathB; $mergePath = $PathA
}

Write-Host ""
Write-Host "최신(유지): $keepPath" -ForegroundColor Green
Write-Host "구버전(병합 후 삭제): $mergePath" -ForegroundColor DarkYellow

if ($keepPath -eq $mergePath) {
    Write-Error "유지/병합 경로가 같습니다."
}

# ── 병합 (구 → 신, 신버전 파일은 덮어쓰지 않음) ───────────────────────────
$excludeDirs = @(".git", ".venv", "venv", "__pycache__", "node_modules", ".streamlit")
$excludeArgs = $excludeDirs | ForEach-Object { "/XD"; $_ }

Write-Host "`n[1/3] 파일 병합 (robocopy)..." -ForegroundColor Cyan
$robolog = Join-Path $env:TEMP ("mail_merge_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$robocopyArgs = @(
    $mergePath, $keepPath,
    "/E", "/XO", "/XN", "/XC",
    "/R:1", "/W:1",
    "/NFL", "/NDL", "/NJH", "/NJS",
    "/LOG:$robolog"
) + $excludeArgs

if ($PSCmdlet.ShouldProcess("$mergePath -> $keepPath", "robocopy merge")) {
    & robocopy @robocopyArgs | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        Write-Error "robocopy 실패 (exit $rc). 로그: $robolog"
    }
    Write-Host "  robocopy 완료 (exit $rc, 0-7=성공/경고). 로그: $robolog"
}

# ── git 동기화 (유지 폴더) ────────────────────────────────────────────────
if (Test-Path -LiteralPath (Join-Path $keepPath ".git")) {
    Write-Host "`n[2/3] Git 동기화 ($keepPath)..." -ForegroundColor Cyan
    Push-Location $keepPath
    try {
        git fetch $Remote $Branch 2>&1 | Write-Host
        $local = (git rev-parse HEAD).Trim()
        $remote = (git rev-parse "$Remote/$Branch" 2>$null)
        if (-not $remote) { throw "remote/$Branch 없음. git remote -v 확인" }
        $remote = $remote.Trim()
        Write-Host "  local : $local"
        Write-Host "  remote: $remote"
        if ($local -ne $remote) {
            $behind = (git rev-list --count "HEAD..$Remote/$Branch")
            $ahead  = (git rev-list --count "$Remote/$Branch..HEAD")
            Write-Host "  ahead=$ahead behind=$behind"
            if (-not $SkipGitPull) {
                if ($PSCmdlet.ShouldProcess($keepPath, "git pull --rebase")) {
                    git pull --rebase $Remote $Branch 2>&1 | Write-Host
                }
            } else {
                Write-Host "  (-SkipGitPull) pull 생략" -ForegroundColor Yellow
            }
        } else {
            Write-Host "  이미 origin/$Branch 와 동일합니다." -ForegroundColor Green
        }
        git status -sb
    } finally { Pop-Location }
} else {
    Write-Host "`n[2/3] 유지 폴더에 .git 없음 — git clone 권장:" -ForegroundColor Yellow
    Write-Host "  git clone https://github.com/pds2225/mail.git `"$keepPath`""
}

# ── 구버전 삭제 ───────────────────────────────────────────────────────────
Write-Host "`n[3/3] 구버전 폴더 삭제..." -ForegroundColor Cyan
if ($ForceDelete) {
    if ($PSCmdlet.ShouldProcess($mergePath, "Remove-Item -Recurse -Force")) {
        Remove-Item -LiteralPath $mergePath -Recurse -Force
        Write-Host "  삭제 완료: $mergePath" -ForegroundColor Green
    }
} else {
    Write-Host "  실제 삭제: -ForceDelete 스위치 추가 후 재실행" -ForegroundColor Yellow
    Write-Host "  예: ... -ForceDelete"
}

Write-Host "`n완료. 최신 작업 폴더: $keepPath" -ForegroundColor Green
