@echo off
rem AI Clipper launcher: loads .env into the environment, then starts the server.
rem Usage: double-click start.bat (or run it from a terminal).
cd /d "%~dp0"
if exist .env (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)
echo Starting AI Clipper on http://127.0.0.1:8765 (Ctrl+C to stop)
python server.py
