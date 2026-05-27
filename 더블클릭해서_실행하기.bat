@echo off
title 아파트 실거래 통계 대시보드 실행기
chcp 65001 > nul
echo ==================================================
echo   아파트 실거래 통계 대시보드 서버 및 화면 시작
echo ==================================================
echo.

:: 포트 8000이 사용 중인지 확인
netstat -ano | findstr :8000 > nul
if %errorlevel% equ 0 (
    echo [정보] 이미 대시보드 백엔드 서버가 실행 중입니다.
    echo [정보] 브라우저에서 대시보드 화면을 엽니다...
    start http://localhost:8000
) else (
    echo [정보] 백엔드 서버가 중지되어 있습니다. 서버를 실행합니다...
    start /b python main.py
    echo [정보] 서버 초기화 대기 중 (2초)...
    timeout /t 2 /nobreak > nul
    start http://localhost:8000
)

echo.
echo [성공] 대시보드 실행이 완료되었습니다! 이 창은 닫으셔도 됩니다.
timeout /t 3 > nul
exit
