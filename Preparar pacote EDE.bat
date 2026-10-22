@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python do projeto ausente.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\package_release.py --public %*
set "EDE_EXIT=%ERRORLEVEL%"
pause
exit /b %EDE_EXIT%
