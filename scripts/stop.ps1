$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$py = if (Test-Path "$Root\.venv\Scripts\python.exe") { "$Root\.venv\Scripts\python.exe" } else { (Get-Command python).Source }
$json = & $py -c "import json; from local_study_app.process import stop; print(json.dumps(stop()))"
if ($LASTEXITCODE -ne 0) { throw 'Could not run the Study Sprout lifecycle helper.' }
$result = $json | ConvertFrom-Json
if (!$result.success) { throw $result.error.message }
Write-Host $result.summary
