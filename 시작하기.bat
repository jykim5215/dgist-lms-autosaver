@echo off
chcp 65001 > nul
cd /d "%~dp0"

if exist "%~dp0.installed" goto run

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 goto fail
echo installed> "%~dp0.installed"

:run
start "" pythonw "%~dp0app.py"
exit /b 0

:fail
echo.
echo  설치에 실패했습니다. 위 메시지를 확인하고 다시 실행해 주세요.
pause
exit /b 1
