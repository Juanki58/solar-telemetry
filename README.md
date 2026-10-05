# Solar Telemetry — Victron / JK BMS

Monitor profesional de **planta solar y salud de baterías LiFePO4** (Victron GX + JK BMS).

[![Monitor demo](docs/preview-bms-monitor.png)](https://htmlpreview.github.io/?https://github.com/Juanki58/solar-telemetry/blob/main/docs/index.html)

**[▶ Demo pública (simulada)](https://htmlpreview.github.io/?https://github.com/Juanki58/solar-telemetry/blob/main/docs/index.html)** — vista previa en el navegador, sin planta.  
El monitor real (Modbus / JK) se instala en Windows en 2 clics.

| Qué | Dónde |
|-----|--------|
| Demo HTML | [htmlpreview](https://htmlpreview.github.io/?https://github.com/Juanki58/solar-telemetry/blob/main/docs/index.html) |
| App local (PC) | `http://127.0.0.1:8501` tras instalar |
| App Android | Carpeta [`android/`](android/) — WebView hacia el PC en LAN |

---

## Instalación en Windows (recomendado)

**Requisito:** [Python **3.11 o 3.12**](https://www.python.org/downloads/) (recomendado) con *Add python.exe to PATH*.  
Evita usar solo Python 3.13/3.14: Streamlit en Windows suele fallar. El instalador busca solo 3.10–3.12.

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

Eso crea `.venv`, instala dependencias, genera `config.json` y deja el acceso directo **B-Intelligent Monitor** en el **Escritorio** y en el **menú Inicio**, con icono `assets\b-intelligent.ico`.

3. Arrancar: doble clic en **B-Intelligent Monitor**, o:

```text
scripts\windows\Start-BIntelligent.bat
```

Si falta `.venv`, **Start** lanza la instalación automáticamente.  
Si falta el acceso directo, **Start** lo recrea.  
Se abre el navegador en `http://127.0.0.1:8501`.

### Acceso directo de escritorio

| Acción | Resultado |
|--------|-----------|
| `Install-BIntelligent.bat` | Crea/recrea **B-Intelligent Monitor** (Escritorio + Inicio) → `Start-BIntelligent.bat` |
| Solo recrear iconos | `powershell -ExecutionPolicy Bypass -File .\scripts\windows\Create-Shortcuts.ps1` |
| Icono | `assets\b-intelligent.ico` |

### Desinstalar accesos directos

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\Uninstall-BIntelligent.ps1
# Opcional: -RemoveVenv  -RemoveConfig
```

---

## App Android (WebView)

El monitor real corre en el **PC**. La app Android es un cliente WebView que abre esa URL en la misma Wi‑Fi (no se publica en Play Store desde este repo).

### Compilar e instalar el APK

1. Instala [Android Studio](https://developer.android.com/studio).
2. Abre la carpeta `android/` (**Open**).
3. **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
4. Instala en el teléfono:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

Detalle completo: [`android/README.md`](android/README.md).

### Apuntar el móvil al monitor del PC

1. En el PC, arranca en modo LAN:

```text
scripts\windows\Start-BIntelligent-LAN.bat
```

(o `python launcher.py --host 0.0.0.0 --port 8501`)

2. Permite el puerto **TCP 8501** en el firewall de Windows (red privada).
3. Obtén la IP del PC (`ipconfig`, p. ej. `192.168.1.40`).
4. En la app: menú → **Configurar servidor** → `http://192.168.1.40:8501`.

PC y móvil deben compartir la misma Wi‑Fi. La primera ejecución pide la URL; también hay opción de abrir la **demo pública** sin planta.

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
python launcher.py --host 0.0.0.0 --port 8501   # visible en la LAN (móvil / Android)
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
| `docs/index.html` | Demo estática (simulada) + PWA manifest |
| `scripts/windows/*` | Instalación, arranque y accesos directos Windows |
| `android/` | App WebView Kotlin/Gradle (cliente LAN) |
| `assets/b-intelligent.ico` | Icono del acceso directo Windows |

## Config

- Plantilla: `config.example.json`
- Local (no se sube): `config.json` — IPs Cerbo/JK, umbrales, WhatsApp

## Seguridad activa Victron

```powershell
.\.venv\Scripts\python.exe victron_industrial_bms_safety.py
```

## Licencia

Uso personal / planta propia salvo que se indique lo contrario.
