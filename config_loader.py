"""
Carga centralizada de config.json para los módulos de solar-telemetry.

Unifica victron_host (clave canónica en config.example.json) con el alias
histórico victron_ip, para que todos los scripts arranquen sin KeyError.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

CORE_DEFAULTS: dict[str, Any] = {
    "victron_host": "192.168.1.100",
    "modbus_port": 502,
    "victron_unit_id": 100,
    "v_cell_critical_high": 3.60,
    "v_cell_warning_high": 3.45,
    "v_cell_critical_low": 2.60,
    "t_critical_high": 55.0,
    "t_charge_low": 0.0,
    "jk_port": 6481,
    "cell_count": 16,
    "batteries": [],
}


def normalize_config(cfg: dict[str, Any], *, loaded_keys: set[str] | None = None) -> dict[str, Any]:
    """Normaliza alias y estructuras derivadas tras mezclar defaults + JSON."""
    loaded_keys = loaded_keys or set()

    if "victron_host" in loaded_keys and cfg.get("victron_host"):
        host = cfg["victron_host"]
    elif "victron_ip" in loaded_keys and cfg.get("victron_ip"):
        host = cfg["victron_ip"]
    else:
        host = cfg.get("victron_host") or cfg.get("victron_ip")

    if host:
        cfg["victron_host"] = host
        cfg["victron_ip"] = host  # alias retrocompatible
    else:
        logger.warning(
            "config sin victron_host ni victron_ip; usando default %s",
            CORE_DEFAULTS["victron_host"],
        )
        cfg["victron_host"] = CORE_DEFAULTS["victron_host"]
        cfg["victron_ip"] = CORE_DEFAULTS["victron_host"]

    if "whatsapp_alerts_enabled" not in loaded_keys and cfg.get("telegram_alerts_enabled") is not None:
        cfg["whatsapp_alerts_enabled"] = cfg["telegram_alerts_enabled"]
    if "whatsapp_alert_cooldown_s" not in loaded_keys and cfg.get("telegram_alert_cooldown_s") is not None:
        cfg["whatsapp_alert_cooldown_s"] = cfg["telegram_alert_cooldown_s"]

    jk_hosts = [cfg.get(f"jk_host_{i}") for i in range(1, 9) if cfg.get(f"jk_host_{i}")]
    if jk_hosts and not cfg.get("batteries"):
        cfg["batteries"] = [
            {
                "name": f"Batería {i}",
                "jk_host": host,
                "jk_port": cfg.get("jk_port", 6481),
            }
            for i, host in enumerate(jk_hosts, start=1)
        ]

    for idx, battery in enumerate(cfg.get("batteries", [])):
        battery.setdefault("id", f"bateria_{idx + 1}")
        battery.setdefault("enabled", True)
        battery.setdefault("cell_count", cfg.get("cell_count", 16))
        battery.setdefault("jk_unit_id", 1)
        battery.setdefault("jk_port", cfg.get("jk_port", 6481))
        flat_host = cfg.get(f"jk_host_{idx + 1}")
        if flat_host:
            battery["jk_host"] = flat_host

    enabled_batteries = [b for b in cfg.get("batteries", []) if b.get("enabled", True)]
    if (
        cfg.get("battery_bank_mode", "parallel") == "parallel"
        and len(enabled_batteries) > 1
        and "battery_capacity_kwh" not in loaded_keys
    ):
        per_unit = cfg.get("battery_capacity_kwh_per_unit", cfg.get("battery_capacity_kwh", 10.0))
        cfg["battery_capacity_kwh"] = per_unit * len(enabled_batteries)

    return cfg


def load_configuration(
    config_path: Path | str | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Carga config.json mezclando defaults del módulo.

    Acepta victron_host (preferido) o victron_ip; ambos quedan disponibles.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    base = {**CORE_DEFAULTS, **(defaults or {})}

    if not path.exists():
        logger.warning(
            "Archivo de configuración %s no encontrado. Usando valores por defecto.",
            path,
        )
        return normalize_config(dict(base), loaded_keys=set())

    with open(path, encoding="utf-8-sig") as f:
        loaded = json.load(f)

    if not isinstance(loaded, dict):
        raise ValueError(f"Config inválida en {path}: se esperaba un objeto JSON")

    merged = {**base, **loaded}
    return normalize_config(merged, loaded_keys=set(loaded.keys()))
