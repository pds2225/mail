# 자동시작 없이 지금 바로 inbox 감시만 켜기 (창 닫으면 종료)
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_customer_intake_bootstrap.ps1"

$python = Get-CustomerIntakePython
Write-Host "inbox 자동 감시 시작 (창을 닫으면 종료됩니다)" -ForegroundColor Cyan
Write-Host "  Python: $python"
Write-Host "  폴더: D:\customer_intake_inbox"
& $python -m customer_intake.watcher --watch --dry-run auto
