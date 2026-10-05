#!/usr/bin/env python3
"""
B-Intelligent — launcher de escritorio.

Arranca Streamlit (bms_web_monitor.py), espera a que el puerto responda
y abre el navegador. Pensado para doble clic / acceso directo Windows.
"""

from __future__ import annotations

import argparse
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
READY_TIMEOUT_S = 45.0


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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not APP.exists():
        print(f"[launcher] No se encuentra {APP.name}", file=sys.stderr)
        return 2

    ensure_config()

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

    print(f"[launcher] Iniciando monitor en {url}")
    print("[launcher] Ctrl+C para detener.")

    env = os.environ.copy()
    env.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)

    try:
        if wait_ready(args.host, args.port, READY_TIMEOUT_S):
            print(f"[launcher] Listo: {url}")
            if not args.no_browser:
                webbrowser.open(url)
        else:
            print(
                f"[launcher] Aviso: el puerto {args.port} no respondió a tiempo; "
                "revisa la salida de Streamlit.",
                file=sys.stderr,
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
