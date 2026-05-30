$ErrorActionPreference = "Stop"

$launcherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $launcherDir
$source = Join-Path $launcherDir "CyclicParticlePluginLauncher.cs"
$output = Join-Path $pluginRoot "CyclicParticlePlugin.exe"
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (-not (Test-Path -LiteralPath $csc)) {
    throw "C# compiler not found: $csc"
}
if (-not (Test-Path -LiteralPath $source)) {
    throw "Source file not found: $source"
}

& $csc /nologo /target:winexe /platform:anycpu /out:$output /reference:System.Windows.Forms.dll $source
if ($LASTEXITCODE -ne 0) {
    throw "csc failed with exit code $LASTEXITCODE"
}

Write-Host "Built launcher:"
Write-Host $output
