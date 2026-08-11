@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ================================================
echo  지원사업 공고첨부 받기 — 처음 설치 (한 번만)
echo ================================================
echo.
echo  이 창이 닫힐 때까지 기다려 주세요. (1~3분)
echo.

REM ---- Python 찾기 (py 런처 → python) ----
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)

if defined PY goto :HAVE_PYTHON

echo [안내] 이 PC에 Python 이 없습니다.
echo.
where winget >nul 2>&1
if errorlevel 1 goto :OPEN_PYTHON_DOWNLOAD

echo winget 으로 Python 3.12 설치를 시도합니다…
echo (관리자 권한이 필요할 수 있습니다)
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :OPEN_PYTHON_DOWNLOAD

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo.
  echo Python 을 설치했지만 아직 인식되지 않습니다.
  echo 이 창을 닫고, PC 를 재시작한 뒤 이 파일을 다시 실행해 주세요.
  pause
  exit /b 1
)

:HAVE_PYTHON
echo Python 확인: %PY%
echo.
%PY% "%~dp0scripts\setup_attach_downloader.py"
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo 설치에 실패했습니다. 위 메시지를 캡처해 보내 주세요.
  pause
  exit /b %ERR%
)
echo.
pause
exit /b 0

:OPEN_PYTHON_DOWNLOAD
echo.
echo 브라우저에서 Python 설치 페이지를 엽니다.
echo 설치 화면에서 반드시 아래를 체크하세요:
echo   [v] Add python.exe to PATH
echo.
echo 설치가 끝나면 이 파일(처음설치_한번만.cmd)을 다시 실행하세요.
echo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
