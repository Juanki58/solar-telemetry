"""
Cliente Modbus TCP para JK BMS v19 — lectura de voltajes celda a celda.

Mapa de registros (holding, escala mV → V con factor 1000):
  0x1200  CellVol0..15   (16 celdas, UINT16 cada una)
  0x1248  MinVolCellNbr / MaxVolCellNbr (UINT8 bajo / UINT8 alto)
  0x12A4  Temperatura batería 1 (UINT16, escala 0.1 °C)
"""

import logging
import math
import time
from typing import Any

from pyModbusTCP.client import ModbusClient

logger = logging.getLogger(__name__)

JK_CELL_VOLTAGE_REG = 0x1200
JK_MAX_MIN_CELL_REG = 0x1248
JK_BATTERY_TEMP_REG = 0x12A4
JK_SOC_REG = 0x12A6
JK_DEFAULT_PORT = 502
JK_DEFAULT_UNIT_ID = 1
JK_CELL_VOLTAGE_SCALE = 1000.0
JK_TEMPERATURE_SCALE = 10.0
JK_DEFAULT_TIMEOUT_S = 2.0
JK_FAIL_COOLDOWN_S = 30.0

_JK_FAIL_CACHE: dict[str, float] = {}


def _jk_cache_key(bank_cfg: dict) -> str:
    return (
        f"{bank_cfg.get('jk_host')}:{bank_cfg.get('jk_port', JK_DEFAULT_PORT)}:"
        f"{bank_cfg.get('jk_unit_id', JK_DEFAULT_UNIT_ID)}"
    )


def _jk_recently_failed(cache_key: str) -> bool:
    last_fail = _JK_FAIL_CACHE.get(cache_key)
    return last_fail is not None and (time.time() - last_fail) < JK_FAIL_COOLDOWN_S


def _is_valid_jk_host(host: str | None) -> bool:
    if not host:
        return False
    upper = host.upper()
    return "IP_DE" not in upper and "TU_" not in upper and "EJEMPLO" not in upper


