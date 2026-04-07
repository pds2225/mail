@echo off
chcp 65001 > nul
echo.
echo ===================================
echo  수출지원 모니터링 실행
echo ===================================
echo.

:: .env 파일에서 환경변수 로드
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set %%A=%%B
)

cd /d %~dp0
python monitor.py

echo.
echo 완료. 아무 키나 누르면 닫힙니다.
pause > nul
