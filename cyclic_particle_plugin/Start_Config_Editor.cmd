@echo off
setlocal
set "PLUGIN_DIR=%~dp0"
set "SCRIPT=%PLUGIN_DIR%ui\edit_config.ps1"

if not exist "%SCRIPT%" (
  echo Cannot find "%SCRIPT%"
  pause
  exit /b 1
)

powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
if errorlevel 1 (
  echo.
  echo Failed to start the config editor.
  pause
  exit /b 1
)
