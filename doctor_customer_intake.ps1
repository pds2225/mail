# customer_intake 상태 진단 (읽기 전용)
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_customer_intake_bootstrap.ps1"

Write-Host "`n=== Customer Intake Doctor ===" -ForegroundColor Cyan

$envPath = "D:\mail\.env"
if (Test-Path $envPath) {
    Write-Host "[OK] .env: $envPath" -ForegroundColor Green
} else {
    Write-Host "[--] .env 없음 (Mock/dry_run 으로 동작 가능)" -ForegroundColor Yellow
}

try {
    $py = Get-CustomerIntakePython
    Write-Host "[OK] Python: $py" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Python: $_" -ForegroundColor Red
}

foreach ($d in @(
    "D:\customer_intake_inbox",
    "D:\customer_intake_done",
    "D:\customer_intake_failed",
    "D:\customer_intake_reports"
)) {
    if (Test-Path $d) { Write-Host "[OK] $d" -ForegroundColor Green }
    else { Write-Host "[--] $d (첫 실행 시 생성)" -ForegroundColor Yellow }
}

$inboxFiles = @(Get-ChildItem "D:\customer_intake_inbox" -File -ErrorAction SilentlyContinue)
Write-Host "inbox 파일: $($inboxFiles.Count)개"

$task = Get-ScheduledTask -TaskName "MailRepo_CustomerIntakeWatch" -ErrorAction SilentlyContinue
if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName "MailRepo_CustomerIntakeWatch"
    Write-Host "[OK] 작업 스케줄러: $($task.State), LastResult=$($info.LastTaskResult)" -ForegroundColor Green
} else {
    Write-Host "[--] 작업 스케줄러 미등록 -> install_customer_intake_autostart.ps1" -ForegroundColor Yellow
}

$log = "D:\customer_intake_reports\watch.log"
if (Test-Path $log) {
    Write-Host "`n--- watch.log (last 8 lines) ---"
    Get-Content $log -Tail 8 -ErrorAction SilentlyContinue
}

Write-Host "`n상세: D:\mail\docs\CUSTOMER_INTAKE.md`n"
