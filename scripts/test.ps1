$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$py = if (Test-Path "$Root\.venv\Scripts\python.exe") { "$Root\.venv\Scripts\python.exe" } else { (Get-Command python).Source }
$sources = Get-ChildItem "$Root\local_study_app" -Filter '*.py' -File
& $py -m py_compile @($sources.FullName)
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'The test suite failed.' }
