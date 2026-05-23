# inbox 자동 감시 (백그라운드 상시 실행용)
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_customer_intake_bootstrap.ps1"

$python = Get-CustomerIntakePython
$logFile = "D:\customer_intake_reports\watch.log"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "`n=== watch start $stamp python=$python ==="

& $python -m customer_intake.watcher --watch --dry-run auto *>> $logFile
