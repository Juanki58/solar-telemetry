@echo off
setlocal EnableExtensions
title B-Intelligent Install
cd /d "%~dp0"

echo.
echo B-Intelligent — instalacion Windows
echo.

where powershell >nul 2>&1
if errorlevel 1 (
  echo ERROR: No se encuentra PowerShell en PATH.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-BIntelligent.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not %EXITCODE%==0 (
  echo.
  echo Instalacion fallida (codigo %EXITCODE%).
  echo Requisitos: Python 3.11 o 3.12 ^(no uses solo 3.14^).
  echo Descarga: https://www.python.org/downloads/
  echo.
  pause
  exit /b %EXITCODE%
)
echo.
pause
exit /b 0
