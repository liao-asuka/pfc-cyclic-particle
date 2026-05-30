Option Explicit

Dim shell, fso, scriptDir, psScript, command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
psScript = fso.BuildPath(scriptDir, "ui\edit_config.ps1")

If Not fso.FileExists(psScript) Then
    MsgBox "Cannot find:" & vbCrLf & psScript, vbCritical, "Cyclic Particle Plugin"
    WScript.Quit 1
End If

command = "powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & psScript & Chr(34)
shell.Run command, 1, False
