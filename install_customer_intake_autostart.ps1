# PC login: register inbox watch (run once as Administrator)
#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$RepoRoot = "D:\mail"
Set-Location $RepoRoot
. "$RepoRoot\_customer_intake_bootstrap.ps1"

$WatchScript = Join-Path $RepoRoot "run_customer_intake_watch.ps1"
$TaskName = "MailRepo_CustomerIntakeWatch"

if (-not (Test-Path $WatchScript)) {
    Write-Error "Missing: $WatchScript"
}

$pythonExe = Get-CustomerIntakePython

$psExe = (Get-Command powershell.exe).Source
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchScript`""

$action = New-ScheduledTaskAction -Execute $psExe -Argument $arguments -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "customer_intake inbox watch" `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 4
$info = Get-ScheduledTaskInfo -TaskName $TaskName

Write-Host ""
Write-Host "OK: Scheduled task $TaskName" -ForegroundColor Green
Write-Host "  Python: $pythonExe"
Write-Host "  inbox: D:\customer_intake_inbox"
Write-Host "  log: D:\customer_intake_reports\watch.log"
Write-Host "  LastTaskResult: $($info.LastTaskResult)"
Write-Host "  Uninstall: .\uninstall_customer_intake_autostart.ps1" -ForegroundColor DarkGray
