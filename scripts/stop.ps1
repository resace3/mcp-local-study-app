$p = Join-Path ${env:LOCALAPPDATA} 'local-study-app\server.pid'
if (Test-Path $p) { $id = Get-Content $p; Stop-Process -Id ([int]$id) -ErrorAction SilentlyContinue; Remove-Item $p -Force }
