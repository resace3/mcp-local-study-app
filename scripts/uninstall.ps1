param([switch]$PurgeData)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
& "$PSScriptRoot\stop.ps1"
$venv = [IO.Path]::GetFullPath((Join-Path $Root '.venv'))
if ($venv.StartsWith([IO.Path]::GetFullPath($Root)) -and (Test-Path -LiteralPath $venv)) {
  Remove-Item -LiteralPath $venv -Recurse -Force
  Write-Host 'Removed the project virtual environment.'
}
if ($PurgeData) {
  $data = [IO.Path]::GetFullPath((Join-Path ${env:LOCALAPPDATA} 'local-study-app'))
  $expected = [IO.Path]::GetFullPath("${env:LOCALAPPDATA}\local-study-app")
  if ($data -ne $expected) { throw 'Refusing to remove an unexpected data directory.' }
  if (Test-Path -LiteralPath $data) { Remove-Item -LiteralPath $data -Recurse -Force }
  Write-Host 'Removed the local database, media, exports, and logs.'
} else {
  Write-Host 'Study data was preserved. Re-run with -PurgeData to remove it.'
}
Write-Host 'The repository itself was not removed.'
