@echo off
chcp 65001 > nul
echo.
echo ===================================
echo  모니터링 관리 대시보드
echo ===================================
echo.

cd /d "%~dp0.."

:: .env 파일에서 환경변수 로드
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set %%A=%%B
)

python -m streamlit run streamlit_app.py

pause > nul
