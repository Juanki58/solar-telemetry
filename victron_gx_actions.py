"""
Acciones opcionales Victron GX (Modbus TCP) — lectura primero, escritura dry-run.

Citas del mapa oficial com.victronenergy (dbus_modbustcp/attributes.csv):
- 806 /Relay/0/State (system) — 0=Open, 1=Closed, writable
- 807 /Relay/1/State (system)
- 2700 /Settings/CGwacs/AcPowerSetPoint — consigna de red (W, int16)
- 2701 MaxChargePercentage, 2702 MaxDischargePercentage
- 2900 BatteryLife/State, 2901 MinimumSocLimit (×0.1 %), 2902 Hub4Mode

Hub4Mode (2902): 1=ESS con compensación de fase, 2=sin compensación,
3=control externo / deshabilitado.
Ver también: https://www.victronenergy.com/live/ess:ess_mode_2_and_3

Seguridad
---------
- Por defecto solo lectura + dry-run de escrituras.
- Escritura real exige manual_write_enabled=true + confirmación en UI.
- Nunca usa el bucle automático de cortes BMS (victron_industrial_bms_safety).
- Registros 2704/2705/2706 (límites de descarga/carga DVCC) siguen bloqueados aquí.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pyModbusTCP.client import ModbusClient

logger = logging.getLogger("bintelligent.gx_actions")

# --- Registros documentados (unit típico: victron_unit_id / system = 100) ---
REG_RELAY_0 = 806
REG_RELAY_1 = 807
REG_AC_POWER_SETPOINT = 2700  # W, int16, scale 1
REG_MAX_CHARGE_PCT = 2701
REG_MAX_DISCHARGE_PCT = 2702
REG_BATTERY_LIFE_STATE = 2900
REG_MIN_SOC_LIMIT = 2901  # scale 10 → %
REG_HUB4_MODE = 2902

# Mismos regs que el supervisor de seguridad bloquea para cortes automáticos.
BLOCKED_AUTO_CUTOFF_REGS = frozenset({2704, 2705, 2706})

# Escrituras opcionales permitidas solo con mapa citado + confirmación UI.
ALLOWED_MANUAL_WRITE_REGS = frozenset(
    {
        REG_RELAY_0,
        REG_RELAY_1,
        REG_AC_POWER_SETPOINT,
        REG_HUB4_MODE,
    }
)

HUB4_MODE_LABELS: dict[int, str] = {
    1: "ESS con compensación de fase",
    2: "ESS sin compensación de fase",
    3: "Control externo / deshabilitado",
}

BATTERY_LIFE_LABELS: dict[int, str] = {
    0: "BatteryLife desactivado",
    1: "Reiniciando",
    2: "Autoconsumo",
    3: "Autoconsumo",
    4: "Autoconsumo",
    5: "Descarga deshabilitada",
    6: "Carga forzada",
    7: "Sustain",
    9: "Mantener baterías cargadas",
    10: "BatteryLife desactivado",
    11: "BatteryLife off (SoC bajo)",
}


@dataclass
class WritePreview:
    register: int
    value: int
    description: str
    unit_id: int
    dry_run: bool
    would_write: bool
    blocked_reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _to_signed_int16(raw: int) -> int:
    return raw - 65536 if raw > 32767 else raw


def _to_uint16(value: int) -> int:
    if value < 0:
        return value + 65536
    return int(value) & 0xFFFF


def manual_writes_enabled(cfg: dict) -> bool:
    """True solo si el operador habilitó escrituras manuales (no el loop de safety)."""
    return bool(cfg.get("manual_write_enabled", False))


def _client_for(cfg: dict, unit_id: int | None = None) -> ModbusClient:
    return ModbusClient(
        host=cfg.get("victron_host") or cfg.get("victron_ip"),
        port=int(cfg.get("modbus_port", 502)),
        unit_id=int(unit_id if unit_id is not None else cfg.get("victron_unit_id", 100)),
        auto_open=True,
        timeout=float(cfg.get("modbus_timeout_s", 3) or 3),
    )


def _read_one(client: ModbusClient, reg: int, *, signed: bool = False) -> int | None:
    regs = client.read_holding_registers(reg, 1)
    if not regs:
        return None
    return _to_signed_int16(regs[0]) if signed else int(regs[0])


def read_ess_insights(cfg: dict) -> dict[str, Any]:
    """
    Lectura de estado ESS / relé / consignas en el unit de sistema (config).
    No escribe nada.
    """
    unit_id = int(cfg.get("victron_unit_id", 100))
    host = cfg.get("victron_host") or cfg.get("victron_ip")
    client = _client_for(cfg, unit_id)
    result: dict[str, Any] = {
        "ok": False,
        "host": host,
        "unit_id": unit_id,
        "error": None,
        "registers": {},
        "summary": {},
    }

    try:
        if not client.open():
            raise ConnectionError(f"No se pudo abrir Modbus TCP {host}:{cfg.get('modbus_port', 502)}")

        hub4 = _read_one(client, REG_HUB4_MODE)
        setpoint = _read_one(client, REG_AC_POWER_SETPOINT, signed=True)
        life = _read_one(client, REG_BATTERY_LIFE_STATE)
        min_soc_raw = _read_one(client, REG_MIN_SOC_LIMIT)
        max_chg = _read_one(client, REG_MAX_CHARGE_PCT)
        max_dchg = _read_one(client, REG_MAX_DISCHARGE_PCT)
        relay0 = _read_one(client, REG_RELAY_0)
        relay1 = _read_one(client, REG_RELAY_1)

        result["registers"] = {
            "hub4_mode": hub4,
            "ac_power_setpoint_w": setpoint,
            "battery_life_state": life,
            "min_soc_limit_raw": min_soc_raw,
            "max_charge_pct": max_chg,
            "max_discharge_pct": max_dchg,
            "relay_0": relay0,
            "relay_1": relay1,
        }

        min_soc = round(min_soc_raw / 10.0, 1) if min_soc_raw is not None else None
        result["summary"] = {
            "hub4_mode": hub4,
            "hub4_mode_label": HUB4_MODE_LABELS.get(hub4 or -1, f"Desconocido ({hub4})"),
            "ac_power_setpoint_w": setpoint,
            "battery_life_state": life,
            "battery_life_label": BATTERY_LIFE_LABELS.get(life or -1, f"Estado {life}"),
            "min_soc_limit_pct": min_soc,
            "max_charge_pct": max_chg,
            "max_discharge_pct": max_dchg,
            "relay_0_closed": bool(relay0) if relay0 is not None else None,
            "relay_1_closed": bool(relay1) if relay1 is not None else None,
            "manual_write_enabled": manual_writes_enabled(cfg),
        }
        result["ok"] = True
        logger.info(
            "ESS insights OK — unit %s Hub4Mode=%s setpoint=%sW relay0=%s",
            unit_id,
            hub4,
            setpoint,
            relay0,
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        logger.error("ESS insights fallo: %s", result["error"])
    finally:
        client.close()

    return result


def build_write_preview(
    cfg: dict,
    register: int,
    value: int,
    description: str,
) -> WritePreview:
    """Construye preview de escritura; dry-run salvo manual_write_enabled."""
    unit_id = int(cfg.get("victron_unit_id", 100))
    write_on = manual_writes_enabled(cfg)
    blocked: str | None = None

    if int(register) in BLOCKED_AUTO_CUTOFF_REGS:
        blocked = (
            f"Registro {register} bloqueado: pertenece al mapa de cortes DVCC/ESS "
            "(2704/2705/2706). No se ofrece desde Acciones; el supervisor de seguridad "
            "tampoco lo escribe sin safety_write_registers_confirmed."
        )
    elif int(register) not in ALLOWED_MANUAL_WRITE_REGS:
        blocked = (
            f"Registro {register} no está en la lista de escrituras manuales auditadas "
            f"({sorted(ALLOWED_MANUAL_WRITE_REGS)})."
        )

    return WritePreview(
        register=int(register),
        value=int(value),
        description=description,
        unit_id=unit_id,
        dry_run=not write_on or blocked is not None,
        would_write=write_on and blocked is None,
        blocked_reason=blocked,
        details={
            "host": cfg.get("victron_host") or cfg.get("victron_ip"),
            "manual_write_enabled": write_on,
        },
    )


def execute_manual_write(
    cfg: dict,
    register: int,
    value: int,
    description: str,
    *,
    confirmed: bool,
) -> dict[str, Any]:
    """
    Ejecuta o simula una escritura Modbus puntual.

    Requiere confirmed=True. Sin manual_write_enabled solo dry-run (éxito de preview).
    """
    preview = build_write_preview(cfg, register, value, description)
    out: dict[str, Any] = {
        "ok": False,
        "dry_run": preview.dry_run,
        "written": False,
        "preview": {
            "register": preview.register,
            "value": preview.value,
            "description": preview.description,
            "unit_id": preview.unit_id,
            "blocked_reason": preview.blocked_reason,
        },
        "message": "",
        "error": None,
    }

    if not confirmed:
        out["message"] = "Confirmación requerida: marca la casilla antes de ejecutar."
        out["error"] = "not_confirmed"
        return out

    if preview.blocked_reason:
        out["message"] = preview.blocked_reason
        out["error"] = "blocked_register"
        logger.warning("Write bloqueado: %s", preview.blocked_reason)
        return out

    if preview.dry_run:
        msg = (
            f"[DRY-RUN] No se escribió. Pretendería unit={preview.unit_id} "
            f"reg={preview.register} value={preview.value} ({description}). "
            'Para escritura real: "manual_write_enabled": true en config.json + confirmación.'
        )
        out["ok"] = True
        out["message"] = msg
        logger.info(msg)
        return out

    client = _client_for(cfg, preview.unit_id)
    try:
        if not client.open():
            raise ConnectionError("Conexión Modbus TCP cerrada con el GX.")
        raw = _to_uint16(int(value))
        ok = client.write_single_register(preview.register, raw)
        if not ok:
            raise RuntimeError(
                f"write_single_register falló (unit {preview.unit_id} reg {preview.register})"
            )
        out["ok"] = True
        out["written"] = True
        out["dry_run"] = False
        out["message"] = (
            f"Escrito unit={preview.unit_id} reg={preview.register} value={value} ({description})"
        )
        logger.warning("MANUAL WRITE: %s", out["message"])
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["message"] = f"Fallo de escritura: {out['error']}"
        logger.error(out["message"])
    finally:
        client.close()

    return out


def action_set_grid_setpoint(cfg: dict, watts: int, *, confirmed: bool) -> dict[str, Any]:
    """Consigna de red ESS (reg 2700). Positivo=importar, negativo=exportar."""
    watts = int(max(-32768, min(32767, watts)))
    return execute_manual_write(
        cfg,
        REG_AC_POWER_SETPOINT,
        watts,
        f"Consigna de red ESS (AcPowerSetPoint) = {watts} W",
        confirmed=confirmed,
    )


def action_set_hub4_mode(cfg: dict, mode: int, *, confirmed: bool) -> dict[str, Any]:
    """Cambia Hub4Mode / modo ESS (reg 2902)."""
    mode = int(mode)
    if mode not in HUB4_MODE_LABELS:
        return {
            "ok": False,
            "dry_run": True,
            "written": False,
            "message": f"Modo ESS inválido: {mode}. Usa 1, 2 o 3.",
            "error": "invalid_mode",
            "preview": {"register": REG_HUB4_MODE, "value": mode},
        }
    label = HUB4_MODE_LABELS[mode]
    return execute_manual_write(
        cfg,
        REG_HUB4_MODE,
        mode,
        f"Modo ESS Hub4Mode = {mode} ({label})",
        confirmed=confirmed,
    )


def action_set_relay(cfg: dict, relay_index: int, closed: bool, *, confirmed: bool) -> dict[str, Any]:
    """Conmuta relé del GX (806 o 807)."""
    if relay_index not in (0, 1):
        return {
            "ok": False,
            "dry_run": True,
            "written": False,
            "message": "relay_index debe ser 0 o 1",
            "error": "invalid_relay",
            "preview": {},
        }
    reg = REG_RELAY_0 if relay_index == 0 else REG_RELAY_1
    value = 1 if closed else 0
    state = "cerrado" if closed else "abierto"
    return execute_manual_write(
        cfg,
        reg,
        value,
        f"Relé GX {relay_index} → {state} (reg {reg})",
        confirmed=confirmed,
    )
