@echo off
rem Start the set designer. Creates the virtual environment on first run.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    python -m venv .venv
    rem --no-cache-dir: pip's cache path is too long for Windows with Store Python
    .venv\Scripts\python -m pip install --no-cache-dir -e .[dev]
)
.venv\Scripts\python -m setdesigner %*
