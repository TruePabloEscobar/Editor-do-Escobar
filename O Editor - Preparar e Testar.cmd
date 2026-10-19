@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
if not exist "%PYTHON%" (
  echo ERRO: Python da virtual environment nao encontrado:
  echo %PYTHON%
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\bootstrap_validate_install.ps1" -ProjectRoot "%ROOT%." -InstallDependencies -InstallLauncher -RunValidation
set "RC=%ERRORLEVEL%"
echo.
echo Preparacao e testes encerrados com codigo %RC%.
echo Nenhuma mutacao no Resolve foi executada.
pause
exit /b %RC%
