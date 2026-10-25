@echo off
rem Start the set designer. Creates the virtual environment on first run.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    .venv\Scripts\python -m pip install -e .[dev]
)
.venv\Scripts\python -m setdesigner %*
