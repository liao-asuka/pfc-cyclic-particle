param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginRoot = Split-Path -Parent $ScriptRoot
$ConfigPath = Join-Path $PluginRoot "config\model_config.json"
$ExamplePath = Join-Path $PluginRoot "config\model_config.example.json"
$RunPluginPath = Join-Path $PluginRoot "pfc\run_plugin.dat"

function Load-Config {
    $path = $ConfigPath
    if (-not (Test-Path -LiteralPath $path)) {
        $path = $ExamplePath
    }
    $cfg = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if ($null -eq $cfg.pfc) {
        $cfg | Add-Member -MemberType NoteProperty -Name pfc -Value ([pscustomobject]@{ gui_path = "D:/PFC/exe64/pfc3d600_gui.exe" })
    }
    return $cfg
}

function Test-ConfigObject {
    param($Config)
    $errors = New-Object System.Collections.Generic.List[string]
    if ([string]::IsNullOrWhiteSpace($Config.model_name)) { $errors.Add("model_name is required") }
    if ($Config.unit -ne "mm") { $errors.Add("unit must be mm") }
    foreach ($axis in @("x","y","z")) {
        try {
            $value = [double]$Config.domain.$axis
            if ($value -le 0.0) { $errors.Add("domain.$axis must be positive") }
        } catch {
            $errors.Add("domain.$axis must be numeric")
        }
    }
    try {
        $por = [double]$Config.target_porosity
        if ($por -le 0.01 -or $por -ge 0.95) { $errors.Add("target_porosity must be between 0.01 and 0.95") }
    } catch {
        $errors.Add("target_porosity must be numeric")
    }
    if (@("particles","fluid","both") -notcontains $Config.output_mode) { $errors.Add("output_mode is invalid") }
    if ([string]::IsNullOrWhiteSpace($Config.output_dir)) { $errors.Add("output_dir is required") }
    $bins = @($Config.radius_bins)
    if ($bins.Count -lt 1 -or $bins.Count -gt 5) { $errors.Add("radius_bins must contain 1 to 5 bins") }
    $sum = 0.0
    for ($i = 0; $i -lt $bins.Count; $i++) {
        $bin = $bins[$i]
        try {
            $rMin = [double]$bin.r_min
            $rMax = [double]$bin.r_max
            $vf = [double]$bin.volume_fraction
            if ([string]::IsNullOrWhiteSpace($bin.name)) { $errors.Add("radius_bins[$i].name is required") }
            if ($rMin -le 0.0 -or $rMax -le 0.0 -or $rMin -ge $rMax) { $errors.Add("radius_bins[$i] has invalid radius range") }
            if ($vf -lt 0.0) { $errors.Add("radius_bins[$i].volume_fraction must be non-negative") }
            $sum += $vf
        } catch {
            $errors.Add("radius_bins[$i] contains non-numeric values")
        }
    }
    if ([math]::Abs($sum - 1.0) -gt 0.000001) { $errors.Add(("volume fractions must sum to 1.0, got {0:N8}" -f $sum)) }
    return $errors
}

if ($ValidateOnly) {
    $cfg = Load-Config
    $errors = Test-ConfigObject $cfg
    if ($errors.Count -gt 0) {
        Write-Host "CONFIG INVALID"
        $errors | ForEach-Object { Write-Host $_ }
        exit 1
    }
    Write-Host "CONFIG OK: $ConfigPath"
    exit 0
}

Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName WindowsBase
Add-Type -AssemblyName System.Windows.Forms

$cfg = Load-Config

$window = New-Object System.Windows.Window
$window.Title = "Cyclic Particle PFC Plugin"
$window.Width = 920
$window.Height = 820
$window.MinWidth = 820
$window.MinHeight = 680
$window.WindowStartupLocation = "CenterScreen"
$window.Background = "#F5F7FA"

$main = New-Object System.Windows.Controls.DockPanel
$window.Content = $main

