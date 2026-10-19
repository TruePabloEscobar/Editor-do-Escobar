@echo off
setlocal
set "ROOT=%~dp0"
"%ROOT%.venv\Scripts\python.exe" "%ROOT%scripts\run_regression.py"
set "RC=%ERRORLEVEL%"
echo.
echo Testes encerrados com codigo %RC%.
pause
exit /b %RC%
