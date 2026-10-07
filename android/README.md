# B-Intelligent Monitor — app Android (WebView)

Cliente ligero que abre el **monitor Streamlit del PC** en la misma Wi‑Fi.
El Victron / telemetría real corre en el PC; el teléfono solo muestra la URL.

No se publica en Play Store desde este repo: genera e instala el APK tú mismo.

## Requisitos

- [Android Studio](https://developer.android.com/studio) (SDK + JDK incluidos)
- PC con el monitor en **modo LAN** y móvil en la **misma Wi‑Fi**

## Instalar el APK (Android Studio)

1. Abre la carpeta `android/` en Android Studio (**File → Open**).
2. Si pide `local.properties`, Android Studio lo crea solo; o copia `local.properties.example` y pon tu `sdk.dir`.
3. Espera a que Gradle sincronice (primera vez descarga dependencias y el wrapper si hace falta).
4. **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
5. APK de depuración:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

6. Cópialo al teléfono e instálalo (permite “orígenes desconocidos” / instalar apps desconocidas si Android lo pide).

### Línea de comandos (si tienes SDK + JDK)

```powershell
cd android
.\gradlew.bat assembleDebug
```

Si no hay wrapper aún, ábrelo una vez en Android Studio (**Sync Project with Gradle Files**).

> En este entorno de CI/agente puede no haber Android SDK: el proyecto queda listo para compilar en tu máquina con Android Studio.

## Apuntar el móvil al PC (monitor en vivo)

### 1. Contraseña LAN (obligatoria)

Antes de escuchar en `0.0.0.0`, configura password:

```json
"web_auth_password": "tu-clave-segura"
```

en `config.json`, **o** `.streamlit/secrets.toml` (ver `.streamlit/secrets.toml.example`).

Sin password, el launcher **bloquea** el modo LAN (fail-closed).

### 2. Arrancar el monitor en LAN

```text
scripts\windows\Start-BIntelligent-LAN.bat
```

o:

```powershell
.\.venv\Scripts\python.exe launcher.py --host 0.0.0.0 --port 8501
```

### 3. Firewall

Permite tráfico entrante **TCP 8501** en la red privada de Windows.

### 4. IP del PC

En PowerShell o CMD:

```text
ipconfig
```

Busca **IPv4** de la Wi‑Fi / Ethernet (ej. `192.168.1.40`). No uses `127.0.0.1` en el móvil.

### 5. En la app

1. Primera ejecución: introduce `http://IP-DEL-PC:8501` → **Guardar y conectar**.
2. Después: menú ⋮ → **Configurar servidor** → misma URL → guarda (reconecta al volver).
3. Si falla: pantalla de error con **Reintentar** (no un WebView en blanco).

PC y móvil deben estar en la **misma Wi‑Fi** (no solo datos móviles del teléfono).

### Demo HTML (opcional)

En ajustes / menú hay atajo a la demo estática pública. **No es el monitor Victron en vivo**; solo sirve para ver aspecto sin planta.

## Seguridad (honesto)

| Tema | Qué hay |
|------|---------|
| Cleartext HTTP | **Permitido en toda la app** (`network_security_config.xml` + `usesCleartextTraffic`). Android no permite limitar cleartext a rangos CIDR privados; hace falta para `http://192.168.x.x:8501`. |
| Auth LAN | Usa `web_auth_password`. No expongas `:8501` a Internet. |
| Red | Solo Wi‑Fi de confianza (casa / planta). |
| Demo HTTPS | La demo pública usa HTTPS; el monitor local usa HTTP. |

## Notas técnicas

- Min SDK 24, target / compile SDK 34, Kotlin, WebView + Material 3.
- Primera ejecución y ajustes guardan la URL en `SharedPreferences`.
- Errores tipificados: sin red, connection refused, host incorrecto, timeout, HTTP 4xx/5xx.
- El monitor **no** corre en el teléfono.
