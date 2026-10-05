#Requires -Version 5.1
<#
.SYNOPSIS
  Instala B-Intelligent Solar Telemetry en Windows (venv + deps + acceso directo).

.DESCRIPTION
  - Crea .venv en la raíz del repo
  - Instala requirements.txt
  - Copia config.example.json -> config.json si falta
  - Crea acceso directo en Escritorio y menú Inicio

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\windows\Install-BIntelligent.ps1
#>
[CmdletBinding()]
param(
    [switch]$NoShortcut,
    [switch]$SimMode
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Find-Python {
    $candidates = @(
        @{ Cmd = "py"; Args = @("-3") },
        @{ Cmd = "python"; Args = @() },
        @{ Cmd = "python3"; Args = @() }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.Cmd -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            $versionArgs = $c.Args + @("--version")
            $ver = & $c.Cmd @versionArgs 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0 -and $null -eq $ver) { continue }
            if ($ver -match "Python 3\.(\d+)") {
                $minor = [int]$Matches[1]
                if ($minor -lt 10) {
                    Write-Warning "Se encontró $($c.Cmd) ($($ver.Trim())) — se recomienda Python 3.10+."
                }
                return @{ Exe = $c.Cmd; PrefixArgs = $c.Args }
            }
        } catch {
            continue
        }
    }
    throw "No se encontró Python 3. Instálalo desde https://www.python.org/downloads/ (marca 'Add python.exe to PATH')."
}

Write-Host "B-Intelligent — instalación Windows" -ForegroundColor Green
Write-Host "Repo: $RepoRoot"

Write-Step "Comprobando Python"
$py = Find-Python
$pyLabel = (& $py.Exe @($py.PrefixArgs + @("--version")) 2>&1 | Out-String).Trim()
Write-Host "Usando: $($py.Exe) ($pyLabel)"

$venvPath = Join-Path $RepoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Step "Creando entorno virtual (.venv)"
    & $py.Exe @($py.PrefixArgs + @("-m", "venv", $venvPath))
    if ($LASTEXITCODE -ne 0) { throw "Fallo al crear .venv" }
} else {
    Write-Step "Reutilizando .venv existente"
}

Write-Step "Actualizando pip e instalando dependencias"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Fallo al actualizar pip" }
& $venvPip install -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Fallo al instalar requirements.txt" }

$configPath = Join-Path $RepoRoot "config.json"
$examplePath = Join-Path $RepoRoot "config.example.json"
if (-not (Test-Path $configPath)) {
    Write-Step "Creando config.json desde plantilla"
    Copy-Item $examplePath $configPath
    if ($SimMode) {
        $raw = Get-Content $configPath -Raw -Encoding UTF8
        $raw = $raw -replace '"default_mode"\s*:\s*"real"', '"default_mode": "sim"'
        Set-Content -Path $configPath -Value $raw -Encoding UTF8
        Write-Host "Modo laboratorio (sim) activado en config.json"
    } else {
        Write-Host "Edita config.json con las IPs de Victron/JK, o vuelve a instalar con -SimMode."
    }
} else {
    Write-Step "config.json ya existe (no se sobrescribe)"
}

$startBat = Join-Path $RepoRoot "scripts\windows\Start-BIntelligent.bat"
if (-not $NoShortcut) {
    Write-Step "Creando accesos directos"
    $wsh = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath("Desktop")
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    if (-not (Test-Path $startMenu)) {
        New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
    }

    foreach ($targetDir in @($desktop, $startMenu)) {
        $lnkPath = Join-Path $targetDir "B-Intelligent Monitor.lnk"
        $shortcut = $wsh.CreateShortcut($lnkPath)
        $shortcut.TargetPath = $startBat
        $shortcut.WorkingDirectory = $RepoRoot
        $shortcut.WindowStyle = 7
        $shortcut.Description = "B-Intelligent — monitor BMS Victron / JK"
        $shortcut.Save()
        Write-Host "  $lnkPath"
    }
}

Write-Host ""
Write-Host "Instalación completada." -ForegroundColor Green
Write-Host "Arranque: doble clic en 'B-Intelligent Monitor' o ejecuta:"
Write-Host "  $startBat"
Write-Host "Monitor: http://127.0.0.1:8501"
