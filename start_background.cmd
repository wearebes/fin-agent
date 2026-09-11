@echo off
cd /d "%~dp0"
if not exist "%~dp0var" mkdir "%~dp0var"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=C:\ProgramData\Anaconda3\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%~dp0src"
if exist "%~dp0var\codex-owner.txt" (
  "%PYTHON%" -m fin_agent.interfaces.local_server --owner-file "%~dp0var\codex-owner.txt" --port 8000 --data-dir "%~dp0var\local-codex" --database-url "sqlite:///./var/fin_agent-local.db" >> "%~dp0var\finagent.log" 2>&1
) else (
  "%PYTHON%" -m fin_agent.bootstrap.cli api --host 127.0.0.1 --port 8000 >> "%~dp0var\finagent.log" 2>&1
)
