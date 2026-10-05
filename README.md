# Solar Telemetry — Victron / JK BMS

Monitor profesional de **planta solar y salud de baterías LiFePO4** (Victron GX + JK BMS).

[![Monitor demo](docs/preview-bms-monitor.png)](https://htmlpreview.github.io/?https://github.com/Juanki58/solar-telemetry/blob/main/docs/index.html)

**[▶ Demo pública (simulada)](https://htmlpreview.github.io/?https://github.com/Juanki58/solar-telemetry/blob/main/docs/index.html)** — vista previa en el navegador, sin planta.  
El monitor real (Modbus / JK) se instala en Windows en 2 clics.

| Qué | Dónde |
|-----|--------|
| Demo HTML | [htmlpreview](https://htmlpreview.github.io/?https://github.com/Juanki58/solar-telemetry/blob/main/docs/index.html) |
| App local | `http://127.0.0.1:8501` tras instalar |

---

## Instalación en Windows (recomendado)

**Requisito:** [Python 3.10+](https://www.python.org/downloads/) con *Add python.exe to PATH*.

1. Descarga o clona este repo.
2. Doble clic en:

```text
scripts\windows\Install-BIntelligent.bat
```

O en PowerShell (modo laboratorio sin planta):

```powershell
cd C:\ruta\a\solar-telemetry
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Install-BIntelligent.ps1 -SimMode
```

Eso crea `.venv`, instala dependencias, genera `config.json` y deja el acceso directo **B-Intelligent Monitor** en el Escritorio y en el menú Inicio.

3. Arrancar: doble clic en **B-Intelligent Monitor**, o:

```text
scripts\windows\Start-BIntelligent.bat
```

Se abre el navegador en `http://127.0.0.1:8501`.

### Desinstalar accesos directos

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Uninstall-BIntelligent.ps1
# Opcional: -RemoveVenv  -RemoveConfig
```

---

## Arranque manual (cualquier SO)

```powershell
cd C:\ruta\a\solar-telemetry
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/mac: source .venv/bin/activate
python -m pip install -r requirements.txt
copy config.example.json config.json  # primera vez
python launcher.py
```

Opciones del launcher:

```text
python launcher.py --host 0.0.0.0 --port 8501   # visible en la LAN
python launcher.py --no-browser
```

Modo laboratorio sin Victron/JK: en `config.json` pon `"default_mode": "sim"`.

---

## Componentes

| Archivo | Uso |
|---------|-----|
| `launcher.py` | Arranque tipo app (Streamlit + navegador) |
| `bms_web_monitor.py` | Dashboard Streamlit (SoC, celdas JK, salud LiFePO4) |
| `bms_gui_monitor.py` | Panel escritorio tkinter (alternativa ligera) |
| `victron_industrial_bms_safety.py` | Protección activa Modbus Victron |
| `jk_bms_client.py` | Cliente JK BMS v19 |
| `config_loader.py` | Carga `config.json` |
| `integrations/whatsapp_alerts.py` | Alertas opcionales WhatsApp Cloud API |
| `docs/index.html` | Demo estática (simulada) |
| `scripts/windows/*` | Instalación y arranque en Windows |

## Config

- Plantilla: `config.example.json`
- Local (no se sube): `config.json` — IPs Cerbo/JK, umbrales, WhatsApp

## Seguridad activa Victron

```powershell
.\.venv\Scripts\python.exe victron_industrial_bms_safety.py
```

## Licencia

Uso personal / planta propia salvo que se indique lo contrario.
