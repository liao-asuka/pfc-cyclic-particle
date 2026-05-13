param(
    [string]$MainDataFile = "run_symmetric_pack.dat"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataPath = Join-Path $scriptDir $MainDataFile

if (-not (Test-Path -LiteralPath $dataPath)) {
    throw "Data file not found: $dataPath"
}

$pfc = Get-Process -Name "pfc3d600_gui" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $pfc) {
    throw "PFC3D GUI is not running. Open PFC3D first, then run this script."
}

$command = "program call '$($dataPath.Replace('\', '/'))'"
$shell = New-Object -ComObject WScript.Shell

Write-Host "Sending to PFC3D GUI Console:"
Write-Host "  $command"
Write-Host ""
Write-Host "Make sure the PFC Console input line is focused. The command will be sent in 3 seconds."
Start-Sleep -Seconds 3

[void]$shell.AppActivate($pfc.Id)
Start-Sleep -Milliseconds 500
$shell.SendKeys($command)
$shell.SendKeys("{ENTER}")
