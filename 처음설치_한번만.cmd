@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ================================================
echo  지원사업 공고첨부 받기 — 처음 설치 (한 번만)
echo ================================================
echo.

if not exist "%~dp0scripts\setup_attach_downloader.py" (
  echo [오류] scripts 폴더를 찾을 수 없습니다.
  echo.
  echo ZIP을 풀었을 때 나온 폴더 안에서 실행하세요.
  echo cmd 파일과 scripts 폴더가 같은 위치에 있어야 합니다.
  echo.
  echo 잘못된 예: 바탕화면에 cmd만 복사
  echo 올바른 예: ZIP 풀린 폴더 열기 ^> 처음설치_한번만.cmd 실행
  echo.
  pause
  exit /b 1
)

echo  이 창이 닫힐 때까지 기다려 주세요. (1~3분, 인터넷 필요)
echo.

REM ---- Python 찾기 ----
set "PYEXE="
set "PYARGS="
if exist "%~dp0.venv\Scripts\python.exe" (
  set "PYEXE=%~dp0.venv\Scripts\python.exe"
  goto :HAVE_PYTHON
)

where py >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=py"
  set "PYARGS=-3"
  goto :HAVE_PYTHON
)

where python >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=python"
  goto :HAVE_PYTHON
)

echo [안내] Python 이 설치되어 있지 않습니다.
echo.
where winget >nul 2>&1
if errorlevel 1 goto :OPEN_PYTHON_DOWNLOAD

echo winget 으로 Python 3.12 설치를 시도합니다…
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :OPEN_PYTHON_DOWNLOAD

set "PYEXE="
set "PYARGS="
where py >nul 2>&1 && set "PYEXE=py" && set "PYARGS=-3"
if not defined PYEXE where python >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
  echo Python 설치 후 PC 재시작하고 이 파일을 다시 실행하세요.
  pause
  exit /b 1
)
goto :HAVE_PYTHON

:HAVE_PYTHON
echo Python: %PYEXE% %PYARGS%
echo.
if defined PYARGS (
  "%PYEXE%" %PYARGS% "%~dp0scripts\setup_attach_downloader.py"
) else (
  "%PYEXE%" "%~dp0scripts\setup_attach_downloader.py"
)
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo.
  echo 설치 실패. 위 빨간/흰 글씨를 캡처해서 보내 주세요.
  echo.
  echo 자주 나는 원인:
  echo  - Python 설치 시 "Add python.exe to PATH" 를 안 체크함
  echo  - 회사 PC 방화벽으로 pip 차단
  echo  - ZIP을 잘못 풀어 scripts 폴더가 없음
  echo.
  pause
  exit /b %ERR%
)
echo.
pause
exit /b 0

:OPEN_PYTHON_DOWNLOAD
echo.
echo Python 설치 페이지를 엽니다.
echo 설치할 때 반드시 체크: [v] Add python.exe to PATH
echo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
