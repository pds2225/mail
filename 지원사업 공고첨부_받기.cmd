@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

REM ---- 가상환경 Python 우선, 없으면 시스템 Python ----
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo.
  echo [안내] 아직 설치가 안 됐습니다.
  echo 같은 폴더의 「처음설치_한번만.cmd」 를 먼저 더블클릭하세요.
  echo.
  pause
  exit /b 1
)

REM 설치 마커 없으면 설치 유도 (강제 중단은 하지 않음 — 이미 패키지 있는 PC 대비)
if not exist "%~dp0.attach_setup_ok" (
  echo.
  echo [안내] 첫 실행이면 「처음설치_한번만.cmd」 를 먼저 실행하는 것이 안전합니다.
  echo 계속 진행합니다…
  echo.
)

echo.
echo ================================================
echo  지원사업 공고첨부 자동 다운로드
echo  공고 상세 페이지 주소를 붙여넣고 Enter
echo  끝내려면 빈 줄에서 Enter
echo ================================================
echo.

%PY% "%~dp0scripts\fetch_notice_attachments.py" --interactive --open --notify --quiet
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo.
  echo 실행 중 문제가 났습니다. 위 메시지를 확인해 주세요.
  echo 해결이 안 되면 「처음설치_한번만.cmd」 를 다시 실행해 보세요.
  pause
  exit /b %ERR%
)

echo.
pause
exit /b 0