def read_jk_bms_bank(bank_cfg: dict, simulated: bool = False, sim_t: float | None = None) -> dict[str, Any]:
    """
    Lee telemetría de un JK BMS v19.
    Devuelve cell_voltages (16), temperaturas y metadatos de conexión.
    """
    bank_id = bank_cfg.get("id", "bank")
    bank_name = bank_cfg.get("name", bank_id)
    cell_count = int(bank_cfg.get("cell_count", 16))

    if simulated or not _is_valid_jk_host(bank_cfg.get("jk_host")):
        result = _read_simulated_bank(bank_cfg, sim_t)
        if bank_cfg.get("jk_host") and not _is_valid_jk_host(bank_cfg.get("jk_host")):
            result["jk_online"] = False
            result["cell_voltage_source"] = "JK BMS v19 — IP pendiente de configurar"
            result["error"] = f"Host JK no configurado: {bank_cfg.get('jk_host')}"
        return result

    cache_key = _jk_cache_key(bank_cfg)
    if _jk_recently_failed(cache_key):
        fallback = _read_simulated_bank(bank_cfg, sim_t)
        fallback["jk_online"] = False
        fallback["cell_voltage_source"] = f"JK BMS v19 — cooldown ({bank_cfg['jk_host']})"
        fallback["error"] = "Conexión JK en cooldown tras fallo reciente"
        return fallback

    host = bank_cfg["jk_host"]
    port = int(bank_cfg.get("jk_port", JK_DEFAULT_PORT))
    unit_id = int(bank_cfg.get("jk_unit_id", JK_DEFAULT_UNIT_ID))
    cell_reg = int(bank_cfg.get("jk_cell_voltage_reg", JK_CELL_VOLTAGE_REG))
    temp_reg = int(bank_cfg.get("jk_battery_temp_reg", JK_BATTERY_TEMP_REG))
    timeout = float(bank_cfg.get("jk_timeout_s", JK_DEFAULT_TIMEOUT_S))

    client = ModbusClient(host=host, port=port, unit_id=unit_id, auto_open=True, timeout=timeout)

    try:
        if not client.open():
            raise ConnectionError(f"No se pudo conectar con JK BMS en {host}:{port} (unit {unit_id})")

        raw_cells = client.read_holding_registers(cell_reg, cell_count)
        if not raw_cells or len(raw_cells) < cell_count:
            raise ConnectionError(
                f"Lectura incompleta de celdas en {bank_name}: "
                f"{len(raw_cells) if raw_cells else 0}/{cell_count} registros"
            )

        cell_voltages = [round(v / JK_CELL_VOLTAGE_SCALE, 3) for v in raw_cells[:cell_count]]

        max_cell_idx = None
        min_cell_idx = None
        try:
            max_min_regs = client.read_holding_registers(
                int(bank_cfg.get("jk_max_min_cell_reg", JK_MAX_MIN_CELL_REG)), 1
            )
            if max_min_regs:
                word = max_min_regs[0]
                min_cell_idx = (word & 0x00FF) + 1
                max_cell_idx = ((word >> 8) & 0x00FF) + 1
        except Exception as exc:
            logger.warning("JK %s: no se leyeron índices max/min celda: %s", bank_name, exc)

        temperature = None
        try:
            temp_regs = client.read_holding_registers(temp_reg, 1)
            if temp_regs:
                temperature = round(temp_regs[0] / JK_TEMPERATURE_SCALE, 1)
        except Exception as exc:
            logger.warning("JK %s: no se leyó temperatura: %s", bank_name, exc)

        soc = None
        try:
            soc_reg = int(bank_cfg.get("jk_soc_reg", JK_SOC_REG))
            soc_regs = client.read_holding_registers(soc_reg, 1)
            if soc_regs:
                word = soc_regs[0]
                soc_high = (word >> 8) & 0xFF
                soc_low = word & 0xFF
                if 0 < soc_high <= 100:
                    soc = soc_high
                elif 0 < soc_low <= 100:
                    soc = soc_low
                logger.info(
                    "JK %s SoC — reg 0x%X: high=%s low=%s → %s%%",
                    bank_name,
                    soc_reg,
                    soc_high,
                    soc_low,
                    soc,
                )
        except Exception as exc:
            logger.warning("JK %s: no se leyó SoC: %s", bank_name, exc)

        v_max = max(cell_voltages)
        v_min = min(cell_voltages)

        logger.info(
            "JK %s OK — %s:%s unit %s · %d celdas · Vmax=%.3f C%s · Vmin=%.3f C%s",
            bank_name,
            host,
            port,
            unit_id,
            cell_count,
            v_max,
            max_cell_idx or "?",
            v_min,
            min_cell_idx or "?",
        )

        return {
            "id": bank_id,
            "name": bank_name,
            "cells": cell_voltages,
            "cell_voltages": cell_voltages,
            "highest_cell_voltage": v_max,
            "lowest_cell_voltage": v_min,
            "max_cell_index": max_cell_idx,
            "min_cell_index": min_cell_idx,
            "max_pack_temperature": temperature if temperature is not None else 25.0,
            "min_pack_temperature": (temperature - 1.0) if temperature is not None else 24.0,
            "soc": soc,
            "cell_voltage_source": f"JK BMS v19 Modbus ({host})",
            "jk_online": True,
            "jk_host": host,
            "error": None,
        }
    except Exception as exc:
        logger.error("JK %s FALLO (%s:%s): %s: %s", bank_name, host, port, type(exc).__name__, exc)
        _JK_FAIL_CACHE[cache_key] = time.time()
        fallback = _read_simulated_bank(bank_cfg, sim_t)
        fallback["jk_online"] = False
        fallback["cell_voltage_source"] = f"JK BMS v19 — sin conexión ({host})"
        fallback["error"] = f"{type(exc).__name__}: {exc}"
        return fallback
    finally:
        client.close()


def _read_simulated_bank(bank_cfg: dict, sim_t: float | None = None) -> dict[str, Any]:
    """Genera 16 celdas simuladas con patrón distinto por banco."""
    bank_id = bank_cfg.get("id", "bank")
    bank_name = bank_cfg.get("name", bank_id)
    cell_count = int(bank_cfg.get("cell_count", 16))
    seed = sum(ord(c) for c in bank_id)
    t = sim_t or time.time()

    base = 3.318 + 0.004 * math.sin(t / 28 + seed * 0.1)
    cell_voltages = [
        round(base + 0.003 * math.sin(t / 9 + i * 0.85 + seed) + 0.001 * (i % 3), 3)
        for i in range(cell_count)
    ]

    temp = round(27.5 + 1.5 * math.sin(t / 40 + seed * 0.05), 1)
    soc = round(68 + 4 * math.sin(t / 50 + seed * 0.07), 1)
    return {
        "id": bank_id,
        "name": bank_name,
        "cells": cell_voltages,
        "cell_voltages": cell_voltages,
        "highest_cell_voltage": max(cell_voltages),
        "lowest_cell_voltage": min(cell_voltages),
        "max_cell_index": cell_voltages.index(max(cell_voltages)) + 1,
        "min_cell_index": cell_voltages.index(min(cell_voltages)) + 1,
        "max_pack_temperature": temp,
        "min_pack_temperature": round(temp - 1.2, 1),
        "soc": soc,
        "cell_voltage_source": "Simulación JK BMS v19",
        "jk_online": True,
        "jk_host": bank_cfg.get("jk_host"),
        "error": None,
    }


