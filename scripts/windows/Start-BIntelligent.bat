@echo off
setlocal EnableExtensions
title B-Intelligent Monitor
cd /d "%~dp0..\.."

set "VENV_PY=.venv\Scripts\python.exe"
set "INSTALL_BAT=%~dp0Install-BIntelligent.bat"
set "URL=http://127.0.0.1:8501"

if not exist "%VENV_PY%" (
  echo.
  echo [B-Intelligent] No hay entorno .venv — ejecutando instalacion...
  echo.
  call "%INSTALL_BAT%"
  if errorlevel 1 (
    echo.
    echo Instalacion fallida. No se puede arrancar el monitor.
    echo Instala Python 3.11 o 3.12 desde https://www.python.org/downloads/
    echo y vuelve a ejecutar Install-BIntelligent.bat
    echo.
    pause
    exit /b 1
  )
  if not exist "%VENV_PY%" (
    echo.
    echo ERROR: Tras la instalacion sigue sin existir:
    echo   %CD%\%VENV_PY%
    echo.
    pause
    exit /b 1
  )
)

"%VENV_PY%" -c "import streamlit" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [B-Intelligent] Faltan dependencias en .venv — reinstalando...
  echo.
  call "%INSTALL_BAT%"
  if errorlevel 1 (
    echo.
    echo No se pudieron instalar las dependencias.
    echo.
    pause
    exit /b 1
  )
)

echo.
echo [B-Intelligent] Arrancando monitor en %URL%
echo Cierra esta ventana para detener el servidor.
echo.

"%VENV_PY%" launcher.py
set EXITCODE=%ERRORLEVEL%
if not %EXITCODE%==0 (
  echo.
  echo El monitor se detuvo con codigo %EXITCODE%.
  echo Si ves errores de import/modulos, ejecuta Install-BIntelligent.bat otra vez.
  echo.
  pause
)
exit /b %EXITCODE%
