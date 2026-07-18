$Root = Split-Path -Parent $PSScriptRoot
$py = if (Test-Path "$Root\.venv\Scripts\python.exe") { "$Root\.venv\Scripts\python.exe" } else { (Get-Command python).Source }
Start-Process -FilePath $py -ArgumentList '-m','local_study_app.server' -WorkingDirectory $Root -WindowStyle Hidden
Write-Host 'Study app starting at http://127.0.0.1:8080'
