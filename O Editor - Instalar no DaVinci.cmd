@echo off
setlocal
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\install_launcher.ps1" -ProjectRoot "%ROOT%."
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\verify_launcher_installation.ps1" -ProjectRoot "%ROOT%."
  set "RC=%ERRORLEVEL%"
)
echo Scripts instalados em:
echo %APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility
echo Configuracao e launch-editor.cmd:
echo %APPDATA%\O Editor
echo.
echo Instalacao encerrada com codigo %RC%.
pause
exit /b %RC%
