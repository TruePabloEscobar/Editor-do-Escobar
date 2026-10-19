@echo off
setlocal
cd /d "%~dp0"
echo Validando e enviando uma release em RASCUNHO para TruePabloEscobar/Editor-do-Escobar.
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\publish_release.py" %*
set "EDE_EXIT=%ERRORLEVEL%"
pause
exit /b %EDE_EXIT%
