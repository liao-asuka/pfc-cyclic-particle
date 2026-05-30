param(
    [string]$InstallDir = "D:\ParaView 6.1.0"
)

$ErrorActionPreference = "Stop"
$zipUrl = "https://www.paraview.org/paraview-downloads/download.php?submit=Download&version=v6.1&type=binary&os=Windows&downloadFile=ParaView-6.1.0-Windows-Python3.12-msvc2017-AMD64.zip"
$downloadDir = Join-Path $env:TEMP "cyclic_particle_plugin"
$zipPath = Join-Path $downloadDir "ParaView-6.1.0-Windows.zip"
$extractParent = Split-Path -Parent $InstallDir

New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
New-Item -ItemType Directory -Force -Path $extractParent | Out-Null

Write-Host "Downloading ParaView 6.1.0..."
& curl.exe --ssl-no-revoke -L -C - -o $zipPath $zipUrl
if ($LASTEXITCODE -ne 0) {
    throw "curl failed with exit code $LASTEXITCODE"
}

$tempExtract = Join-Path $downloadDir "extract"
if (Test-Path $tempExtract) {
    Remove-Item -LiteralPath $tempExtract -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $tempExtract | Out-Null

Write-Host "Extracting..."
Expand-Archive -LiteralPath $zipPath -DestinationPath $tempExtract -Force
$extracted = Get-ChildItem -LiteralPath $tempExtract -Directory | Select-Object -First 1
if ($null -eq $extracted) {
    throw "No ParaView directory was found in the zip archive."
}

if (Test-Path $InstallDir) {
    Write-Host "Install directory already exists: $InstallDir"
    Write-Host "Leaving it untouched."
} else {
    Move-Item -LiteralPath $extracted.FullName -Destination $InstallDir
}

$pvpython = Join-Path $InstallDir "bin\pvpython.exe"
if (-not (Test-Path $pvpython)) {
    throw "pvpython.exe was not found at $pvpython"
}

Write-Host "ParaView installed."
Write-Host "Set paraview.pvpython_path to:"
Write-Host $pvpython