def fetch_all_batteries(cfg: dict, simulated: bool = False, sim_t: float | None = None) -> list[dict[str, Any]]:
    """Lee todos los bancos configurados en cfg['batteries']."""
    banks_cfg = normalize_battery_configs(cfg)
    return [read_jk_bms_bank(bank, simulated=simulated, sim_t=sim_t) for bank in banks_cfg]


def normalize_battery_configs(cfg: dict) -> list[dict]:
    """Devuelve la lista de baterías activas; crea un banco por defecto si falta."""
    batteries = cfg.get("batteries")
    if batteries:
        return [b for b in batteries if b.get("enabled", True)]

    return [
        {
            "id": "bank_1",
            "name": "Banco LiFePO4",
            "cell_count": cfg.get("cell_count", 16),
            "jk_host": cfg.get("jk_host"),
            "jk_port": cfg.get("jk_port", JK_DEFAULT_PORT),
            "jk_unit_id": cfg.get("jk_unit_id", JK_DEFAULT_UNIT_ID),
            "enabled": True,
        }
    ]


def _aggregate_parallel_soc(bank_socs: list[float]) -> float:
    """Baterías en paralelo comparten el mismo % de carga → media, nunca suma."""
    if not bank_socs:
        return 0.0
    return round(sum(bank_socs) / len(bank_socs), 1)


def _resolve_system_soc(system_telemetry: dict, batteries: list[dict], cfg: dict) -> tuple[float, str]:
    victron_soc = system_telemetry.get("soc")
    bank_mode = cfg.get("battery_bank_mode", "parallel")

    if victron_soc is not None:
        victron_soc = round(min(max(float(victron_soc), 0.0), 100.0), 1)

    # Banco paralelo: el Cerbo GX mide el pack completo — nunca sumar ni promediar JK.
    if bank_mode == "parallel" and victron_soc is not None:
        return victron_soc, "Victron Cerbo GX (sistema completo)"

    if cfg.get("soc_source") == "jk":
        jk_socs = [
            b["soc"]
            for b in batteries
            if b.get("soc") is not None and b.get("jk_online") and not b.get("error")
        ]
        if jk_socs:
            return _aggregate_parallel_soc(jk_socs), f"JK BMS v19 — media {len(jk_socs)} bancos"

    if victron_soc is not None:
        return victron_soc, "Victron Modbus"

    return 0.0, "desconocido"


def merge_battery_telemetry(system_telemetry: dict, batteries: list[dict], cfg: dict | None = None) -> dict:
    """Combina telemetría Victron/simulada con datos JK por banco."""
    cfg = cfg or {}
    merged = {**system_telemetry, "batteries": batteries}

    soc, soc_label = _resolve_system_soc(system_telemetry, batteries, cfg)
    merged["soc"] = soc
    merged["soc_source_label"] = soc_label
    merged["victron_soc"] = system_telemetry.get("soc")

    jk_banks = [b for b in batteries if b.get("cell_voltages") or b.get("cells")]
    if not jk_banks:
        return merged

    all_cells: list[float] = []
    for bank in jk_banks:
        all_cells.extend(bank.get("cells") or bank.get("cell_voltages") or [])

    online_banks = [
        b
        for b in jk_banks
        if b.get("jk_online")
        and b.get("jk_host")
        and "sin conexión" not in (b.get("cell_voltage_source") or "")
        and "cooldown" not in (b.get("cell_voltage_source") or "")
    ]

    merged["highest_cell_voltage"] = max(all_cells)
    merged["lowest_cell_voltage"] = min(all_cells)
    merged["cell_voltages"] = all_cells

    if online_banks:
        merged["cell_voltage_source"] = (
            f"JK BMS v19 — {len(online_banks)}/{len(jk_banks)} bancos online"
        )
    else:
        merged["cell_voltage_source"] = (
            f"JK BMS v19 — fallback ({len(jk_banks)} bancos sin conexión)"
        )

    temps_high = [b["max_pack_temperature"] for b in jk_banks if b.get("max_pack_temperature") is not None]
    temps_low = [b["min_pack_temperature"] for b in jk_banks if b.get("min_pack_temperature") is not None]
    if temps_high:
        merged["max_pack_temperature"] = max(temps_high)
    if temps_low:
        merged["min_pack_temperature"] = min(temps_low)

    return merged
