#!/usr/bin/env python3
"""
B-Intelligent — launcher de escritorio.

Arranca Streamlit (bms_web_monitor.py), espera a que el puerto responda
y abre el navegador. Pensado para doble clic / acceso directo Windows.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "bms_web_monitor.py"
CONFIG = ROOT / "config.json"
CONFIG_EXAMPLE = ROOT / "config.example.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8501
READY_TIMEOUT_S = 60.0
MIN_MINOR = 10
MAX_MINOR = 12


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def check_runtime() -> int | None:
    """Devuelve código de error si el runtime no sirve; None si OK."""
    major, minor = sys.version_info[:2]
    if major != 3 or minor < MIN_MINOR:
        _eprint(
            f"[launcher] Python {major}.{minor} no soportado. "
            f"Usa Python 3.{MIN_MINOR}–3.{MAX_MINOR}."
        )
        _eprint(
            "[launcher] En Windows: ejecuta scripts\\windows\\Install-BIntelligent.bat"
        )
        return 3
    if minor > MAX_MINOR:
        _eprint(
            f"[launcher] Python {major}.{minor} puede romper Streamlit. "
            f"Se recomienda 3.11 o 3.12."
        )
        _eprint(
            "[launcher] Recrea el entorno con scripts\\windows\\Install-BIntelligent.bat"
        )
        return 3

    try:
        import streamlit  # noqa: F401
    except ImportError:
        _eprint("[launcher] Falta el paquete 'streamlit' en este Python.")
        _eprint(f"[launcher] Intérprete: {sys.executable}")
        _eprint(
            "[launcher] Solución: doble clic en "
            "scripts\\windows\\Install-BIntelligent.bat"
        )
        return 4

    if not APP.exists():
        _eprint(f"[launcher] No se encuentra {APP.name} en {ROOT}")
        return 2

    return None


def ensure_config() -> None:
    if CONFIG.exists():
        return
    if not CONFIG_EXAMPLE.exists():
        raise FileNotFoundError(f"Falta {CONFIG_EXAMPLE.name}")
    shutil.copyfile(CONFIG_EXAMPLE, CONFIG)
    print(
        f"[launcher] Creado {CONFIG.name} desde plantilla. "
        "Edita IPs o pon default_mode=sim."
    )


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_ready(host: str, port: int, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if port_open(host, port):
            return True
        time.sleep(0.35)
    return False


def is_non_local_bind(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("0.0.0.0", "::", "[::]")


def resolve_web_auth_password(config_path: Path) -> str:
    """Lee web_auth_password de secrets.toml o config.json (sin Streamlit)."""
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if secrets_path.exists():
        try:
            text = secrets_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                raw = line.strip()
                if raw.startswith("#") or "=" not in raw:
                    continue
                key, _, val = raw.partition("=")
                key = key.strip()
                if key in ("web_auth_password", "BMS_WEB_PASSWORD"):
                    return val.strip().strip('"').strip("'")
        except OSError:
            pass

    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8-sig"))
            return str(data.get("web_auth_password") or "").strip()
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return ""


def enforce_lan_auth_or_exit(host: str) -> int | None:
    """
    Fail-closed: binding LAN sin password → no arrancar.
    Devuelve código de error o None si OK.
    """
    if not is_non_local_bind(host):
        return None

    password = resolve_web_auth_password(CONFIG)
    if password:
        print("[launcher] Auth LAN: contraseña detectada (config/secrets).")
        return None

    _eprint(
        "[launcher] BLOQUEADO: --host 0.0.0.0 (LAN) sin web_auth_password.\n"
        "[launcher] Cualquiera en la Wi‑Fi podría ver el monitor.\n"
        "[launcher] Configura una de estas opciones y reinicia:\n"
        "  1) config.json → \"web_auth_password\": \"tu-clave\"\n"
        "  2) .streamlit/secrets.toml → web_auth_password = \"tu-clave\"\n"
        "[launcher] O usa solo localhost: Start-BIntelligent.bat (sin LAN)."
    )
    return 6


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Arranca el monitor BMS B-Intelligent")
    p.add_argument("--host", default=os.environ.get("BMS_HOST", DEFAULT_HOST))
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BMS_PORT", str(DEFAULT_PORT))),
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="No abrir el navegador automáticamente",
    )
    p.add_argument(
        "--allow-insecure-lan",
        action="store_true",
        help="Permitir LAN sin password (NO recomendado; solo laboratorio)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    err = check_runtime()
    if err is not None:
        return err

    try:
        ensure_config()
    except FileNotFoundError as exc:
        _eprint(f"[launcher] {exc}")
        return 2

    if not args.allow_insecure_lan:
        auth_err = enforce_lan_auth_or_exit(args.host)
        if auth_err is not None:
            return auth_err
    elif is_non_local_bind(args.host):
        _eprint(
            "[launcher] AVISO: LAN sin auth (--allow-insecure-lan). "
            "No uses esto fuera de un laboratorio aislado."
        )

    url = f"http://{args.host}:{args.port}"
    if port_open(args.host, args.port):
        print(f"[launcher] Ya hay un servicio en {url} — abriendo navegador.")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP),
        "--server.headless=true",
        f"--server.address={args.host}",
        f"--server.port={args.port}",
        "--browser.gatherUsageStats=false",
    ]

    print(f"[launcher] Python {sys.version.split()[0]} — {sys.executable}")
    print(f"[launcher] Iniciando monitor en {url}")
    if is_non_local_bind(args.host):
        print("[launcher] Modo LAN: se requiere web_auth_password (fail-closed).")
    print("[launcher] Ctrl+C para detener.")

    env = os.environ.copy()
    env.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    env["BMS_BIND_HOST"] = args.host
    env["STREAMLIT_SERVER_ADDRESS"] = args.host

    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
    except OSError as exc:
        _eprint(f"[launcher] No se pudo arrancar Streamlit: {exc}")
        return 5

    try:
        if wait_ready(args.host, args.port, READY_TIMEOUT_S):
            print(f"[launcher] Listo: {url}")
            if not args.no_browser:
                webbrowser.open(url)
        else:
            if proc.poll() is not None:
                _eprint(
                    f"[launcher] Streamlit salió con código {proc.returncode} "
                    "antes de abrir el puerto. Revisa el error anterior."
                )
                return int(proc.returncode or 1)
            _eprint(
                f"[launcher] Aviso: el puerto {args.port} no respondió a tiempo; "
                "revisa la salida de Streamlit."
            )

        return int(proc.wait() or 0)
    except KeyboardInterrupt:
        print("\n[launcher] Deteniendo…")
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
