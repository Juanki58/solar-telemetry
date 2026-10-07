"""
Cliente Modbus TCP para JK BMS v19 — lectura de voltajes celda a celda.

battery_source:
  - victron | gx_can — pack vía Victron GX (JK en CAN/DVCC; sin celdas TCP)
  - jk_tcp — pack + celdas solo desde JK Modbus TCP en LAN
  - hybrid — pack/SoC/V/I desde Victron; celdas C1…C16 desde JK TCP
    (RS485→Ethernet/WiFi gateway; CAN Victron intacto)

Mapa de registros JK (holding, escala mV → V con factor 1000):
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

BATTERY_SOURCE_JK_TCP = "jk_tcp"
BATTERY_SOURCE_VICTRON = "victron"
BATTERY_SOURCE_GX_CAN = "gx_can"
BATTERY_SOURCE_HYBRID = "hybrid"
_VICTRON_SOURCES = frozenset({BATTERY_SOURCE_VICTRON, BATTERY_SOURCE_GX_CAN})
_JK_CELL_SOURCES = frozenset({BATTERY_SOURCE_JK_TCP, BATTERY_SOURCE_HYBRID})

_JK_FAIL_CACHE: dict[str, float] = {}


def resolve_battery_source(cfg: dict | None) -> str:
    """victron | gx_can | jk_tcp | hybrid (pack Victron + celdas JK TCP)."""
    raw = str((cfg or {}).get("battery_source") or BATTERY_SOURCE_VICTRON).strip().lower()
    if raw in ("gx", "can", "victron_can", "gx_can"):
        return BATTERY_SOURCE_GX_CAN
    if raw in ("victron", "gx_modbus", "system"):
        return BATTERY_SOURCE_VICTRON
    if raw in ("jk_tcp", "jk", "jk_bms", "modbus_jk"):
        return BATTERY_SOURCE_JK_TCP
    if raw in (
        "hybrid",
        "victron_jk",
        "victron+jk",
        "victron_jk_tcp",
        "dual",
        "pack_victron_cells_jk",
    ):
        return BATTERY_SOURCE_HYBRID
    if raw in _VICTRON_SOURCES or raw in _JK_CELL_SOURCES:
        return raw
    # Desconocido → pack Victron (honesto) en vez de inventar celdas JK TCP.
    return BATTERY_SOURCE_VICTRON


def uses_victron_battery(cfg: dict | None) -> bool:
    """True solo si el pack viene de Victron y NO se leen celdas JK TCP."""
    return resolve_battery_source(cfg) in _VICTRON_SOURCES


def uses_hybrid_battery(cfg: dict | None) -> bool:
    return resolve_battery_source(cfg) == BATTERY_SOURCE_HYBRID


def uses_jk_cell_source(cfg: dict | None) -> bool:
    """True si se intentan celdas vía Modbus TCP del JK (jk_tcp o hybrid)."""
    return resolve_battery_source(cfg) in _JK_CELL_SOURCES


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
        if simulated:
            # Solo laboratorio intencional: celdas sintéticas etiquetadas.
            return _read_simulated_bank(bank_cfg, sim_t, data_source="simulated")
        # Host inválido: vacío honesto — nunca grid sinusoidal fingiendo mediciones.
        return _empty_jk_bank(
            bank_cfg,
            data_source="jk_unconfigured",
            cell_voltage_source="JK BMS v19 — IP pendiente de configurar",
            error=f"Host JK no configurado: {bank_cfg.get('jk_host')}",
        )

    cache_key = _jk_cache_key(bank_cfg)
    if _jk_recently_failed(cache_key):
        return _empty_jk_bank(
            bank_cfg,
            data_source="jk_fallback",
            cell_voltage_source=f"JK BMS v19 — cooldown ({bank_cfg['jk_host']})",
            error="Conexión JK en cooldown tras fallo reciente",
        )

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
            "data_source": "jk_modbus",
            "jk_online": True,
            "jk_host": host,
            "error": None,
        }
    except Exception as exc:
        logger.error("JK %s FALLO (%s:%s): %s: %s", bank_name, host, port, type(exc).__name__, exc)
        _JK_FAIL_CACHE[cache_key] = time.time()
        # Sin conexión: vacío honesto — no inventar celdas sinusoidales.
        return _empty_jk_bank(
            bank_cfg,
            data_source="jk_fallback",
            cell_voltage_source=f"JK BMS v19 — sin conexión ({host})",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        client.close()


def _empty_jk_bank(
    bank_cfg: dict,
    *,
    data_source: str,
    cell_voltage_source: str,
    error: str | None,
) -> dict[str, Any]:
    """Banco sin celdas medibles (fallo TCP / sin configurar).

    Nunca rellena voltajes sintéticos: la UI debe mostrar «celdas no disponibles».
    """
    bank_id = bank_cfg.get("id", "bank")
    bank_name = bank_cfg.get("name", bank_id)
    return {
        "id": bank_id,
        "name": bank_name,
        "cells": [],
        "cell_voltages": [],
        "highest_cell_voltage": None,
        "lowest_cell_voltage": None,
        "max_cell_index": None,
        "min_cell_index": None,
        "max_pack_temperature": None,
        "min_pack_temperature": None,
        "soc": None,
        "cell_voltage_source": cell_voltage_source,
        "data_source": data_source,
        "cells_available": False,
        "jk_online": False,
        "jk_host": bank_cfg.get("jk_host"),
        "error": error,
    }


def _read_simulated_bank(
    bank_cfg: dict,
    sim_t: float | None = None,
    *,
    data_source: str = "simulated",
) -> dict[str, Any]:
    """Genera 16 celdas simuladas — SOLO modo laboratorio intencional.

    No usar para jk_fallback / jk_unconfigured (ver `_empty_jk_bank`).
    """
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
        "cell_voltage_source": "Simulación JK BMS v19 (laboratorio)",
        "data_source": data_source,
        # Nunca marcar simulación como online real.
        "jk_online": False,
        "jk_host": bank_cfg.get("jk_host"),
        "error": None,
    }


def build_victron_pack_bank(
    system_telemetry: dict | None = None,
    cfg: dict | None = None,
    *,
    simulated: bool = False,
) -> dict[str, Any]:
    """
    Banco a nivel de pack desde Victron GX (JK vía CAN/DVCC).

    Sin celdas individuales: el servicio de batería agregado no expone
    CellVol0..N por Modbus TCP estándar. Nunca marca jk_online=True.
    """
    cfg = cfg or {}
    system = system_telemetry or {}
    name = cfg.get("battery_pack_name") or "Batería (Victron GX / CAN)"
    temp = system.get("max_pack_temperature")
    if temp is None:
        temp = system.get("battery_temperature")

    if simulated and system.get("source") == "simulated":
        data_source = "simulated"
        source_label = "Simulación pack Victron (laboratorio)"
    else:
        data_source = "victron_gx"
        source_label = "Victron GX Modbus (pack; celdas no expuestas vía CAN)"

    return {
        "id": "pack_victron",
        "name": name,
        "cells": [],
        "cell_voltages": [],
        "highest_cell_voltage": None,
        "lowest_cell_voltage": None,
        "max_cell_index": None,
        "min_cell_index": None,
        "max_pack_temperature": temp,
        "min_pack_temperature": system.get("min_pack_temperature", temp),
        "soc": system.get("soc"),
        "pack_voltage": system.get("pack_voltage"),
        "battery_current_a": system.get("battery_current_a"),
        "battery_power_w": system.get("battery_power_w"),
        "cell_voltage_source": source_label,
        "data_source": data_source,
        "cells_available": False,
        "jk_online": False,
        "jk_host": None,
        "error": None,
    }


def fetch_all_batteries(
    cfg: dict,
    simulated: bool = False,
    sim_t: float | None = None,
    system_telemetry: dict | None = None,
) -> list[dict[str, Any]]:
    """Lee bancos JK TCP, pack Victron, o hybrid (JK celdas + pack en merge)."""
    if uses_victron_battery(cfg):
        if simulated and (system_telemetry is None or system_telemetry.get("source") != "simulated"):
            # Laboratorio sin telemetría de sistema: pack simulado vacío de celdas.
            stub = {
                "soc": 42.0,
                "pack_voltage": 53.2,
                "battery_current_a": -12.5,
                "battery_power_w": -665.0,
                "max_pack_temperature": 28.5,
                "min_pack_temperature": 27.0,
                "source": "simulated",
            }
            return [build_victron_pack_bank(stub, cfg, simulated=True)]
        return [build_victron_pack_bank(system_telemetry, cfg, simulated=simulated)]

    # jk_tcp y hybrid: celdas desde gateway/JK Modbus TCP.
    banks_cfg = normalize_battery_configs(cfg)
    return [read_jk_bms_bank(bank, simulated=simulated, sim_t=sim_t) for bank in banks_cfg]


def normalize_battery_configs(cfg: dict) -> list[dict]:
    """Devuelve la lista de baterías activas; crea un banco por defecto si falta."""
    if uses_victron_battery(cfg):
        return [
            {
                "id": "pack_victron",
                "name": cfg.get("battery_pack_name") or "Batería (Victron GX / CAN)",
                "enabled": True,
                "cell_count": 0,
            }
        ]

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
    """Combina telemetría Victron/simulada con datos JK por banco, pack GX o hybrid."""
    cfg = cfg or {}
    merged = {**system_telemetry, "batteries": batteries}
    src = resolve_battery_source(cfg)
    merged["battery_source"] = src
    merged["cells_available"] = False

    soc, soc_label = _resolve_system_soc(system_telemetry, batteries, cfg)
    merged["soc"] = soc
    merged["soc_source_label"] = soc_label
    merged["victron_soc"] = system_telemetry.get("soc")

    if uses_victron_battery(cfg):
        merged["cells_available"] = False
        merged["cell_voltages"] = []
        merged["highest_cell_voltage"] = None
        merged["lowest_cell_voltage"] = None
        merged["cell_voltage_source"] = (
            "Celdas no disponibles — JK en CAN Victron (solo métricas de pack)"
        )
        # Pack V/I/T ya vienen del system; no inventar celdas ni marcar JK online.
        if batteries:
            pack = batteries[0]
            if pack.get("max_pack_temperature") is not None:
                merged["max_pack_temperature"] = pack["max_pack_temperature"]
            if pack.get("min_pack_temperature") is not None:
                merged["min_pack_temperature"] = pack["min_pack_temperature"]
            if pack.get("pack_voltage") is not None:
                merged["pack_voltage"] = pack["pack_voltage"]
        return merged

    # jk_tcp / hybrid: solo bancos con lectura JK real aportan celdas.
    # Pack SoC/V/I ya vienen de system_telemetry (Victron) en hybrid.
    # Fallback/unconfigured vienen vacíos; simulación de lab solo en modo simulated.
    online_banks = [
        b
        for b in batteries
        if b.get("data_source") == "jk_modbus"
        and b.get("jk_online")
        and b.get("jk_host")
        and not b.get("error")
        and (b.get("cell_voltages") or b.get("cells"))
    ]
    lab_sim_banks = [
        b
        for b in batteries
        if b.get("data_source") == "simulated" and (b.get("cell_voltages") or b.get("cells"))
    ]
    unavailable = [
        b
        for b in batteries
        if b.get("data_source") in ("jk_fallback", "jk_unconfigured")
        or (
            b.get("data_source") != "jk_modbus"
            and b.get("data_source") != "simulated"
            and not (b.get("cell_voltages") or b.get("cells"))
        )
    ]

    source_banks = online_banks if online_banks else lab_sim_banks
    all_cells: list[float] = []
    for bank in source_banks:
        all_cells.extend(bank.get("cells") or bank.get("cell_voltages") or [])

    if all_cells and online_banks:
        merged["highest_cell_voltage"] = max(all_cells)
        merged["lowest_cell_voltage"] = min(all_cells)
        merged["cell_voltages"] = all_cells
        merged["cells_available"] = True
        if src == BATTERY_SOURCE_HYBRID:
            merged["cell_voltage_source"] = (
                f"Hybrid: pack Victron + JK TCP "
                f"({len(online_banks)}/{len(batteries)} bancos online)"
            )
        else:
            merged["cell_voltage_source"] = (
                f"JK BMS v19 — {len(online_banks)}/{len(batteries)} bancos online"
            )
    elif all_cells and lab_sim_banks and not online_banks:
        # Laboratorio explícito: celdas sintéticas, nunca como «medición».
        merged["highest_cell_voltage"] = max(all_cells)
        merged["lowest_cell_voltage"] = min(all_cells)
        merged["cell_voltages"] = all_cells
        merged["cells_available"] = False
        merged["cell_voltage_source"] = "Simulación laboratorio (JK)"
    else:
        merged["highest_cell_voltage"] = None
        merged["lowest_cell_voltage"] = None
        merged["cell_voltages"] = []
        merged["cells_available"] = False
        n_fail = len(unavailable) or len(batteries)
        if src == BATTERY_SOURCE_HYBRID:
            merged["cell_voltage_source"] = (
                f"Hybrid: pack Victron OK — celdas JK TCP pendientes "
                f"({n_fail} banco(s) sin lectura; probar puerto 502)"
            )
        else:
            merged["cell_voltage_source"] = (
                f"Celdas no disponibles — JK TCP sin lectura ({n_fail} banco(s))"
            )

    temps_high = [
        b["max_pack_temperature"]
        for b in online_banks
        if b.get("max_pack_temperature") is not None
    ]
    temps_low = [
        b["min_pack_temperature"]
        for b in online_banks
        if b.get("min_pack_temperature") is not None
    ]
    if temps_high:
        merged["max_pack_temperature"] = max(temps_high)
    if temps_low:
        merged["min_pack_temperature"] = min(temps_low)

    return merged
