@echo off
cd /d "%~dp0"
echo Starting Fin Agent...
python -m fin_agent.bootstrap.cli api --reload
pause
