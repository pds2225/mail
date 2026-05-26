# PC login: register inbox watch (run once as Administrator)
#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$RepoRoot = "D:\mail"
Set-Location $RepoRoot
. "$RepoRoot\_customer_intake_bootstrap.ps1"

$TaskName = "MailRepo_CustomerIntakeWatch"
$pythonExe = Get-CustomerIntakePython
$logFile = "D:\customer_intake_reports\watch.log"

$arguments = "-m customer_intake.watcher --watch --dry-run auto"

$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument $arguments `
    -WorkingDirectory $RepoRoot

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
Start-Sleep -Seconds 5
$info = Get-ScheduledTaskInfo -TaskName $TaskName

Write-Host ""
Write-Host "OK: $TaskName" -ForegroundColor Green
Write-Host "  Python: $pythonExe"
Write-Host "  inbox: D:\customer_intake_inbox"
Write-Host "  log: $logFile"
Write-Host "  LastTaskResult: $($info.LastTaskResult) (0=OK)"
Write-Host "  Uninstall: .\uninstall_customer_intake_autostart.ps1" -ForegroundColor DarkGray