$header = New-Object System.Windows.Controls.Border
$header.Background = "#1F2937"
$header.Padding = "22,16,22,16"
[System.Windows.Controls.DockPanel]::SetDock($header, "Top")
$main.Children.Add($header) | Out-Null

$headerStack = New-Object System.Windows.Controls.StackPanel
$header.Child = $headerStack
$title = New-Object System.Windows.Controls.TextBlock
$title.Text = "Cyclic Particle PFC Plugin"
$title.Foreground = "White"
$title.FontSize = 24
$title.FontWeight = "SemiBold"
$subtitle = New-Object System.Windows.Controls.TextBlock
$subtitle.Text = "Edit model parameters, save the config, and launch PFC generation from this window."
$subtitle.Foreground = "#CBD5E1"
$subtitle.Margin = "0,5,0,0"
$subtitle.FontSize = 13
$headerStack.Children.Add($title) | Out-Null
$headerStack.Children.Add($subtitle) | Out-Null

$footer = New-Object System.Windows.Controls.Border
$footer.Background = "#FFFFFF"
$footer.BorderBrush = "#D6DAE0"
$footer.BorderThickness = "0,1,0,0"
$footer.Padding = "16"
[System.Windows.Controls.DockPanel]::SetDock($footer, "Bottom")
$main.Children.Add($footer) | Out-Null

$footerGrid = New-Object System.Windows.Controls.Grid
$footerGrid.ColumnDefinitions.Add((New-Object System.Windows.Controls.ColumnDefinition)) | Out-Null
$footerGrid.ColumnDefinitions.Add((New-Object System.Windows.Controls.ColumnDefinition -Property @{ Width = "Auto" })) | Out-Null
$footer.Child = $footerGrid

$statusText = New-Object System.Windows.Controls.TextBlock
$statusText.Text = "Ready"
$statusText.VerticalAlignment = "Center"
$statusText.Foreground = "#4B5563"
[System.Windows.Controls.Grid]::SetColumn($statusText, 0)
$footerGrid.Children.Add($statusText) | Out-Null

$buttonPanel = New-Object System.Windows.Controls.StackPanel
$buttonPanel.Orientation = "Horizontal"
$buttonPanel.HorizontalAlignment = "Right"
[System.Windows.Controls.Grid]::SetColumn($buttonPanel, 1)
$footerGrid.Children.Add($buttonPanel) | Out-Null

$scroll = New-Object System.Windows.Controls.ScrollViewer
$scroll.VerticalScrollBarVisibility = "Auto"
$main.Children.Add($scroll) | Out-Null

$root = New-Object System.Windows.Controls.StackPanel
$root.Margin = "18"
$scroll.Content = $root

function New-Button {
    param($Text, $Width, $Background = "#2563EB", $Foreground = "White")
    $button = New-Object System.Windows.Controls.Button
    $button.Content = $Text
    $button.Width = $Width
    $button.Height = 34
    $button.Margin = "8,0,0,0"
    $button.Background = $Background
    $button.Foreground = $Foreground
    $button.BorderBrush = $Background
    $button.Padding = "10,4,10,4"
    return $button
}

function Add-Section {
    param($Title, $Description)
    $border = New-Object System.Windows.Controls.Border
    $border.Background = "White"
    $border.BorderBrush = "#D6DAE0"
    $border.BorderThickness = "1"
    $border.CornerRadius = "8"
    $border.Padding = "16"
    $border.Margin = "0,0,0,14"
    $stack = New-Object System.Windows.Controls.StackPanel
    $border.Child = $stack
    $sectionTitle = New-Object System.Windows.Controls.TextBlock
    $sectionTitle.Text = $Title
    $sectionTitle.FontSize = 17
    $sectionTitle.FontWeight = "SemiBold"
    $sectionTitle.Foreground = "#111827"
    $stack.Children.Add($sectionTitle) | Out-Null
    if (-not [string]::IsNullOrWhiteSpace($Description)) {
        $desc = New-Object System.Windows.Controls.TextBlock
        $desc.Text = $Description
        $desc.Foreground = "#6B7280"
        $desc.FontSize = 12
        $desc.TextWrapping = "Wrap"
        $desc.Margin = "0,3,0,12"
        $stack.Children.Add($desc) | Out-Null
    }
    $root.Children.Add($border) | Out-Null
    return $stack
}

