"""
Supervisor de seguridad Victron ↔ JK BMS (experimental).

IMPORTANTE
----------
- Por defecto opera en DRY-RUN (solo lectura / log). No escribe en Victron
  salvo que `safety_write_enabled` sea true en config.json.
- NUNCA actúa sobre telemetría simulada ni fallback: exige lecturas reales
  de JK (y, si se usa, Victron). Si la fuente no es fiable, se niega la escritura.
- `safety_require_jk_online=false` NO relaja las puertas de fuente de verdad:
  sim/fallback/unknown nunca obtienen write_allowed.
- Registros 2704/2705/2706 están bloqueados hasta auditar el mapa Victron de
  la planta; hace falta además `safety_write_registers_confirmed: true`.
- Esto NO es un BMS certificado. Los cortes activos son experimentales y
  no sustituyen protecciones hardware ni un BMS homologado.
  Ver docs/SAFETY_DISCLAIMER.md.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Any

from pyModbusTCP.client import ModbusClient

from config_loader import load_configuration
from jk_bms_client import fetch_all_batteries, merge_battery_telemetry, uses_victron_battery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
)
logger = logging.getLogger("bintelligent.safety")

SAFETY_DEFAULTS: dict[str, Any] = {
    "safety_write_enabled": False,
    "safety_require_jk_online": True,
    # Mapa de registros Victron (2704/05/06) no auditado por planta → bloqueado.
    "safety_write_registers_confirmed": False,
    "safety_loop_interval_s": 5,
}

# Hasta validar el Unit ID / mapa ESS de esta planta, estas escrituras son riesgo.
UNVALIDATED_VICTRON_WRITE_REGS = frozenset({2704, 2705, 2706})
REAL_LIVE_SOURCES = frozenset({"jk_modbus"})
UNRELIABLE_BANK_SOURCES = frozenset({"simulated", "jk_fallback", "jk_unconfigured"})


class VictronBmsSafetySupervisor:
    """Supervisa umbrales y, solo si está habilitado, escribe registros Victron."""

    def __init__(self, config_path=None, *, force_dry_run: bool | None = None):
        self.config_path = Path(config_path) if config_path else (
            Path(__file__).resolve().parent / "config.json"
        )
        self.config = load_configuration(self.config_path, defaults=SAFETY_DEFAULTS)

        write_flag = bool(self.config.get("safety_write_enabled", False))
        if force_dry_run is True:
            write_flag = False
        self.write_enabled = write_flag
        self.dry_run = not self.write_enabled
        self.registers_confirmed = bool(
            self.config.get("safety_write_registers_confirmed", False)
        )

        self.victron_client = ModbusClient(
            host=self.config["victron_host"],
            port=self.config["modbus_port"],
            unit_id=self.config["victron_unit_id"],
            auto_open=True,
        )

        mode = "ESCRITURA ACTIVA (experimental)" if self.write_enabled else "DRY-RUN / solo lectura"
        logger.warning(
            "=== Supervisor BMS Victron — %s ===",
            mode,
        )
        logger.warning(
            "AVISO: cortes activos NO son un BMS certificado. "
            "Uso experimental / planta propia. Ver docs/SAFETY_DISCLAIMER.md"
        )
        if not self.registers_confirmed:
            logger.warning(
                "Registros 2704/2705/2706 BLOQUEADOS (mapa Victron no confirmado). "
                'Para desbloquear tras auditoría: "safety_write_registers_confirmed": true'
            )
        if self.dry_run:
            logger.info(
                "Escrituras Modbus deshabilitadas. "
                "Para habilitar (bajo tu responsabilidad): "
                '"safety_write_enabled": true en config.json'
            )

    def read_bms_telemetry(self) -> dict[str, Any]:
        """
        Lee telemetría REAL de bancos JK (jk_tcp/hybrid) o pack Victron (victron/gx_can).

        Si no hay datos JK fiables, marca source=unreliable y no permite writes.
        En modo Victron/CAN puro no hay celdas: los cortes por celda quedan denegados.
        En hybrid, los cortes por celda exigen lectura JK TCP live (como jk_tcp).

        Importante: `safety_require_jk_online=false` NO autoriza write_allowed
        sobre simulación, fallback o fuentes desconocidas.
        """
        if uses_victron_battery(self.config):
            merged = {
                "soc": None,
                "source": "unreliable",
                "error": (
                    "battery_source=victron/gx_can: sin celdas JK TCP. "
                    "Cortes activos por celda no aplicables (solo pack vía GX)."
                ),
                "write_allowed": False,
                "cells_available": False,
                "batteries": fetch_all_batteries(self.config, simulated=False),
                "house_consumption_w": 0,
                "pv_power_w": 0,
                "battery_power_w": 0,
                "grid_power_w": 0,
            }
            return merged

        batteries = fetch_all_batteries(self.config, simulated=False, sim_t=None)
        system_stub = {
            "soc": None,
            "source": "jk_only",
            "error": None,
            "house_consumption_w": 0,
            "pv_power_w": 0,
            "battery_power_w": 0,
            "grid_power_w": 0,
        }
        merged = merge_battery_telemetry(system_stub, batteries, self.config)

        real_banks = [
            b
            for b in batteries
            if b.get("data_source") == "jk_modbus"
            and b.get("jk_online")
            and not b.get("error")
            and (b.get("cell_voltages") or b.get("cells"))
        ]
        sim_or_fallback = [
            b
            for b in batteries
            if b.get("data_source") in UNRELIABLE_BANK_SOURCES
            or b.get("data_source") not in REAL_LIVE_SOURCES
            or not b.get("jk_online")
            or b.get("error")
            or not (b.get("cell_voltages") or b.get("cells"))
        ]

        if not batteries:
            merged["source"] = "unreliable"
            merged["error"] = "No hay bancos JK configurados"
            merged["write_allowed"] = False
            return merged

        # Puerta dura de fuente de verdad: nunca write_allowed sin JK real live.
        # safety_require_jk_online=false NO puede relajar esto.
        if not real_banks:
            merged["source"] = "unreliable"
            merged["error"] = (
                "Ningún JK online con lectura real "
                f"(sim/fallback/unknown: {len(sim_or_fallback)}). "
                "safety_require_jk_online no autoriza escrituras sobre datos no reales."
            )
            merged["write_allowed"] = False
            return merged

        if sim_or_fallback:
            # Telemetría parcial / mezcla no es suficiente para writes.
            names = ", ".join(b.get("name", "?") for b in sim_or_fallback)
            merged["source"] = "unreliable"
            merged["error"] = (
                f"Bancos sin lectura real JK (write bloqueado): {names}. "
                "Fuente de verdad incompleta — no se relaja con safety_require_jk_online=false."
            )
            merged["write_allowed"] = False
            return merged

        # require_jk_online=true (default): ya cubierto arriba.
        # require_jk_online=false: solo permitiría writes si TODOS los bancos son
        # jk_modbus live (mismo camino). Nunca sim/fallback.
        merged["source"] = "jk_modbus"
        merged["error"] = None
        merged["write_allowed"] = True
        merged["jk_online_count"] = len(real_banks)
        return merged

    def _refuse_write(self, reason: str) -> bool:
        logger.error("ESCRITURA DENEGADA: %s", reason)
        return False

    def _register_write_allowed(self, register: int) -> bool:
        """Bloquea 2704/05/06 hasta confirmar mapa Victron de la planta."""
        if int(register) not in UNVALIDATED_VICTRON_WRITE_REGS:
            return True
        if self.registers_confirmed:
            return True
        self._refuse_write(
            f"registro Victron {register} bloqueado: mapa no auditado para esta planta. "
            "Riesgo de escribir consignas ESS/inversor incorrectas. "
            'Tras validar Unit ID + mapa: "safety_write_registers_confirmed": true '
            "(sigue haciendo falta safety_write_enabled=true). Ver docs/SAFETY_DISCLAIMER.md"
        )
        return False

    def aplicar_contramedida_victron(self, register, value, descripcion, *, telemetry: dict | None = None):
        """
        Escribe en Victron solo si write_enabled, telemetría real fiable y
        registros confirmados (2704/05/06). En dry-run solo registra la acción.
        """
        telemetry = telemetry or {}

        if telemetry.get("source") in ("simulated", "unreliable", "modbus_error", None):
            src = telemetry.get("source")
            err = telemetry.get("error") or "fuente no fiable"
            return self._refuse_write(
                f"telemetría no real (source={src}): {err}. "
                "Nunca se escribe sobre datos simulados/fallback."
            )

        if telemetry.get("source") not in REAL_LIVE_SOURCES:
            return self._refuse_write(
                f"source={telemetry.get('source')!r} no es camino live verificado "
                f"(requerido: {sorted(REAL_LIVE_SOURCES)})"
            )

        if telemetry.get("write_allowed") is not True:
            return self._refuse_write(
                telemetry.get("error") or "write_allowed no es True"
            )

        if not self._register_write_allowed(register):
            return False

        if self.dry_run or not self.write_enabled:
            logger.warning(
                "[DRY-RUN] Se habría aplicado: %s (Reg: %s -> Val: %s) — "
                "sin escritura Modbus",
                descripcion,
                register,
                value,
            )
            return True

        if not self.victron_client.is_open and not self.victron_client.open():
            return self._refuse_write("Conexión Modbus TCP cerrada con el Color Control GX.")

        success = self.victron_client.write_single_register(register, value)
        if success:
            logger.warning(
                "✔ Contramedida aplicada (EXPERIMENTAL, no BMS certificado): "
                "%s (Reg: %s -> Val: %s)",
                descripcion,
                register,
                value,
            )
            return True

        logger.error("❌ Fallo crítico al escribir en el registro Modbus de Victron: %s", register)
        return False

    def supervisar_planta(self) -> dict[str, Any]:
        telemetria = self.read_bms_telemetry()
        cfg = self.config

        if telemetria.get("source") != "jk_modbus" or telemetria.get("write_allowed") is not True:
            logger.warning(
                "Sin telemetría JK real — no se evaluarán escrituras. %s",
                telemetria.get("error") or telemetria.get("source"),
            )
            # Aun así logueamos números si existen (pueden ser vacíos) marcados como no-acción.
            if telemetria.get("highest_cell_voltage") is not None:
                logger.info(
                    "Monitor (NO ESCRIBIR) -> Celda Máx: %sV | Celda Mín: %sV | Temp Máx: %s°C | source=%s",
                    telemetria.get("highest_cell_voltage"),
                    telemetria.get("lowest_cell_voltage"),
                    telemetria.get("max_pack_temperature"),
                    telemetria.get("source"),
                )
            return telemetria

        v_max = telemetria["highest_cell_voltage"]
        v_min = telemetria["lowest_cell_voltage"]
        t_max = telemetria["max_pack_temperature"]
        t_min = telemetria["min_pack_temperature"]

        logger.info(
            "Monitor de Planta (JK real, %s bancos) -> Celda Máx: %sV | Celda Mín: %sV | Temp Máx: %s°C",
            telemetria.get("jk_online_count", "?"),
            v_max,
            v_min,
            t_max,
        )

        # --- ALGORITMO DE CONTROL DE SEGURIDAD (experimental) ---
        # Escrituras a 2704/05/06 siguen pasando por _register_write_allowed.

        if t_max is not None and t_max >= cfg["t_critical_high"]:
            self.aplicar_contramedida_victron(
                2706, 4, "APAGADO DE EMERGENCIA POR SOBRETEMPERATURA", telemetry=telemetria
            )
            return telemetria

        if t_min is not None and t_min <= cfg["t_charge_low"]:
            self.aplicar_contramedida_victron(
                2704, 0, "CORRIENTE DE CARGA A 0A POR TEMPERATURA BAJO CERO", telemetry=telemetria
            )
            return telemetria

        if v_max is not None and v_max >= cfg["v_cell_critical_high"]:
            self.aplicar_contramedida_victron(
                2704, 0, "CORRIENTE DE CARGA A 0A POR VOLTAJE CRÍTICO DE CELDA", telemetry=telemetria
            )
            return telemetria

        if v_max is not None and v_max >= cfg["v_cell_warning_high"]:
            self.aplicar_contramedida_victron(
                2704, 10, "REDUCCIÓN DE CARGA PREVENTIVA (CELDA ALTA)", telemetry=telemetria
            )
            return telemetria

        if v_min is not None and v_min <= cfg["v_cell_critical_low"]:
            self.aplicar_contramedida_victron(
                2705, 0, "CORRIENTE DE DESCARGA A 0A POR SOBREDESCARGA DE CELDA", telemetry=telemetria
            )
            return telemetria

        logger.info("Infraestructura estable. No se requieren acciones de mitigación.")
        return telemetria


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Supervisor experimental Victron/JK (dry-run por defecto)"
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Una sola pasada de supervisión y salir",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Forzar dry-run aunque safety_write_enabled=true",
    )
    p.add_argument(
        "--config",
        type=str,
        default=None,
        help="Ruta a config.json",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger.info("=== Iniciando Supervisor Industrial de Baterías Victron-BMS ===")
    supervisor = VictronBmsSafetySupervisor(
        config_path=args.config,
        force_dry_run=True if args.dry_run else None,
    )

    try:
        if args.once:
            supervisor.supervisar_planta()
            return 0
        while True:
            supervisor.supervisar_planta()
            interval = float(supervisor.config.get("safety_loop_interval_s", 5))
            time.sleep(max(interval, 1.0))
    except KeyboardInterrupt:
        logger.info("Supervisor industrial detenido por el operador del sistema.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
