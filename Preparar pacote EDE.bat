@echo off
setlocal
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\package_release.py" %*
set "EDE_EXIT=%ERRORLEVEL%"
pause
exit /b %EDE_EXIT%