function Add-Field {
    param($Parent, $Label, $Hint, $Value, $Width = 210)
    $panel = New-Object System.Windows.Controls.StackPanel
    $panel.Margin = "0,0,14,12"
    $text = New-Object System.Windows.Controls.TextBlock
    $text.Text = $Label
    $text.FontWeight = "SemiBold"
    $text.Foreground = "#374151"
    $hintText = New-Object System.Windows.Controls.TextBlock
    $hintText.Text = $Hint
    $hintText.FontSize = 11
    $hintText.Foreground = "#6B7280"
    $hintText.TextWrapping = "Wrap"
    $hintText.Margin = "0,1,0,4"
    $box = New-Object System.Windows.Controls.TextBox
    $box.Text = [string]$Value
    $box.Width = $Width
    $box.Height = 28
    $box.ToolTip = $Hint
    $panel.Children.Add($text) | Out-Null
    $panel.Children.Add($hintText) | Out-Null
    $panel.Children.Add($box) | Out-Null
    $Parent.Children.Add($panel) | Out-Null
    return $box
}

function Add-Row {
    param($Parent)
    $row = New-Object System.Windows.Controls.WrapPanel
    $row.Margin = "0,0,0,4"
    $Parent.Children.Add($row) | Out-Null
    return $row
}

