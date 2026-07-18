$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
python -c "import sys; assert sys.version_info >= (3,9), 'Python 3.9+ required'"
if (!(Test-Path "$Root\.venv\Scripts\python.exe")) { python -m venv "$Root\.venv" }
& "$Root\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Root\.venv\Scripts\python.exe" -m pip install -e "$Root"
& "$Root\.venv\Scripts\python.exe" -c "from local_study_app.db import init_db; init_db()"
& "$Root\.venv\Scripts\python.exe" -m pytest
Write-Host "Install complete. MCP registration: codex mcp add local-study-app -- `"$Root\.venv\Scripts\python.exe`" -m local_study_app.mcp_server"
