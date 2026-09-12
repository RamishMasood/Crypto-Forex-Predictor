# Portable installer used when sending the unpacked QuantTerminal folder.
$ErrorActionPreference = "Stop"
$Source = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path (Join-Path $Source "QuantTerminal.exe")) {
    $AppSource = $Source
} elseif (Test-Path (Join-Path $Source "QuantTerminal\QuantTerminal.exe")) {
    $AppSource = Join-Path $Source "QuantTerminal"
} else {
    throw "QuantTerminal.exe was not found next to this installer."
}

$Dest = Join-Path $env:LOCALAPPDATA "QuantTerminal"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item -Path (Join-Path $AppSource "*") -Destination $Dest -Recurse -Force

$Exe = Join-Path $Dest "QuantTerminal.exe"
$Wsh = New-Object -ComObject WScript.Shell

$Desktop = Join-Path $Wsh.SpecialFolders.Item("Desktop") "Quant Terminal.lnk"
$Shortcut = $Wsh.CreateShortcut($Desktop)
$Shortcut.TargetPath = $Exe
$Shortcut.WorkingDirectory = $Dest
$Shortcut.Description = "Quant Terminal"
$Shortcut.Save()

$Programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
New-Item -ItemType Directory -Force -Path $Programs | Out-Null
$StartMenu = Join-Path $Programs "Quant Terminal.lnk"
$Shortcut = $Wsh.CreateShortcut($StartMenu)
$Shortcut.TargetPath = $Exe
$Shortcut.WorkingDirectory = $Dest
$Shortcut.Description = "Quant Terminal"
$Shortcut.Save()

$Startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Quant Terminal.lnk"
$Shortcut = $Wsh.CreateShortcut($Startup)
$Shortcut.TargetPath = $Exe
$Shortcut.WorkingDirectory = $Dest
$Shortcut.Description = "Quant Terminal"
$Shortcut.Save()

Start-Process -FilePath $Exe
Write-Host "Quant Terminal installed to $Dest"
Write-Host "Desktop, Start Menu, and Startup shortcuts were created."
