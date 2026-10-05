@echo off
setlocal
title B-Intelligent Monitor
cd /d "%~dp0..\.."

if not exist ".venv\Scripts\python.exe" (
  echo No hay instalacion. Ejecuta primero Install-BIntelligent.bat
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" launcher.py
set EXITCODE=%ERRORLEVEL%
if not %EXITCODE%==0 (
  echo.
  echo El monitor se detuvo con codigo %EXITCODE%.
  pause
)
exit /b %EXITCODE%
