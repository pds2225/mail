@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if not exist "%~dp0scripts\fetch_notice_attachments.py" (
  echo.
  echo [ERROR] scripts folder not found.
  echo Run this inside the unzipped folder.
  echo The .cmd and scripts folder must be together.
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
echo [INFO] Python not found. Run 처음설치_한번만.cmd first.
echo.
pause
exit /b 1

:RUN
if not exist "%~dp0.attach_setup_ok" (
  echo.
  echo [INFO] First time? Run 처음설치_한번만.cmd first.
  echo Continuing anyway...
  echo.
)

echo.
echo ================================================
echo  Notice attachment downloader
echo  Paste notice URL, then Enter
echo  Empty line + Enter = quit
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
  echo Error. Try running 처음설치_한번만.cmd again.
  pause
  exit /b %ERR%
)

echo.
pause
exit /b 0
