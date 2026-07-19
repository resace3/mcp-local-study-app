$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
python -c "import sys; assert sys.version_info >= (3,9), 'Python 3.9+ required'"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.9 or newer is required.' }
if (!(Test-Path "$Root\.venv\Scripts\python.exe")) { python -m venv "$Root\.venv" }
& "$Root\.venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Could not upgrade pip.' }
& "$Root\.venv\Scripts\python.exe" -m pip install -e "$Root" pytest httpx
if ($LASTEXITCODE -ne 0) { throw 'Could not install Study Sprout and its test dependencies.' }
& "$Root\.venv\Scripts\python.exe" -c "from local_study_app.db import init_db; init_db()"
if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the local database.' }
& "$Root\.venv\Scripts\python.exe" -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'The post-install test suite failed.' }
Write-Host "Install complete. MCP registration: codex mcp add local-study-app -- `"$Root\.venv\Scripts\python.exe`" -m local_study_app.mcp_server"
