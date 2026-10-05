@echo off
setlocal EnableExtensions
title B-Intelligent Monitor (LAN)
cd /d "%~dp0"

echo.
echo [B-Intelligent] Modo LAN: Streamlit escuchara en 0.0.0.0:8501
echo.
echo IMPORTANTE — autenticacion obligatoria:
echo   Configura web_auth_password en config.json o .streamlit\secrets.toml
echo   Sin password el launcher BLOQUEA el arranque (fail-closed).
echo.
echo Ejemplo secrets.toml:
echo   web_auth_password = "tu-clave-segura"
echo.
echo Abre el puerto 8501 en el firewall de Windows si el movil no conecta.
echo En el telefono usa: http://IP-DE-ESTE-PC:8501
echo.

call "%~dp0Start-BIntelligent.bat" --host 0.0.0.0 --port 8501
exit /b %ERRORLEVEL%
