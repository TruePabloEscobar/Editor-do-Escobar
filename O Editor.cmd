@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if exist "%ROOT%python\python.exe" set "PYTHON=%ROOT%python\python.exe"
if exist "%ROOT%tools\ffmpeg\bin\ffmpeg.exe" set "PATH=%ROOT%tools\ffmpeg\bin;%PATH%"
set "PYTHONUTF8=1"
set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
set "LOGDIR=%ROOT%runtime\logs"
set "LOG=%LOGDIR%\double-click.log"
if not exist "%PYTHON%" (
  echo ERRO: Python da virtual environment nao encontrado: "%PYTHON%"
  pause
  exit /b 1
)
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
"%PYTHON%" -m o_editor %* >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo O Editor terminou com erro %RC%. Consulte:
  echo %LOG%
  pause
)
exit /b %RC%
