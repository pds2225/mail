@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ================================================
echo  남에게 줄 배포용 ZIP 만들기
echo ================================================
echo.

set "OUT=%USERPROFILE%\Desktop\지원사업_공고첨부_받기_설치.zip"
if defined USERPROFILE if exist "%USERPROFILE%\OneDrive\바탕 화면\" (
  set "OUT=%USERPROFILE%\OneDrive\바탕 화면\지원사업_공고첨부_받기_설치.zip"
)

where powershell >nul 2>&1
if errorlevel 1 (
  echo PowerShell 이 없어 압축할 수 없습니다.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\pack_attach_downloader.ps1" -OutZip "%OUT%"
set "ERR=%ERRORLEVEL%"
echo.
if "%ERR%"=="0" (
  echo 완료: %OUT%
  echo 이 ZIP 파일을 상대에게 보내면 됩니다.
  echo 상대는 압축 풀고 「처음설치_한번만.cmd」 → 「지원사업 공고첨부_받기.cmd」 순서.
) else (
  echo 압축에 실패했습니다.
)
echo.
pause
exit /b %ERR%
