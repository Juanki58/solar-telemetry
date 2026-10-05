#Requires -Version 5.1
<#
.SYNOPSIS
  Crea/recrea accesos directos "B-Intelligent Monitor" (Escritorio + menu Inicio).

.DESCRIPTION
  Apunta a scripts\windows\Start-BIntelligent.bat y usa assets\b-intelligent.ico.
  Seguro de ejecutar varias veces (reemplaza accesos rotos o sin icono).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$startBat = Join-Path $RepoRoot "scripts\windows\Start-BIntelligent.bat"
$iconPath = Join-Path $RepoRoot "assets\b-intelligent.ico"

if (-not (Test-Path $startBat)) {
    throw "No se encuentra Start-BIntelligent.bat en $startBat"
}

$wsh = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
if (-not (Test-Path $startMenu)) {
    New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
}

$created = @()
foreach ($targetDir in @($desktop, $startMenu)) {
    $lnkPath = Join-Path $targetDir "B-Intelligent Monitor.lnk"
    if (Test-Path $lnkPath) {
        Remove-Item $lnkPath -Force -ErrorAction SilentlyContinue
    }
    $shortcut = $wsh.CreateShortcut($lnkPath)
    $shortcut.TargetPath = $startBat
    $shortcut.WorkingDirectory = $RepoRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = "B-Intelligent - monitor BMS Victron / JK"
    if (Test-Path $iconPath) {
        $shortcut.IconLocation = "$iconPath,0"
    }
    $shortcut.Save()
    $created += $lnkPath
}

$created
