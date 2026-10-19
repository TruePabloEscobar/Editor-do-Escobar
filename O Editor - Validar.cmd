@echo off
setlocal
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\validate_all.ps1" -ProjectRoot "%ROOT%." -ReadOnlyProbe
set "RC=%ERRORLEVEL%"
echo.
echo Validacao encerrada com codigo %RC%.
pause
exit /b %RC%
