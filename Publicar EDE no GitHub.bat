@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente de desenvolvimento ausente. Prepare o projeto com Python 3.11.
    pause
    exit /b 1
)
echo Publicacao publica do EDE: testes, snapshot permitido, ZIP e SHA-256.
echo Requer Git e GitHub CLI autenticado com gh auth login.
".venv\Scripts\python.exe" scripts\publish_release.py %*
set "EDE_EXIT=%ERRORLEVEL%"
if not "%EDE_EXIT%"=="0" echo Publicacao interrompida. Confira o erro acima.
if "%EDE_EXIT%"=="0" echo Operacao concluida.
pause
exit /b %EDE_EXIT%
