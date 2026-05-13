param(
    [string]$PfcConsole = "D:\PFC\exe64\pfc3d600_console.exe",
    [string]$MainDataFile = "run_symmetric_pack.dat"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataPath = Join-Path $scriptDir $MainDataFile

if (-not (Test-Path -LiteralPath $PfcConsole)) {
    throw "PFC console not found: $PfcConsole"
}
if (-not (Test-Path -LiteralPath $dataPath)) {
    throw "Data file not found: $dataPath"
}

$quotedDataPath = $dataPath.Replace("\", "/")
$command = "program call '$quotedDataPath'"

Write-Host "PFC3D 6.0 console executable was found:"
Write-Host "  $PfcConsole"
Write-Host ""
Write-Host "On this installation, pfc3d600_console.exe starts an interactive prompt but does not"
Write-Host "consume normal PowerShell/cmd piped input. Use this command inside PFC Console:"
Write-Host ""
Write-Host "  $command"
Write-Host ""
Write-Host "For GUI automation, run:"
Write-Host "  .\send_to_pfc_gui.ps1"
