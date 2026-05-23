# 고객사 서류 inbox 1회 처리 — 실제 Google Sheets 기록 (dry_run=false)
. "$PSScriptRoot\_customer_intake_bootstrap.ps1"

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "  실제 Google Sheets 입력을 진행합니다." -ForegroundColor Yellow
Write-Host "  (.env 의 GOOGLE_SHEET_ID, 서비스 계정 필요)" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""
$confirm = Read-Host "계속하려면 Y 를 입력하세요 (그 외 취소)"
if ($confirm -ne "Y" -and $confirm -ne "y") {
    Write-Host "취소되었습니다." -ForegroundColor Gray
    exit 0
}

python -m customer_intake.watcher --once --dry-run false
exit $LASTEXITCODE
