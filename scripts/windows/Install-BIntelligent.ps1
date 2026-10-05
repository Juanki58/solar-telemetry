#Requires -Version 5.1
<#
.SYNOPSIS
  Instala B-Intelligent Solar Telemetry en Windows (venv + deps + acceso directo).

.DESCRIPTION
  - Busca Python 3.11-3.12 (evita 3.13+ / 3.14 que suelen romper Streamlit)
  - Crea .venv en la raiz del repo
  - Instala requirements.txt
  - Copia config.example.json -> config.json si falta
  - Crea acceso directo en Escritorio y menu Inicio

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

# Preferidos por compatibilidad con Streamlit en Windows.
$PreferredMinors = @(12, 11)
$MinMinor = 10
$MaxMinor = 12

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
}

function Get-PythonVersionInfo {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$PrefixArgs = @()
    )
    try {
        $raw = & $Exe @($PrefixArgs + @("-c", "import sys; print('%d.%d.%d'%sys.version_info[:3]); print(sys.executable)")) 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $lines = @($raw | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
        if ($lines.Count -lt 2) { return $null }
        if ($lines[0] -notmatch '^(\d+)\.(\d+)\.(\d+)$') { return $null }
        return @{
            Major      = [int]$Matches[1]
            Minor      = [int]$Matches[2]
            Patch      = [int]$Matches[3]
            Version    = $lines[0]
            Executable = $lines[1]
            Exe        = $Exe
            PrefixArgs = $PrefixArgs
        }
    } catch {
        return $null
    }
}

function Find-Python {
    $found = @()

    # 1) py launcher - versiones preferidas y tags Astral/uv conocidos
    $pyCmd = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $launcherSpecs = @(
            @{ Args = @("-3.12") },
            @{ Args = @("-3.11") },
            @{ Args = @("-V:Astral\CPython3.12.13") },
            @{ Args = @("-V:Astral\CPython3.12") },
            @{ Args = @("-V:Astral\CPython3.11") },
            @{ Args = @("-3") }
        )
        foreach ($spec in $launcherSpecs) {
            $info = Get-PythonVersionInfo -Exe "py" -PrefixArgs $spec.Args
            if ($null -ne $info) { $found += $info }
        }
    }

    # 2) python / python3 en PATH
    foreach ($name in @("python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        # Evitar el stub de WindowsApps que abre la Store
        if ($cmd.Source -match 'WindowsApps\\python') { continue }
        $info = Get-PythonVersionInfo -Exe $cmd.Source -PrefixArgs @()
        if ($null -ne $info) { $found += $info }
    }

    # 3) Rutas habituales (oficial + uv/Astral)
    $pathGlobs = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:LOCALAPPDATA\Python\pythoncore-3*\python.exe",
        "$env:APPDATA\uv\python\cpython-3*\python.exe",
        "$env:USERPROFILE\.local\share\uv\python\cpython-3*\python.exe",
        "C:\Python3*\python.exe"
    )
    foreach ($glob in $pathGlobs) {
        Get-Item -Path $glob -ErrorAction SilentlyContinue | ForEach-Object {
            $info = Get-PythonVersionInfo -Exe $_.FullName -PrefixArgs @()
            if ($null -ne $info) { $found += $info }
        }
    }

    # Deduplicar por executable real
    $unique = @{}
    foreach ($f in $found) {
        $key = $f.Executable.ToLowerInvariant()
        if (-not $unique.ContainsKey($key)) {
            $unique[$key] = $f
        }
    }
    $candidates = @($unique.Values)

    if ($candidates.Count -eq 0) {
        throw @"
No se encontro Python 3.
Instalalo desde https://www.python.org/downloads/ (marca 'Add python.exe to PATH')
o con:  py install 3.12
Se recomienda Python 3.11 o 3.12 (Streamlit aun no es fiable en 3.13/3.14).
"@
    }

    # Preferir 3.12 luego 3.11, luego cualquier 3.10-3.12
    foreach ($want in $PreferredMinors) {
        $hit = $candidates | Where-Object { $_.Major -eq 3 -and $_.Minor -eq $want } |
            Sort-Object Patch -Descending | Select-Object -First 1
        if ($hit) { return $hit }
    }

    $ok = $candidates | Where-Object {
        $_.Major -eq 3 -and $_.Minor -ge $MinMinor -and $_.Minor -le $MaxMinor
    } | Sort-Object Minor, Patch -Descending | Select-Object -First 1
    if ($ok) { return $ok }

    $shown = ($candidates | ForEach-Object { "  - $($_.Version)  $($_.Executable)" }) -join "`n"
    throw @"
