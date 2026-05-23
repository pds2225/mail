# customer_intake 복구: 폴더 생성 + 감시 재등록 + inbox 1회 처리
#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_customer_intake_bootstrap.ps1"

Write-Host "`n=== Customer Intake Repair ===" -ForegroundColor Cyan

foreach ($d in @(
    "D:\customer_intake_inbox",
    "D:\customer_intake_done",
    "D:\customer_intake_failed",
    "D:\customer_intake_reports"
)) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
    Write-Host "[OK] $d"
}

& "$PSScriptRoot\install_customer_intake_autostart.ps1"

Write-Host "`n inbox 1회 처리 시도..." -ForegroundColor Cyan
& "$PSScriptRoot\run_customer_intake_once.ps1"

Write-Host "`nRepair 완료. doctor: .\doctor_customer_intake.ps1`n"
