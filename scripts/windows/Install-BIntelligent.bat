@echo off
setlocal
title B-Intelligent Install
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-BIntelligent.ps1" %*
set EXITCODE=%ERRORLEVEL%
if not %EXITCODE%==0 (
  echo.
  echo Instalacion fallida (codigo %EXITCODE%).
  pause
  exit /b %EXITCODE%
)
echo.
pause
exit /b 0
