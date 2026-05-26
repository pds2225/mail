# PC 로그인 자동 감시 해제
#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

$TaskName = "MailRepo_CustomerIntakeWatch"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "자동 감시 해제 완료: $TaskName" -ForegroundColor Green
} else {
    Write-Host "등록된 작업 없음: $TaskName" -ForegroundColor Yellow
}
