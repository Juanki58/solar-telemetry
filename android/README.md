# B-Intelligent Monitor — app Android (WebView)

App ligera que abre el monitor Streamlit que corre en tu PC (misma Wi‑Fi),
o la demo estática de documentación.

No se publica en Play Store desde este repo: genera e instala el APK tú mismo.

## Requisitos

- [Android Studio](https://developer.android.com/studio) (incluye SDK + JDK)
- Un PC con el monitor en marcha y visible en la LAN

## Build del APK (Android Studio)

1. Abre la carpeta `android/` en Android Studio (**Open**).
2. Espera a que Gradle sincronice (primera vez puede descargar dependencias).
3. Menú **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
4. El APK queda en:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

5. Cópialo al teléfono e instálalo (activa “orígenes desconocidos” si Android lo pide).

### Build por línea de comandos (si tienes SDK)

```powershell
cd android
.\gradlew.bat assembleDebug
```

Si no hay `gradlew` wrapper aún, Android Studio lo genera al abrir el proyecto.
También puedes usar: **File → Sync Project with Gradle Files**.

## Conectar el móvil al monitor del PC

1. En el PC, arranca el monitor escuchando en todas las interfaces:

```text
scripts\windows\Start-BIntelligent-LAN.bat
```

o:

```powershell
.\.venv\Scripts\python.exe launcher.py --host 0.0.0.0 --port 8501
```

2. Firewall de Windows: permite tráfico entrante TCP **8501** (red privada).
3. Averigua la IP LAN del PC (`ipconfig` → IPv4, p. ej. `192.168.1.40`).
4. Abre la app → menú ⋮ → **Configurar servidor** → URL:

```text
http://192.168.1.40:8501
```

(sustituye por la IP real de tu PC).

5. PC y móvil deben estar en la **misma red Wi‑Fi** (no uses datos móviles).

### Demo sin planta

En ajustes puedes poner la URL de la demo estática del repo (htmlpreview / GitHub Pages)
si solo quieres ver el aspecto sin conectar al PC.

## Notas

- El monitor real no corre en el teléfono: la app es un cliente WebView.
- HTTP claro (`http://…`) está permitido solo para IPs privadas / localhost (ver `network_security_config.xml`).
- Min SDK 24, target SDK 34.
