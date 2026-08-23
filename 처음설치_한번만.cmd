@echo off
REM UTF-8 console for Hangul (must be before any Korean echo)
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo ================================================
echo  Notice attachment downloader - first-time setup
echo  (처음 설치 - 한 번만)
echo ================================================
echo.

if not exist "%~dp0scripts\setup_attach_downloader.py" (
  echo [ERROR] scripts folder not found.
  echo.
  echo Run this inside the unzipped folder.
  echo The .cmd file and the scripts folder must be together.
  echo.
  echo Wrong: copy only the .cmd to Desktop
  echo Right: open the unzipped folder, then run this file
  echo.
  pause
  exit /b 1
)

echo  Please wait until this window finishes. (1-3 min, needs internet)
echo.

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

echo [INFO] Python is not installed.
echo.
where winget >nul 2>&1
if errorlevel 1 goto :OPEN_PYTHON_DOWNLOAD

echo Trying to install Python 3.12 with winget...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :OPEN_PYTHON_DOWNLOAD

set "PYEXE="
set "PYARGS="
where py >nul 2>&1 && set "PYEXE=py" && set "PYARGS=-3"
if not defined PYEXE where python >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
  echo Python installed but not found yet. Restart PC, then run this again.
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
  echo Setup FAILED. Please screenshot the message above.
  echo.
  echo Common causes:
  echo  - Python install without "Add python.exe to PATH"
  echo  - Company firewall blocks pip
  echo  - ZIP extracted wrong / scripts folder missing
  echo.
  pause
  exit /b %ERR%
)
echo.
pause
exit /b 0

:OPEN_PYTHON_DOWNLOAD
echo.
echo Opening Python download page.
echo During install, CHECK: [v] Add python.exe to PATH
echo Then run this file again.
echo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
