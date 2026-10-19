@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_release.ps1" %*
set "EDE_EXIT=%ERRORLEVEL%"
if not "%EDE_EXIT%"=="0" echo A instalacao nao foi concluida. Confira a mensagem acima.
pause
exit /b %EDE_EXIT%
