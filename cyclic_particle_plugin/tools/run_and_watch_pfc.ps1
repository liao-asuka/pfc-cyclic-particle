param(
    [string]$PfcGui = "D:\PFC\exe64\pfc3d600_gui.exe",
    [string]$PluginRoot = (Split-Path -Parent $PSScriptRoot),
    [int]$PollSeconds = 5,
    [int]$MaxMinutes = 120
)

$ErrorActionPreference = "Stop"
$RunDat = Join-Path $PluginRoot "pfc\run_plugin.dat"
$ConfigPath = Join-Path $PluginRoot "config\model_config.json"

if (-not (Test-Path -LiteralPath $RunDat)) {
    throw "Cannot find run_plugin.dat: $RunDat"
}
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Cannot find config: $ConfigPath"
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$caseDir = Join-Path $config.output_dir $config.model_name
$logPath = Join-Path $caseDir "run_log.txt"

$pfc = Get-Process -Name "pfc3d600_gui" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $pfc) {
    if (-not (Test-Path -LiteralPath $PfcGui)) {
        throw "PFC GUI not found: $PfcGui"
    }
    Write-Host "Starting PFC GUI..."
    Start-Process -FilePath $PfcGui | Out-Null
    Start-Sleep -Seconds 10
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $PluginRoot)
$bridge = Join-Path $projectRoot "tools\pfc_console_bridge.ps1"
if (-not (Test-Path -LiteralPath $bridge)) {
    $bridge = Join-Path (Get-Location) "tools\pfc_console_bridge.ps1"
}
if (-not (Test-Path -LiteralPath $bridge)) {
    throw "Cannot find pfc_console_bridge.ps1"
}

$runPath = $RunDat.Replace("\", "/")
$command = "program call '$runPath'"
Write-Host "Sending command to PFC:"
Write-Host "  $command"
& powershell -NoProfile -ExecutionPolicy Bypass -File $bridge -Command $command -WaitSeconds 8 -TailChars 16000 | Write-Host

$deadline = (Get-Date).AddMinutes($MaxMinutes)
$lastLogLength = -1

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds $PollSeconds

    if (Test-Path -LiteralPath $logPath) {
        $info = Get-Item -LiteralPath $logPath
        if ($info.Length -ne $lastLogLength) {
            $lastLogLength = $info.Length
            Write-Host ""
            Write-Host "---- run_log tail ----"
            Get-Content -LiteralPath $logPath -Tail 25 | Write-Host
        }
    }

    Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
    Add-Type -AssemblyName UIAutomationTypes -ErrorAction SilentlyContinue
    $pfc = Get-Process -Name "pfc3d600_gui" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $pfc) {
        Write-Host "PFC process exited."
        break
    }
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($pfc.MainWindowHandle)
    if ($null -eq $root) { continue }
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty,
        "itasca3d::TextOutput"
    )
    $output = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if ($null -eq $output) { continue }
    try {
        $vp = $output.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $text = $vp.Current.Value
    } catch {
        $tp = $output.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
        $text = $tp.DocumentRange.GetText(-1)
    }
    if ($text -match "Python error|Command Processing Error|Traceback|ERROR:") {
        Write-Host ""
        Write-Host "---- detected PFC error ----"
        if ($text.Length -gt 12000) {
            $text = $text.Substring($text.Length - 12000)
        }
        Write-Host $text
        exit 1
    }
    if ($text -match "pipeline complete") {
        Write-Host "Pipeline completed."
        exit 0
    }
}

Write-Host "Watcher finished without seeing completion."
