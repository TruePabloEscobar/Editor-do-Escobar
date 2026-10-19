@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
set "LOGDIR=%ROOT%runtime\logs"
set "LOG=%LOGDIR%\double-click-mock.log"
if not exist "%PYTHON%" (
  echo ERRO: Python da virtual environment nao encontrado: "%PYTHON%"
  pause
  exit /b 1
)
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
"%PYTHON%" -m o_editor --mock %* >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo O Editor Mock terminou com erro %RC%. Consulte:
  echo %LOG%
  pause
)
exit /b %RC%
