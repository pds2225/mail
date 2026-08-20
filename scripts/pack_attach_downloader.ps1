# 비개발자 배포용 ZIP 생성
param(
    [Parameter(Mandatory = $false)]
    [string]$OutZip = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutZip) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    if (-not $desktop) { $desktop = Join-Path $env:USERPROFILE "Desktop" }
    $OutZip = Join-Path $desktop "지원사업_공고첨부_받기_설치.zip"
}

$stage = Join-Path $env:TEMP ("mail_attach_pack_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stage | Out-Null

$include = @(
    "지원사업 공고첨부_받기.cmd",
    "처음설치_한번만.cmd",
    "사용방법_공고첨부.txt",
    "monitor.py",
    "requirements.txt",
    "scripts\fetch_notice_attachments.py",
    "scripts\download_kstartup_targets.py",
    "scripts\setup_attach_downloader.py",
    "scripts\requirements-attach.txt",
    "scripts\notice_download_config.json",
    "mail_core",
    "config"
)

Write-Host "준비 중: $stage"
foreach ($item in $include) {
    $src = Join-Path $Root $item
    if (-not (Test-Path $src)) {
        Write-Warning "건너뜀(없음): $item"
        continue
    }
    $dest = Join-Path $stage $item
    $destParent = Split-Path -Parent $dest
    if (-not (Test-Path $destParent)) {
        New-Item -ItemType Directory -Path $destParent -Force | Out-Null
    }
    if (Test-Path $src -PathType Container) {
        Copy-Item -Path $src -Destination $dest -Recurse -Force
    } else {
        Copy-Item -Path $src -Destination $dest -Force
    }
}

# 비밀·캐시 제거
Get-ChildItem -Path $stage -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @(".env", ".env.local") -or $_.Name -eq "__pycache__" -or $_.Extension -eq ".pyc" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 배포용 설정: 개인 PC 경로 비움 (설치 스크립트가 다시 채움)
$configPath = Join-Path $stage "scripts\notice_download_config.json"
@{ out_dir = "" } | ConvertTo-Json | Set-Content -Path $configPath -Encoding UTF8

if (Test-Path $OutZip) { Remove-Item $OutZip -Force }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $OutZip -Force
Remove-Item $stage -Recurse -Force

Write-Host "ZIP 생성: $OutZip"
exit 0
