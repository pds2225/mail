# inbox 1회 처리
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_customer_intake_bootstrap.ps1"

$python = Get-CustomerIntakePython
& $python -m customer_intake.watcher --once --dry-run auto
exit $LASTEXITCODE