Se encontro Python, pero ninguna version compatible (se necesita 3.$MinMinor-3.$MaxMinor).
Detectado:
$shown

Instala Python 3.12 desde https://www.python.org/downloads/ o ejecuta: py install 3.12
Python 3.14 / 3.13 suelen fallar con Streamlit en Windows.
"@
}

Write-Host "B-Intelligent - instalacion Windows" -ForegroundColor Green
Write-Host "Repo: $RepoRoot"

try {
    Write-Step "Comprobando Python (preferido 3.11-3.12)"
    $py = Find-Python
    Write-Host "Usando: Python $($py.Version)"
    Write-Host "  $($py.Executable)"

    if ($py.Minor -gt $MaxMinor) {
        throw "Python $($py.Version) no es compatible. Usa 3.11 o 3.12."
    }

    $venvPath = Join-Path $RepoRoot ".venv"
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    $venvPip = Join-Path $venvPath "Scripts\pip.exe"

    if (-not (Test-Path $venvPython)) {
        Write-Step "Creando entorno virtual (.venv)"
        & $py.Exe @($py.PrefixArgs + @("-m", "venv", $venvPath))
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
            throw "Fallo al crear .venv con Python $($py.Version)"
        }
    } else {
        Write-Step "Reutilizando .venv existente"
        $venvInfo = Get-PythonVersionInfo -Exe $venvPython
        if ($null -eq $venvInfo) {
            Write-Warning ".venv danado; se recreara."
            Remove-Item $venvPath -Recurse -Force
            & $py.Exe @($py.PrefixArgs + @("-m", "venv", $venvPath))
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
                throw "Fallo al recrear .venv"
            }
        } elseif ($venvInfo.Minor -gt $MaxMinor) {
            Write-Warning ".venv usa Python $($venvInfo.Version) (demasiado nuevo). Se recreara con $($py.Version)."
            Remove-Item $venvPath -Recurse -Force
            & $py.Exe @($py.PrefixArgs + @("-m", "venv", $venvPath))
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
                throw "Fallo al recrear .venv con Python $($py.Version)"
            }
        } else {
            Write-Host "  .venv: Python $($venvInfo.Version)"
        }
    }

    Write-Step "Actualizando pip e instalando dependencias"
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Fallo al actualizar pip" }
    & $venvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Fallo al instalar requirements.txt" }

    Write-Step "Comprobando Streamlit en el entorno"
    & $venvPython -c "import streamlit; print('streamlit', streamlit.__version__)"
    if ($LASTEXITCODE -ne 0) {
        throw "Streamlit no se importa correctamente. Revisa el log de pip o usa Python 3.12."
    }

    $configPath = Join-Path $RepoRoot "config.json"
    $examplePath = Join-Path $RepoRoot "config.example.json"
    if (-not (Test-Path $configPath)) {
        Write-Step "Creando config.json desde plantilla"
        if (-not (Test-Path $examplePath)) {
            throw "Falta config.example.json en el repo"
        }
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
            $shortcut.Description = "B-Intelligent - monitor BMS Victron / JK"
            $shortcut.Save()
            Write-Host "  $lnkPath"
        }
    }

    Write-Host ""
    Write-Host "Instalacion completada." -ForegroundColor Green
    Write-Host "Arranque: doble clic en 'B-Intelligent Monitor' o ejecuta:"
    Write-Host "  $startBat"
    Write-Host "Monitor: http://127.0.0.1:8501"
    exit 0
} catch {
    Write-Fail $_.Exception.Message
    exit 1
}