function Add-PathField {
    param($Parent, $Label, $Hint, $Value, $BrowseMode)
    $panel = New-Object System.Windows.Controls.StackPanel
    $panel.Margin = "0,0,0,12"
    $text = New-Object System.Windows.Controls.TextBlock
    $text.Text = $Label
    $text.FontWeight = "SemiBold"
    $text.Foreground = "#374151"
    $hintText = New-Object System.Windows.Controls.TextBlock
    $hintText.Text = $Hint
    $hintText.FontSize = 11
    $hintText.Foreground = "#6B7280"
    $hintText.Margin = "0,1,0,4"
    $hintText.TextWrapping = "Wrap"
    $dock = New-Object System.Windows.Controls.DockPanel
    $box = New-Object System.Windows.Controls.TextBox
    $box.Text = [string]$Value
    $box.Height = 28
    $button = New-Button "Browse" 82 "#E5E7EB" "#111827"
    [System.Windows.Controls.DockPanel]::SetDock($button, "Right")
    $dock.Children.Add($button) | Out-Null
    $dock.Children.Add($box) | Out-Null
    $panel.Children.Add($text) | Out-Null
    $panel.Children.Add($hintText) | Out-Null
    $panel.Children.Add($dock) | Out-Null
    $Parent.Children.Add($panel) | Out-Null
    $handler = {
        try {
            if ($BrowseMode -eq "Folder") {
                $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
                $dialog.Description = "Select output directory"
                $dialog.ShowNewFolderButton = $true
                $current = $box.Text.Replace("/", "\")
                if (Test-Path -LiteralPath $current) {
                    $dialog.SelectedPath = $current
                }
                $result = $dialog.ShowDialog()
                if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
                    $box.Text = $dialog.SelectedPath.Replace("\", "/")
                }
            } else {
                $dialog = New-Object Microsoft.Win32.OpenFileDialog
                $dialog.Filter = "Executable (*.exe)|*.exe|All files (*.*)|*.*"
                $current = $box.Text.Replace("/", "\")
                if (Test-Path -LiteralPath $current) {
                    $dialog.FileName = $current
                    $dialog.InitialDirectory = Split-Path -Parent $current
                } else {
                    $parent = Split-Path -Parent $current -ErrorAction SilentlyContinue
                    if ($parent -and (Test-Path -LiteralPath $parent)) {
                        $dialog.InitialDirectory = $parent
                    }
                }
                if ($dialog.ShowDialog($window) -eq $true) {
                    $box.Text = $dialog.FileName.Replace("\", "/")
                }
            }
        } catch {
            [System.Windows.MessageBox]::Show(
                "Failed to open the browse dialog:`n`n" + [string]$_.Exception.Message,
                "Browse failed"
            ) | Out-Null
        }
    }.GetNewClosure()
    $button.Add_Click($handler)
    return $box
}

$basic = Add-Section "Model" "Set final RVE size and porosity. All lengths are in mm."
$row = Add-Row $basic
$modelName = Add-Field $row "Model name" "Used as the output case folder name." $cfg.model_name 210
$porosity = Add-Field $row "Target porosity" "Particle model target porosity, for example 0.40." $cfg.target_porosity 160
$domainX = Add-Field $row "Domain X" "RVE length in x direction." $cfg.domain.x 130
$domainY = Add-Field $row "Domain Y" "RVE length in y direction." $cfg.domain.y 130
$domainZ = Add-Field $row "Domain Z" "RVE length in z direction." $cfg.domain.z 130

$runSection = Add-Section "Output and Run" "Choose outputs, periodic axes, and external program paths. The run button saves before sending the PFC command."
$modePanel = Add-Row $runSection
$modeBlock = New-Object System.Windows.Controls.StackPanel
$modeBlock.Margin = "0,0,14,12"
$modeLabel = New-Object System.Windows.Controls.TextBlock
$modeLabel.Text = "Output mode"
$modeLabel.FontWeight = "SemiBold"
$modeHint = New-Object System.Windows.Controls.TextBlock
$modeHint.Text = "particles: particle STL only; fluid: fluid STL only; both: all outputs."
$modeHint.Foreground = "#6B7280"
$modeHint.FontSize = 11
$modeHint.Margin = "0,1,0,4"
$modeHint.TextWrapping = "Wrap"
$mode = New-Object System.Windows.Controls.ComboBox
$mode.Width = 180
$mode.Height = 28
@("particles","fluid","both") | ForEach-Object { $mode.Items.Add($_) | Out-Null }
$mode.SelectedItem = [string]$cfg.output_mode
$modeBlock.Children.Add($modeLabel) | Out-Null
$modeBlock.Children.Add($modeHint) | Out-Null
$modeBlock.Children.Add($mode) | Out-Null
$modePanel.Children.Add($modeBlock) | Out-Null

$axisBlock = New-Object System.Windows.Controls.StackPanel
$axisBlock.Margin = "0,0,14,12"
$axisLabel = New-Object System.Windows.Controls.TextBlock
$axisLabel.Text = "Periodic axes"
$axisLabel.FontWeight = "SemiBold"
$axisHint = New-Object System.Windows.Controls.TextBlock
$axisHint.Text = "Selected directions are generated as cyclic particle boundaries."
$axisHint.Foreground = "#6B7280"
$axisHint.FontSize = 11
$axisHint.Margin = "0,1,0,4"
$axisHint.TextWrapping = "Wrap"
$axisChecks = New-Object System.Windows.Controls.StackPanel
$axisChecks.Orientation = "Horizontal"
$checkX = New-Object System.Windows.Controls.CheckBox
$checkX.Content = "x"
$checkX.Margin = "0,0,12,0"
$checkX.IsChecked = @($cfg.periodic_axes) -contains "x"
$checkY = New-Object System.Windows.Controls.CheckBox
$checkY.Content = "y"
$checkY.Margin = "0,0,12,0"
$checkY.IsChecked = @($cfg.periodic_axes) -contains "y"
$checkZ = New-Object System.Windows.Controls.CheckBox
$checkZ.Content = "z"
$checkZ.Margin = "0,0,12,0"
$checkZ.IsChecked = @($cfg.periodic_axes) -contains "z"
$axisChecks.Children.Add($checkX) | Out-Null
$axisChecks.Children.Add($checkY) | Out-Null
$axisChecks.Children.Add($checkZ) | Out-Null
$axisBlock.Children.Add($axisLabel) | Out-Null
$axisBlock.Children.Add($axisHint) | Out-Null
$axisBlock.Children.Add($axisChecks) | Out-Null
$modePanel.Children.Add($axisBlock) | Out-Null

$outputDir = Add-PathField $runSection "Output directory" "The plugin creates one case folder here using the model name." $cfg.output_dir "Folder"
$pfcGuiPath = Add-PathField $runSection "PFC GUI path" "Used by Save and Run PFC. Default is D:/PFC/exe64/pfc3d600_gui.exe." $cfg.pfc.gui_path "File"
$pvPath = Add-PathField $runSection "ParaView pvpython path" "Required only when output mode is fluid or both." $cfg.paraview.pvpython_path "File"

$binsSection = Add-Section "Particle Size Distribution" "Define 1 to 5 radius bins. Volume fractions must add to 1.0."
$binGrid = New-Object System.Windows.Controls.Grid
$binGrid.Margin = "0,2,0,0"
@("2*","1*","1*","1.2*") | ForEach-Object {
    $col = New-Object System.Windows.Controls.ColumnDefinition
    $col.Width = $_
    $binGrid.ColumnDefinitions.Add($col)
}
for ($r = 0; $r -lt 6; $r++) {
    $rowDef = New-Object System.Windows.Controls.RowDefinition
    $rowDef.Height = "Auto"
    $binGrid.RowDefinitions.Add($rowDef)
}
$headers = @("Name","r min (mm)","r max (mm)","Volume fraction")
for ($c = 0; $c -lt 4; $c++) {
    $headerText = New-Object System.Windows.Controls.TextBlock
    $headerText.Text = $headers[$c]
    $headerText.FontWeight = "SemiBold"
    $headerText.Foreground = "#374151"
    $headerText.Margin = "3,0,3,4"
    [System.Windows.Controls.Grid]::SetRow($headerText, 0)
    [System.Windows.Controls.Grid]::SetColumn($headerText, $c)
    $binGrid.Children.Add($headerText) | Out-Null
}
$binBoxes = @()
$jsonHeaders = @("name","r_min","r_max","volume_fraction")
for ($r = 0; $r -lt 5; $r++) {
    $rowBoxes = @()
    $source = $null
    if ($r -lt @($cfg.radius_bins).Count) { $source = @($cfg.radius_bins)[$r] }
    for ($c = 0; $c -lt 4; $c++) {
        $box = New-Object System.Windows.Controls.TextBox
        $box.Margin = "3"
        $box.Height = 28
        if ($source -ne $null) { $box.Text = [string]$source.($jsonHeaders[$c]) }
        [System.Windows.Controls.Grid]::SetRow($box, $r + 1)
        [System.Windows.Controls.Grid]::SetColumn($box, $c)
        $binGrid.Children.Add($box) | Out-Null
        $rowBoxes += $box
    }
    $binBoxes += ,$rowBoxes
}
$binsSection.Children.Add($binGrid) | Out-Null

$fluid = Add-Section "Fluid Surface" "Controls the smoothed level-set STL for Fluent Meshing. Smoothness and cyclic-face correspondence are prioritized."
$row = Add-Row $fluid
$radiusShrink = Add-Field $row "Radius shrink" "Slightly shrinks particles before fluid-surface extraction." $cfg.fluid_surface.radius_shrink 140
$gridSpacing = Add-Field $row "Grid spacing" "Smaller keeps more detail but creates more STL triangles." $cfg.fluid_surface.grid_spacing 140
$smoothSigma = Add-Field $row "Smooth sigma" "Larger values make the inner fluid surface smoother." $cfg.fluid_surface.smooth_sigma_cells 140
$smoothClip = Add-Field $row "Smooth clip" "Distance range used before smoothing the solid field." $cfg.fluid_surface.smooth_clip_distance 140
$levelOffset = Add-Field $row "Level offset" "Small offset for the extracted level-set surface." $cfg.fluid_surface.level_offset 140

function Build-ConfigFromUi {
    $axes = @()
    if ($checkX.IsChecked) { $axes += "x" }
    if ($checkY.IsChecked) { $axes += "y" }
    if ($checkZ.IsChecked) { $axes += "z" }
    $bins = @()
    foreach ($row in $binBoxes) {
        if (-not [string]::IsNullOrWhiteSpace($row[0].Text)) {
            $bins += [ordered]@{
                name = $row[0].Text.Trim()
                r_min = [double]$row[1].Text
                r_max = [double]$row[2].Text
                volume_fraction = [double]$row[3].Text
            }
        }
    }
    return [ordered]@{
        model_name = $modelName.Text.Trim()
        unit = "mm"
        domain = [ordered]@{
            x = [double]$domainX.Text
            y = [double]$domainY.Text
            z = [double]$domainZ.Text
        }
        target_porosity = [double]$porosity.Text
        periodic_axes = $axes
        output_mode = [string]$mode.SelectedItem
        output_dir = $outputDir.Text.Trim().Replace("\", "/")
        radius_bins = $bins
        fluid_surface = [ordered]@{
            enabled = $true
            radius_shrink = [double]$radiusShrink.Text
            grid_spacing = [double]$gridSpacing.Text
            smooth_sigma_cells = [double]$smoothSigma.Text
            smooth_clip_distance = [double]$smoothClip.Text
            level_offset = [double]$levelOffset.Text
        }
        paraview = [ordered]@{
            pvpython_path = $pvPath.Text.Trim().Replace("\", "/")
        }
        pfc = [ordered]@{
            gui_path = $pfcGuiPath.Text.Trim().Replace("\", "/")
        }
    }
}

function Save-ConfigFromUi {
    $newCfg = Build-ConfigFromUi
    $errors = Test-ConfigObject ([pscustomobject]$newCfg)
    if ($errors.Count -gt 0) {
        throw ($errors -join "`n")
    }
    $json = $newCfg | ConvertTo-Json -Depth 8
    Set-Content -LiteralPath $ConfigPath -Value $json -Encoding UTF8
        $statusText.Text = "Saved: $ConfigPath"
    return $newCfg
}

function Update-PfcEntryFile {
    $scriptsDir = (Join-Path $PluginRoot "scripts").Replace("\", "\\")
    $configPath = (Join-Path $PluginRoot "config\model_config.json").Replace("\", "\\")
    $bootstrapPath = Join-Path $PluginRoot "scripts\run_plugin_bootstrap.py"
    $bootstrapText = @"
from __future__ import print_function

import os
import sys
import importlib


SCRIPT_DIR = r"$scriptsDir"
CONFIG_PATH = r"$configPath"

os.environ["CYCLIC_PARTICLE_PLUGIN_SCRIPT_DIR"] = SCRIPT_DIR

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

for module_name in ("run_pipeline", "plugin_common"):
    if module_name in sys.modules:
        del sys.modules[module_name]

run_pipeline = importlib.import_module("run_pipeline")


run_pipeline.main(CONFIG_PATH)
"@
    Set-Content -LiteralPath $bootstrapPath -Value $bootstrapText -Encoding ASCII

    $pipelinePath = $bootstrapPath.Replace("\", "/")
    $entryText = @"
; Cyclic Particle Plugin entry for PFC3D 6.x
; This file is updated by the config editor before each run.

program call '$pipelinePath'
"@
    Set-Content -LiteralPath $RunPluginPath -Value $entryText -Encoding ASCII
}

function Find-PfcPrompt {
    param($Process)
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $rootElement = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    if ($null -eq $rootElement) { return $null }
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ClassNameProperty,
        "itasca3d::PromptLineEdit"
    )
    return $rootElement.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Send-PfcCommand {
    param($PfcGui, $Command)

    if (-not (Test-Path -LiteralPath $PfcGui)) {
        throw "PFC GUI not found: $PfcGui"
    }

    $process = Get-Process -Name "pfc3d600_gui" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $process) {
        $statusText.Text = "Starting PFC GUI..."
        Start-Process -FilePath $PfcGui -WindowStyle Normal | Out-Null
        Start-Sleep -Seconds 6
        $process = Get-Process -Name "pfc3d600_gui" -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if ($null -eq $process) {
        throw "PFC GUI did not start. Please open PFC manually and click Run again."
    }

    $prompt = $null
    for ($i = 0; $i -lt 20; $i++) {
        $prompt = Find-PfcPrompt $process
        if ($null -ne $prompt) { break }
        Start-Sleep -Seconds 1
    }
    if ($null -eq $prompt) {
        throw "Cannot find the PFC Console input line. Open the Console panel, then click Run again."
    }

    Add-Type -AssemblyName System.Windows.Forms
    if (-not ("Win32PluginInput" -as [type])) {
$win32PluginInputSource = @'
using System;
using System.Runtime.InteropServices;
public class Win32PluginInput {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
}
'@
        Add-Type -TypeDefinition $win32PluginInputSource
    }
    $shell = New-Object -ComObject WScript.Shell
    [Win32PluginInput]::ShowWindow($process.MainWindowHandle, 5) | Out-Null
    [Win32PluginInput]::SetForegroundWindow($process.MainWindowHandle) | Out-Null
    [void]$shell.AppActivate($process.Id)
    Start-Sleep -Milliseconds 400

    $rect = $prompt.Current.BoundingRectangle
    $clickX = [int]($rect.Left + [Math]::Min(40, [Math]::Max(5, $rect.Width / 2)))
    $clickY = [int]($rect.Top + ($rect.Height / 2))
    [Win32PluginInput]::SetCursorPos($clickX, $clickY) | Out-Null
    [Win32PluginInput]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    [Win32PluginInput]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 200

    try {
        $valuePattern = $prompt.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $valuePattern.SetValue("")
    } catch {}
    [System.Windows.Forms.Clipboard]::SetText($Command)
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    Start-Sleep -Milliseconds 100
    [System.Windows.Forms.SendKeys]::SendWait("^v")
    Start-Sleep -Milliseconds 100
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
}

$cancelButton = New-Button "Close" 88 "#E5E7EB" "#111827"
$saveButton = New-Button "Save" 96 "#2563EB" "White"
$runButton = New-Button "Save and Run PFC" 150 "#16A34A" "White"
$buttonPanel.Children.Add($cancelButton) | Out-Null
$buttonPanel.Children.Add($saveButton) | Out-Null
$buttonPanel.Children.Add($runButton) | Out-Null

$cancelButton.Add_Click({ $window.Close() })

$saveButton.Add_Click({
    try {
        Save-ConfigFromUi | Out-Null
        [System.Windows.MessageBox]::Show("Configuration saved.", "Cyclic Particle PFC Plugin") | Out-Null
    } catch {
        [System.Windows.MessageBox]::Show([string]$_.Exception.Message, "Invalid config") | Out-Null
    }
})

$runButton.Add_Click({
    try {
        $saved = Save-ConfigFromUi
        Update-PfcEntryFile
        $commandPath = $RunPluginPath.Replace("\", "/")
        $command = "program call '$commandPath'"
        $statusText.Text = "Sending command to PFC..."
        Send-PfcCommand -PfcGui $saved.pfc.gui_path -Command $command
        $statusText.Text = "PFC command sent: $command"
        [System.Windows.MessageBox]::Show("PFC command has been sent.`n`n$command", "Cyclic Particle PFC Plugin") | Out-Null
    } catch {
        $statusText.Text = "Run failed"
        [System.Windows.MessageBox]::Show([string]$_.Exception.Message, "PFC launch failed") | Out-Null
    }
})

$window.ShowDialog() | Out-Null
