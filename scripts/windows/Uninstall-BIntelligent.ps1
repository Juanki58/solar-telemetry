#Requires -Version 5.1
<#
.SYNOPSIS
  Quita accesos directos y, opcionalmente, el entorno .venv.
#>
[CmdletBinding()]
param(
    [switch]$RemoveVenv,
    [switch]$RemoveConfig
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
foreach ($dir in @($desktop, $startMenu)) {
    $lnk = Join-Path $dir "B-Intelligent Monitor.lnk"
    if (Test-Path $lnk) {
        Remove-Item $lnk -Force
        Write-Host "Eliminado: $lnk"
    }
}

if ($RemoveVenv) {
    $venv = Join-Path $RepoRoot ".venv"
    if (Test-Path $venv) {
        Remove-Item $venv -Recurse -Force
        Write-Host "Eliminado: $venv"
    }
}

if ($RemoveConfig) {
    $cfg = Join-Path $RepoRoot "config.json"
    if (Test-Path $cfg) {
        Remove-Item $cfg -Force
        Write-Host "Eliminado: $cfg"
    }
}

Write-Host "Desinstalación de accesos directos completada."
Write-Host "El código del repo no se borra."
