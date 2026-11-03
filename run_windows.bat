@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -m venv .venv
  if errorlevel 1 goto :error
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
if errorlevel 1 goto :error
goto :eof
:error
echo AccessPath startup failed. Check that Python 3.10+ is installed and available as 'py'.
pause
