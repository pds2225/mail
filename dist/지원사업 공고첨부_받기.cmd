@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "%~dp0scripts\fetch_notice_attachments.py" (
  echo.
  echo [오류] scripts 폴더를 찾을 수 없습니다.
  echo ZIP을 풀었을 때 나온 폴더 안에서 실행하세요.
  echo cmd 와 scripts 가 같은 폴더에 있어야 합니다.
  echo.
  pause
  exit /b 1
)

set "PYEXE="
set "PYARGS="
if exist "%~dp0.venv\Scripts\python.exe" (
  set "PYEXE=%~dp0.venv\Scripts\python.exe"
  goto :RUN
)

where py >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=py"
  set "PYARGS=-3"
  goto :RUN
)

where python >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=python"
  goto :RUN
)

echo.
echo [안내] Python 이 없거나 설치가 안 됐습니다.
echo 「처음설치_한번만.cmd」 를 먼저 더블클릭하세요.
echo.
pause
exit /b 1

:RUN
if not exist "%~dp0.attach_setup_ok" (
  echo.
  echo [안내] 처음이면 「처음설치_한번만.cmd」 를 먼저 실행하세요.
  echo 계속 진행합니다…
  echo.
)

echo.
echo ================================================
echo  지원사업 공고첨부 자동 다운로드
echo  공고 상세 페이지 주소 붙여넣기 ^> Enter
echo  끝내려면 빈 줄에서 Enter
echo ================================================
echo.

if defined PYARGS (
  "%PYEXE%" %PYARGS% "%~dp0scripts\fetch_notice_attachments.py" --interactive --open --notify --quiet
) else (
  "%PYEXE%" "%~dp0scripts\fetch_notice_attachments.py" --interactive --open --notify --quiet
)
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo 실행 오류. 「처음설치_한번만.cmd」 를 다시 실행해 보세요.
  pause
  exit /b %ERR%
)

echo.
pause
exit /b 0
