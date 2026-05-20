param(
    [Parameter(Mandatory=$true)]
    [string]$Command,
    [int]$WaitSeconds = 2,
    [int]$TailChars = 12000,
    [switch]$NoEnter
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Input {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
}
"@

$pfc = Get-Process -Name "pfc3d600_gui" -ErrorAction Stop | Select-Object -First 1
$root = [System.Windows.Automation.AutomationElement]::FromHandle($pfc.MainWindowHandle)
if ($null -eq $root) {
    throw "Cannot attach to the PFC3D main window."
}

function Find-ByClass([string]$className) {
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty,
        $className
    )
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

$prompt = Find-ByClass "itasca3d::PromptLineEdit"
$output = Find-ByClass "itasca3d::TextOutput"
if ($null -eq $prompt) {
    throw "Cannot find PFC Console prompt input control."
}
if ($null -eq $output) {
    throw "Cannot find PFC Console output control."
}

$wshell = New-Object -ComObject WScript.Shell
[Win32Input]::ShowWindow($pfc.MainWindowHandle, 5) | Out-Null
[Win32Input]::SetForegroundWindow($pfc.MainWindowHandle) | Out-Null
[void]$wshell.AppActivate($pfc.Id)
Start-Sleep -Milliseconds 500
$rect = $prompt.Current.BoundingRectangle
$clickX = [int]($rect.Left + [Math]::Min(40, [Math]::Max(5, $rect.Width / 2)))
$clickY = [int]($rect.Top + ($rect.Height / 2))
[Win32Input]::SetCursorPos($clickX, $clickY) | Out-Null
[Win32Input]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
[Win32Input]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 200

if (-not $NoEnter) {
    [System.Windows.Forms.SendKeys]::SendWait("+{ESC}")
    Start-Sleep -Milliseconds 300
}

try {
    $valuePattern = $prompt.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $valuePattern.SetValue("")
} catch {}

[System.Windows.Forms.Clipboard]::SetText($Command)
[System.Windows.Forms.SendKeys]::SendWait("^a")
Start-Sleep -Milliseconds 100
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 100

if (-not $NoEnter) {
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
}

Start-Sleep -Seconds $WaitSeconds

$text = ""
try {
    $outputValue = $output.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $text = $outputValue.Current.Value
} catch {
    $textPattern = $output.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    $text = $textPattern.DocumentRange.GetText(-1)
}

if ($text.Length -gt $TailChars) {
    $text = $text.Substring($text.Length - $TailChars)
}

Write-Output $text
