"""
B-Intelligent — BMS Cloud Auditor (Web App)
Monitor visual en tiempo real con Streamlit.
"""

import logging
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from pyModbusTCP.client import ModbusClient

_INTEGRATIONS = Path(__file__).resolve().parent / "integrations"
if str(_INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(_INTEGRATIONS))

from whatsapp_alerts import send_whatsapp_alert

from config_loader import load_configuration as _load_shared_configuration
from jk_bms_client import fetch_all_batteries, merge_battery_telemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [MODBUS] - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
MODE_SIM = "Modo Laboratorio (Simulado)"
MODE_REAL = "Modo Planta Real (Victron Modbus)"

COLOR_BG = "#060d18"
COLOR_BG_GRADIENT = "linear-gradient(145deg, #060d18 0%, #0a1a32 45%, #0d2847 100%)"
COLOR_SURFACE = "#0f1e35"
COLOR_SURFACE_GRADIENT = "linear-gradient(160deg, rgba(15, 30, 53, 0.95) 0%, rgba(18, 40, 72, 0.88) 100%)"
COLOR_BORDER = "#2a5a9a"
COLOR_TEXT = "#f5f8ff"
COLOR_TEXT_MUTED = "#9eb8d9"
COLOR_ACCENT = "#00f5d4"
COLOR_ACCENT_2 = "#7b61ff"
COLOR_GREEN = "#00ff88"
COLOR_YELLOW = "#ffd93d"
COLOR_RED = "#ff4757"
COLOR_ORANGE = "#ff9f1c"
COLOR_GREEN_DARK = "linear-gradient(135deg, #0a3d28 0%, #0d5c3a 100%)"
COLOR_SOC_ON = "#ff9f1c"
COLOR_SOC_ON_GLOW = "#ffd93d"
COLOR_SOC_OFF = "#12243d"
COLOR_SOLAR = "#ffd93d"
COLOR_LOAD = "#4fc3f7"
COLOR_BATTERY = "#00e676"
COLOR_GRID = "#b388ff"
SOC_BAR_SEGMENTS = 20

METRIC_ACCENTS = {
    "cells": "#00f5d4",
    "temperature": "#ff6b6b",
    "consumption": "#4fc3f7",
    "solar": "#ffd93d",
    "battery": "#00e676",
    "grid": "#b388ff",
}

WEB_DEFAULTS = {
    "default_mode": "real",
    "sample_interval_s": 5,
    "soc_sim_min": 35,
    "soc_sim_max": 45,
    "cell_count": 16,
    "cell_spread_v": 0.04,
    "modbus_reg_system_voltage": 840,
    "modbus_reg_system_soc": 843,
    "modbus_reg_system_voltage_scale": 10,
    "modbus_reg_system_soc_scale": 1,
    "modbus_reg_system_soc_fallback": None,
    "modbus_reg_system_soc_fallback_scale": 1,
    "modbus_reg_ac_consumption_l1": 817,
    "modbus_reg_ac_consumption_l2": 818,
    "modbus_reg_ac_consumption_l3": 819,
    "modbus_reg_pv_power": 850,
    "modbus_reg_grid_power": 820,
    "modbus_reg_battery_power": 842,
    "battery_capacity_kwh": 10.0,
    "battery_capacity_kwh_per_unit": 10.0,
    "battery_bank_mode": "parallel",
    "soc_source": "victron",
    "soc_alert_warning": 20.0,
    "soc_alert_critical": 10.0,
    "whatsapp_alerts_enabled": False,
    "whatsapp_alert_cooldown_s": 3600,
    "whatsapp_recipient": "",
    "whatsapp_template_name": "alerta_bintelligent",
    "whatsapp_template_language": "es",
    "plant_name": "B-Intelligent Plant",
    "inverter_unit_id": 225,
    "battery_unit_id": None,
    "modbus_reg_battery_temperature": 282,
    "modbus_reg_battery_temperature_scale": 10,
    "batteries": [],
}


def load_configuration(config_path: Path = CONFIG_PATH) -> dict:
    """Carga config compartida + defaults del dashboard web."""
    return _load_shared_configuration(config_path, defaults=WEB_DEFAULTS)

def _to_signed_int16(value: int) -> int:
    return value - 65536 if value >= 32768 else value


def format_house_power(watts: float) -> tuple[str, str]:
    """Formatea potencia de consumo para la tarjeta principal."""
    watts = max(watts, 0.0)
    if watts >= 1000:
        return f"{watts / 1000:.2f} kW", f"{watts:.0f} W instantáneos"
    return f"{watts:.0f} W", "Consumo AC instantáneo de la vivienda"


def format_power_watts(watts: float) -> str:
    watts = abs(watts)
    if watts >= 1000:
        return f"{watts / 1000:.2f} kW"
    return f"{watts:.0f} W"


def format_grid_power(watts: float) -> tuple[str, str]:
    if watts > 50:
        return format_power_watts(watts), "Importando de la red eléctrica"
    if watts < -50:
        return format_power_watts(watts), "Exportando excedente a la red"
    return "0 W", "Red en equilibrio"


def format_battery_power(watts: float) -> tuple[str, str]:
    if watts > 50:
        return format_power_watts(watts), "Batería cargando"
    if watts < -50:
        return format_power_watts(watts), "Batería descargando"
    return "0 W", "Batería en reposo"


def estimate_autonomy_hours(soc_percent: float, capacity_kwh: float, consumption_w: float) -> float | None:
    """Estima autonomía: energía usable / consumo instantáneo."""
    if consumption_w <= 50 or capacity_kwh <= 0:
        return None
    available_wh = capacity_kwh * 1000.0 * (soc_percent / 100.0)
    return available_wh / consumption_w


def format_autonomy(hours: float | None) -> str:
    if hours is None:
        return "— (consumo muy bajo)"
    if hours >= 24:
        return f"{hours / 24:.1f} días"
    return f"{hours:.1f} h"


def analizar_salud_celdas(voltajes_celdas: list[float]) -> dict:
    n = len(voltajes_celdas)
    if n == 0:
        return {
            "drift_mv": 0,
            "desviacion_estandar_mv": 0,
            "estado": "Sin datos",
            "tipo_alerta": "info",
            "media_v": 0,
        }

    v_max = max(voltajes_celdas)
    v_min = min(voltajes_celdas)
    drift_mv = (v_max - v_min) * 1000

    media = sum(voltajes_celdas) / n
    varianza = sum((x - media) ** 2 for x in voltajes_celdas) / n
    desviacion_estandar_mv = math.sqrt(varianza) * 1000

    if desviacion_estandar_mv < 10:
        estado = "Excelente 🟢"
        tipo_alerta = "success"
    elif desviacion_estandar_mv < 25:
        estado = "Normal / Bueno 🟡"
        tipo_alerta = "info"
    elif desviacion_estandar_mv < 50:
        estado = "Desequilibrio detectado 🟠"
        tipo_alerta = "warning"
    else:
        estado = "CRÍTICO (Revisar celdas/busbars) 🔴"
        tipo_alerta = "error"

    return {
        "drift_mv": round(drift_mv, 1),
        "desviacion_estandar_mv": round(desviacion_estandar_mv, 1),
        "estado": estado,
        "tipo_alerta": tipo_alerta,
        "media_v": round(media, 3),
    }


def build_simulated_cell_voltages(cell_count: int, t: float | None = None) -> list[float]:
    t = t or time.time()
    base = 3.322 + 0.003 * math.sin(t / 30)
    return [
        round(base + 0.002 * math.sin(t / 7 + i * 0.9) + 0.001 * math.sin(i * 1.7), 3)
        for i in range(cell_count)
    ]


def build_estimated_cell_voltages(v_min: float, v_max: float, cell_count: int) -> list[float]:
    if cell_count <= 0:
        return []
    if cell_count == 1:
        return [round(v_min, 3)]
    step = (v_max - v_min) / (cell_count - 1)
    return [round(v_min + i * step, 3) for i in range(cell_count)]


def _cell_status_class(voltage: float, cfg: dict, is_max: bool, is_min: bool) -> str:
    if voltage >= cfg["v_cell_critical_high"] or voltage <= cfg["v_cell_critical_low"]:
        return "cell-critical"
    if voltage >= cfg["v_cell_warning_high"]:
        return "cell-warning"
    if is_max:
        return "cell-max"
    if is_min:
        return "cell-min"
    return "cell-normal"


def _cell_card_html(cell_index: int, voltage: float, is_max: bool, is_min: bool, cfg: dict) -> str:
    status = _cell_status_class(voltage, cfg, is_max, is_min)
    tag = "MAX" if is_max else ("MIN" if is_min else "")
    tag_html = f'<span class="cell-tag">{tag}</span>' if tag else ""
    return (
        f'<div class="cell-card {status}">'
        f'<div class="cell-id">C{cell_index:02d}{tag_html}</div>'
        f'<div class="cell-voltage">{voltage:.3f} V</div>'
        f"</div>"
    )


def render_battery_cells_panel(batteries: list[dict], cfg: dict):
    """Grid 4×4 de botones con el voltaje de cada celda JK BMS v19."""
    if not batteries:
        return

    if "selected_cell" not in st.session_state:
        st.session_state.selected_cell = None

    st.markdown("### 🔬 Celdas JK BMS v19 — por batería")
    st.caption("Pulsa «Ver detalles» en una celda para ampliar. ▲ máxima · ▼ mínima del banco.")

    for b_idx, battery in enumerate(batteries):
        voltajes = battery.get("cells") or battery.get("cell_voltages") or []
        bank_id = battery.get("id", f"bank_{b_idx}")
        bank_key = str(bank_id).replace(" ", "_").replace(".", "_")
        bank_name = battery.get("name", bank_id)
        online = battery.get("jk_online", False)
        source = battery.get("cell_voltage_source", "desconocido")
        status = "🟢 Online" if online and not battery.get("error") else "🔴 Offline / estimado"

        st.markdown(f"#### {status} · {bank_name}")
        if battery.get("soc") is not None:
            st.caption(f"SoC individual JK: {battery['soc']}% · {source}")
        else:
            st.caption(source)
        if battery.get("error"):
            st.warning(f"JK BMS: {battery['error']}")

        if not voltajes:
            st.info("Sin datos de celdas para este banco.")
            continue

        v_max = max(voltajes)
        v_min = min(voltajes)
        media = sum(voltajes) / len(voltajes)

        for row in range(4):
            cols = st.columns(4)
            for col in range(4):
                cell_idx = row * 4 + col
                if cell_idx >= len(voltajes):
                    continue
                voltage = voltajes[cell_idx]
                is_max = voltage == v_max
                is_min = voltage == v_min
                with cols[col]:
                    st.markdown(_cell_card_html(cell_idx + 1, voltage, is_max, is_min, cfg), unsafe_allow_html=True)
                    if st.button(
                        "Ver detalles",
                        key=f"jk_detail_{bank_key}_{cell_idx}",
                        use_container_width=True,
                    ):
                        st.session_state.selected_cell = {
                            "battery_id": bank_id,
                            "battery_name": bank_name,
                            "cell_index": cell_idx + 1,
                            "voltage": voltage,
                            "is_highest": is_max,
                            "is_lowest": is_min,
                            "delta_from_avg_mv": round((voltage - media) * 1000, 1),
                            "source": source,
                            "max_cell_index": battery.get("max_cell_index"),
                            "min_cell_index": battery.get("min_cell_index"),
                        }

        salud = analizar_salud_celdas(voltajes)
        st.markdown(
            f'<div class="cell-bank-summary">'
            f'Drift <strong>{salud["drift_mv"]} mV</strong> · '
            f'σ <strong>{salud["desviacion_estandar_mv"]} mV</strong> · '
            f'{salud["estado"]}'
            f"</div>",
            unsafe_allow_html=True,
        )

    selected = st.session_state.get("selected_cell")
    if selected:
        st.markdown("---")
        st.markdown(
            f'<div class="cell-detail-panel">'
            f'<div class="cell-detail-title">Celda seleccionada — {selected["battery_name"]}</div>'
            f'<div class="cell-detail-grid">'
            f'<div><span>Celda</span><strong>C{selected["cell_index"]:02d}</strong></div>'
            f'<div><span>Voltaje</span><strong>{selected["voltage"]:.3f} V</strong></div>'
            f'<div><span>Δ vs media</span><strong>{selected["delta_from_avg_mv"]:+.1f} mV</strong></div>'
            f'<div><span>Fuente</span><strong>JK v19</strong></div>'
            f"</div></div>",
            unsafe_allow_html=True,
        )

        hints = []
        if selected.get("is_highest"):
            hints.append("Celda con **voltaje máximo** del banco")
        if selected.get("is_lowest"):
            hints.append("Celda con **voltaje mínimo** del banco")
        if selected.get("max_cell_index") == selected["cell_index"]:
            hints.append("Confirmado por registro JK `MaxVolCellNbr`")
        if selected.get("min_cell_index") == selected["cell_index"]:
            hints.append("Confirmado por registro JK `MinVolCellNbr`")
        if selected["voltage"] >= cfg["v_cell_critical_high"]:
            hints.append("⚠ Por encima del umbral crítico de carga")
        elif selected["voltage"] >= cfg["v_cell_warning_high"]:
            hints.append("⚠ Zona de advertencia de carga")
        if selected["voltage"] <= cfg["v_cell_critical_low"]:
            hints.append("⚠ Por debajo del umbral crítico de descarga")

        if hints:
            st.info(" · ".join(hints))
        if st.button("Cerrar detalle", key="jk_cell_clear_selection"):
            st.session_state.selected_cell = None


def render_cell_health_sidebar(telemetry: dict, cfg: dict):
    batteries = telemetry.get("batteries") or []
    source = telemetry.get("cell_voltage_source", "desconocido")

    st.markdown("---")
    st.markdown("#### 🏥 Salud LiFePO4")

    if batteries:
        for bank in batteries:
            voltajes = bank.get("cells") or bank.get("cell_voltages") or []
            if not voltajes:
                continue
            salud = analizar_salud_celdas(voltajes)
            health_class = {
                "success": "health-success",
                "info": "health-info",
                "warning": "health-warning",
                "error": "health-error",
            }.get(salud["tipo_alerta"], "health-info")
            bank_name = bank.get("name", bank.get("id", "Banco"))
            online = "🟢" if bank.get("jk_online") and not bank.get("error") else "🔴"
            st.caption(f"{online} {bank_name} · {len(voltajes)} celdas · media {salud['media_v']:.3f} V")
            st.markdown(
                f'<div class="health-badge {health_class}">{salud["estado"]}</div>',
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            c1.metric("σ", f"{salud['desviacion_estandar_mv']} mV")
            c2.metric("Drift", f"{salud['drift_mv']} mV")
        st.caption(f"Fuente agregada: {source}")
    else:
        voltajes = telemetry.get("cell_voltages") or []
        salud = analizar_salud_celdas(voltajes)
        health_class = {
            "success": "health-success",
            "info": "health-info",
            "warning": "health-warning",
            "error": "health-error",
        }.get(salud["tipo_alerta"], "health-info")
        st.caption(f"Fuente: {source} · {len(voltajes)} celdas · media {salud['media_v']:.3f} V")
        st.markdown(
            f'<div class="health-badge {health_class}">Estado: {salud["estado"]}</div>',
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                label="Desviación Est.",
                value=f"{salud['desviacion_estandar_mv']} mV",
                help="Dispersión media entre celdas. Lo ideal es mantenerla por debajo de 15 mV en operación.",
            )
        with col2:
            st.metric(
                label="Dispersión (Drift)",
                value=f"{salud['drift_mv']} mV",
                help="Diferencia entre la celda con voltaje más alto y la más baja (Vmax − Vmin).",
            )

    with st.expander("ℹ️ ¿Por qué importa la Desviación Estándar?"):
        st.write(
            "A diferencia del drift clásico, la desviación estándar evalúa el comportamiento "
            "del bloque completo de celdas. Si sube de forma persistente al mismo SoC, avisa de "
            "envejecimiento prematuro o resistencia anómala en bornes (busbars) antes de que "
            "salte la protección del JK BMS."
        )


def read_modbus_register_w(client: ModbusClient, reg: int, signed: bool = False, label: str = "") -> float:
    try:
        regs = client.read_holding_registers(reg, 1)
        if not regs:
            logger.warning("Reg %s (%s): lectura vacía", reg, label)
            return 0.0
        value = _to_signed_int16(regs[0]) if signed else regs[0]
        logger.info("Potencia %s — reg %s: %s W", label, reg, value)
        return float(value)
    except Exception as exc:
        logger.error("ERROR reg %s (%s): %s: %s", reg, label, type(exc).__name__, exc)
        return 0.0


def process_whatsapp_alerts(telemetry: dict, cfg: dict, plant_status: str):
    if not cfg.get("whatsapp_alerts_enabled"):
        return

    soc = telemetry["soc"]
    plant = cfg.get("plant_name", "Planta")
    now = time.time()
    cooldown = cfg.get("whatsapp_alert_cooldown_s", 3600)
    recipient = cfg.get("whatsapp_recipient") or None
    template_name = cfg.get("whatsapp_template_name")
    template_language = cfg.get("whatsapp_template_language")

    alerts = []
    if soc <= cfg.get("soc_alert_critical", 10):
        alerts.append(("critical", f"SoC crítico: {soc:.1f}%"))
    elif soc <= cfg.get("soc_alert_warning", 20):
        alerts.append(("warning", f"SoC bajo: {soc:.1f}%"))
    if plant_status == "CRITICAL":
        alerts.append(("critical_status", "Estado de planta: CRÍTICO"))

    if "whatsapp_cooldown" not in st.session_state:
        st.session_state.whatsapp_cooldown = {}

    for key, message_text in alerts:
        last = st.session_state.whatsapp_cooldown.get(key, 0)
        if now - last >= cooldown:
            ok, detail = send_whatsapp_alert(
                message_text,
                plant_name=plant,
                recipient=recipient,
                template_name=template_name,
                template_language=template_language,
            )
            if ok:
                st.session_state.whatsapp_cooldown[key] = now
                logger.info("Alerta WhatsApp enviada: %s", key)
            else:
                logger.warning("WhatsApp no enviado (%s): %s", key, detail)


def read_ac_consumption_w(client: ModbusClient, cfg: dict) -> float:
    """Suma consumo AC L1+L2+L3 (registros 817-819, escala 1 W)."""
    total_w = 0.0
    phases = [
        ("L1", cfg["modbus_reg_ac_consumption_l1"]),
        ("L2", cfg.get("modbus_reg_ac_consumption_l2")),
        ("L3", cfg.get("modbus_reg_ac_consumption_l3")),
    ]
    for phase_name, reg in phases:
        if reg is None:
            continue
        try:
            regs = client.read_holding_registers(reg, 1)
            if not regs:
                logger.warning("Consumo AC %s — reg %s: lectura vacía", phase_name, reg)
                continue
            watts = _to_signed_int16(regs[0])
            if watts < 0:
                watts = 0
            total_w += watts
            logger.info("Consumo AC %s — reg %s: %s W", phase_name, reg, watts)
        except Exception as exc:
            logger.error("ERROR consumo AC %s reg %s: %s: %s", phase_name, reg, type(exc).__name__, exc)
    return total_w


def read_simulated_telemetry(cfg: dict) -> dict:
    phase = time.time() / 20
    soc_min = cfg["soc_sim_min"]
    soc_max = cfg["soc_sim_max"]
    soc = soc_min + (soc_max - soc_min) * (0.5 + 0.5 * math.sin(phase))

    house_w = 780 + 120 * math.sin(time.time() / 15)
    pv_w = max(0, 1200 + 400 * math.sin(time.time() / 25))
    battery_w = -350 + 200 * math.sin(time.time() / 18)
    grid_w = house_w - pv_w - battery_w
    autonomy = estimate_autonomy_hours(soc, cfg.get("battery_capacity_kwh", 10.0), house_w)
    cell_voltages = build_simulated_cell_voltages(cfg["cell_count"])

    return {
        "highest_cell_voltage": max(cell_voltages),
        "lowest_cell_voltage": min(cell_voltages),
        "max_pack_temperature": 28.5,
        "min_pack_temperature": 27.0,
        "soc": round(soc, 1),
        "pack_voltage": round(sum(cell_voltages), 2),
        "house_consumption_w": round(house_w, 0),
        "pv_power_w": round(pv_w, 0),
        "battery_power_w": round(battery_w, 0),
        "grid_power_w": round(grid_w, 0),
        "autonomy_hours": autonomy,
        "cell_voltages": cell_voltages,
        "cell_voltage_source": "Simulación laboratorio (JK)",
        "source": "simulated",
        "error": None,
    }


def read_victron_modbus_telemetry(cfg: dict) -> dict:
    """
    Lee telemetría Victron vía Modbus TCP (com.victronenergy.system, unit ID 100).
    SoC: registro 820, uint16, factor de escala 0.1 (raw 460 -> 46.0 %).
    Voltaje pack: registro 840, escala 0.1 V.
    """
    host = cfg["victron_ip"]
    port = cfg["modbus_port"]
    unit_id = cfg["victron_unit_id"]
    client = ModbusClient(host=host, port=port, unit_id=unit_id, auto_open=True, timeout=5)

    try:
        if not client.open():
            raise ConnectionError(f"No se pudo abrir conexión Modbus TCP con {host}:{port} (unit {unit_id})")

        # --- SoC: registro 843 en Cerbo GX (0-100 directo). 820 comparte mapa con grid power. ---
        raw_soc = None
        soc = None
        try:
            soc_regs = client.read_holding_registers(cfg["modbus_reg_system_soc"], 1)
            if not soc_regs:
                raise ConnectionError(
                    f"Lectura SoC vacía en registro {cfg['modbus_reg_system_soc']} "
                    f"(unit {unit_id}, host {host})"
                )
            raw_soc = soc_regs[0]
            soc = raw_soc / cfg["modbus_reg_system_soc_scale"]
            logger.info(
                "SoC reg %s — raw=%s, escala=%s, calculado=%.1f%%",
                cfg["modbus_reg_system_soc"],
                raw_soc,
                cfg["modbus_reg_system_soc_scale"],
                soc,
            )
        except Exception as exc:
            logger.error(
                "ERROR lectura SoC reg %s — unit %s, host %s: %s: %s",
                cfg["modbus_reg_system_soc"],
                unit_id,
                host,
                type(exc).__name__,
                exc,
            )
            soc = None

        # Fallback opcional solo si el registro primario falla o está fuera de rango.
        fallback_reg = cfg.get("modbus_reg_system_soc_fallback")
        if fallback_reg is not None:
            try:
                fb_regs = client.read_holding_registers(fallback_reg, 1)
                if fb_regs:
                    raw_fb = fb_regs[0]
                    soc_fb = raw_fb / cfg.get("modbus_reg_system_soc_fallback_scale", 1)
                    logger.info(
                        "SoC fallback reg %s — raw=%s, calculado=%.1f%%",
                        fallback_reg,
                        raw_fb,
                        soc_fb,
                    )
                    if soc is None or not (0 <= soc <= 100):
                        raw_soc, soc = raw_fb, soc_fb
                        logger.warning("Usando SoC fallback reg %s (primario inválido)", fallback_reg)
            except Exception as exc:
                logger.error(
                    "ERROR lectura SoC fallback reg %s: %s: %s",
                    fallback_reg,
                    type(exc).__name__,
                    exc,
                )

        if soc is None:
            raise ConnectionError("No se pudo leer SoC ni desde registro primario ni fallback")

        # --- Voltaje de batería: registro 840 ---
        try:
            voltage_regs = client.read_holding_registers(cfg["modbus_reg_system_voltage"], 1)
            if not voltage_regs:
                raise ConnectionError(
                    f"Lectura voltaje vacía en registro {cfg['modbus_reg_system_voltage']}"
                )
            raw_voltage = voltage_regs[0]
            pack_voltage = raw_voltage / cfg["modbus_reg_system_voltage_scale"]
            logger.info(
                "Voltaje pack OK — reg %s, raw=%s, pack=%.2f V",
                cfg["modbus_reg_system_voltage"],
                raw_voltage,
                pack_voltage,
            )
        except Exception as exc:
            logger.error(
                "ERROR lectura voltaje — reg %s: %s: %s",
                cfg["modbus_reg_system_voltage"],
                type(exc).__name__,
                exc,
            )
            raise

        if not (0 <= soc <= 100):
            raise ValueError(
                f"SoC fuera de rango tras escala 0.1: raw={raw_soc}, calculado={soc:.1f}% "
                f"(registro {cfg['modbus_reg_system_soc']})"
            )

        temperature = None
        battery_unit_id = cfg.get("battery_unit_id")
        if battery_unit_id:
            try:
                client.unit_id = battery_unit_id
                temp_regs = client.read_holding_registers(cfg["modbus_reg_battery_temperature"], 1)
                if temp_regs:
                    temperature = _to_signed_int16(temp_regs[0]) / cfg["modbus_reg_battery_temperature_scale"]
                    logger.info("Temperatura OK — unit %s, temp=%.1f C", battery_unit_id, temperature)
            except Exception as exc:
                logger.error(
                    "ERROR lectura temperatura — unit %s, reg %s: %s: %s",
                    battery_unit_id,
                    cfg["modbus_reg_battery_temperature"],
                    type(exc).__name__,
                    exc,
                )

        if temperature is None:
            temperature = 28.0

        try:
            house_consumption_w = read_ac_consumption_w(client, cfg)
        except Exception as exc:
            logger.error("ERROR lectura consumo casa: %s: %s", type(exc).__name__, exc)
            house_consumption_w = 0.0

        pv_power_w = read_modbus_register_w(client, cfg["modbus_reg_pv_power"], signed=False, label="PV")
        battery_power_w = read_modbus_register_w(
            client, cfg["modbus_reg_battery_power"], signed=True, label="Batería"
        )
        grid_power_w = read_modbus_register_w(
            client, cfg["modbus_reg_grid_power"], signed=True, label="Red"
        )
        autonomy_hours = estimate_autonomy_hours(
            soc, cfg.get("battery_capacity_kwh", 10.0), house_consumption_w
        )

        cell_count = cfg["cell_count"]
        spread = cfg["cell_spread_v"]
        v_avg = pack_voltage / cell_count
        v_max = round(v_avg + spread / 2, 3)
        v_min = round(v_avg - spread / 2, 3)
        cell_voltages = build_estimated_cell_voltages(v_min, v_max, cell_count)

        return {
            "highest_cell_voltage": max(cell_voltages),
            "lowest_cell_voltage": min(cell_voltages),
            "max_pack_temperature": round(temperature, 1),
            "min_pack_temperature": round(temperature - 1.0, 1),
            "soc": round(soc, 1),
            "pack_voltage": round(pack_voltage, 2),
            "house_consumption_w": round(house_consumption_w, 0),
            "pv_power_w": round(pv_power_w, 0),
            "battery_power_w": round(battery_power_w, 0),
            "grid_power_w": round(grid_power_w, 0),
            "autonomy_hours": autonomy_hours,
            "cell_voltages": cell_voltages,
            "cell_voltage_source": "Estimado desde pack Victron",
            "raw_soc": raw_soc,
            "source": "modbus",
            "error": None,
        }
    except Exception as exc:
        logger.error("FALLO Modbus TCP global: %s: %s", type(exc).__name__, exc)
        raise
    finally:
        client.close()


def fetch_telemetry(mode: str, cfg: dict) -> dict:
    simulated = mode != MODE_REAL
    if mode == MODE_REAL:
        try:
            system = read_victron_modbus_telemetry(cfg)
        except Exception as exc:
            logger.error("Modo Real con fallback simulado: %s: %s", type(exc).__name__, exc)
            system = read_simulated_telemetry(cfg)
            system["source"] = "modbus_error"
            system["error"] = f"{type(exc).__name__}: {exc}"
    else:
        system = read_simulated_telemetry(cfg)

    batteries = fetch_all_batteries(cfg, simulated=simulated, sim_t=time.time())
    merged = merge_battery_telemetry(system, batteries, cfg)

    # Seguro extra: en paralelo el SoC del sistema es solo el del Cerbo GX.
    if cfg.get("battery_bank_mode", "parallel") == "parallel" and system.get("soc") is not None:
        merged["soc"] = round(min(max(float(system["soc"]), 0.0), 100.0), 1)
        merged["soc_source_label"] = "Victron Cerbo GX (sistema completo)"

    merged["autonomy_hours"] = estimate_autonomy_hours(
        merged.get("soc", 0),
        cfg.get("battery_capacity_kwh", 10.0),
        merged.get("house_consumption_w", 0),
    )
    return merged


def evaluate_plant_status(telemetry: dict, cfg: dict) -> tuple[str, str, str]:
    v_max = telemetry["highest_cell_voltage"]
    v_min = telemetry["lowest_cell_voltage"]
    t_max = telemetry["max_pack_temperature"]
    t_min = telemetry["min_pack_temperature"]

    if t_max >= cfg["t_critical_high"]:
        return "CRITICAL", "APAGADO DE EMERGENCIA — SOBRETEMPERATURA", COLOR_RED
    if t_min <= cfg["t_charge_low"]:
        return "CRITICAL", "CARGA BLOQUEADA — TEMPERATURA BAJO CERO", COLOR_RED
    if v_max >= cfg["v_cell_critical_high"]:
        return "CRITICAL", "CARGA A 0A — VOLTAJE CRÍTICO DE CELDA", COLOR_RED
    if v_min <= cfg["v_cell_critical_low"]:
        return "CRITICAL", "DESCARGA A 0A — SOBREDESCARGA DE CELDA", COLOR_RED
    if v_max >= cfg["v_cell_warning_high"]:
        return "WARNING", "REDUCCIÓN DE CARGA PREVENTIVA — CELDA ALTA", COLOR_YELLOW
    return "STABLE", "SISTEMA ESTABLE", COLOR_GREEN


def build_soc_segment_bar(soc: float, total_segments: int = SOC_BAR_SEGMENTS) -> str:
    """Genera barritas encendidas/apagadas de 0 a 100 %."""
    lit = int(round(min(max(soc, 0.0), 100.0) / 100.0 * total_segments))
    parts = []
    for index in range(total_segments):
        state = "on" if index < lit else "off"
        parts.append(f'<div class="soc-seg soc-seg-{state}"></div>')
    return f'<div class="soc-segments">{"".join(parts)}</div>'


def soc_glow_color(soc: float) -> str:
    if soc <= 15:
        return COLOR_RED
    if soc <= 35:
        return COLOR_ORANGE
    if soc <= 60:
        return COLOR_YELLOW
    return COLOR_GREEN


def inject_corporate_theme():
    st.markdown(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

            .stApp {{
                background: {COLOR_BG_GRADIENT};
                color: {COLOR_TEXT};
                font-family: 'Inter', Helvetica, Arial, sans-serif;
            }}
            [data-testid="stHeader"], [data-testid="stToolbar"] {{
                background: rgba(6, 13, 24, 0.92);
            }}
            [data-testid="stSidebar"] {{
                background: linear-gradient(180deg, #0c1830 0%, #0a1428 100%);
                border-right: 1px solid rgba(0, 245, 212, 0.15);
            }}
            [data-testid="stSidebar"] * {{ color: {COLOR_TEXT} !important; }}
            [data-testid="stSidebar"] .stMetric {{
                background: rgba(0, 245, 212, 0.06);
                border: 1px solid rgba(0, 245, 212, 0.2);
                border-radius: 10px;
                padding: 0.5rem;
            }}
            .block-container {{ padding-top: 1.2rem; max-width: 1100px; }}

            .cell-bank-summary {{
                color: {COLOR_TEXT_MUTED};
                font-size: 0.88rem;
                margin: 0.35rem 0 1.2rem 0;
                padding: 0.55rem 0.75rem;
                border-radius: 10px;
                background: rgba(0, 245, 212, 0.05);
                border: 1px solid rgba(0, 245, 212, 0.12);
            }}

            .cell-card {{
                border-radius: 12px;
                padding: 0.7rem 0.45rem 0.55rem;
                margin-bottom: 0.4rem;
                text-align: center;
                border: 2px solid transparent;
            }}
            .cell-card .cell-id {{
                font-size: 0.72rem;
                color: #c8daf0;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }}
            .cell-card .cell-voltage {{
                font-size: 1.12rem;
                font-weight: 800;
                color: #ffffff;
                margin-top: 0.2rem;
            }}
            .cell-card .cell-tag {{
                display: inline-block;
                margin-left: 0.35rem;
                padding: 0.05rem 0.35rem;
                border-radius: 999px;
                font-size: 0.62rem;
                font-weight: 800;
                background: rgba(255, 255, 255, 0.18);
            }}
            .cell-normal {{
                background: linear-gradient(160deg, #0f5c52 0%, #0a3d38 100%);
                border-color: #00c9a7;
                box-shadow: 0 4px 14px rgba(0, 201, 167, 0.22);
            }}
            .cell-max {{
                background: linear-gradient(160deg, #1565a8 0%, #0c3f6e 100%);
                border-color: #00f5d4;
                box-shadow: 0 0 16px rgba(0, 245, 212, 0.38);
            }}
            .cell-min {{
                background: linear-gradient(160deg, #8a5a12 0%, #5c3a08 100%);
                border-color: #ffd93d;
                box-shadow: 0 0 14px rgba(255, 217, 61, 0.28);
            }}
            .cell-warning {{
                background: linear-gradient(160deg, #9a6d08 0%, #6b4a04 100%);
                border-color: #ffc107;
                box-shadow: 0 0 14px rgba(255, 193, 7, 0.3);
            }}
            .cell-critical {{
                background: linear-gradient(160deg, #a81830 0%, #6e0d1f 100%);
                border-color: #ff4757;
                box-shadow: 0 0 16px rgba(255, 71, 87, 0.35);
            }}

            .cell-detail-panel {{
                background: linear-gradient(160deg, #123456 0%, #0c2440 100%);
                border: 2px solid {COLOR_ACCENT};
                border-radius: 14px;
                padding: 1rem 1.2rem;
                margin: 0.5rem 0 1rem 0;
                box-shadow: 0 0 20px rgba(0, 245, 212, 0.18);
            }}
            .cell-detail-title {{
                color: {COLOR_ACCENT};
                font-size: 1rem;
                font-weight: 800;
                margin-bottom: 0.85rem;
            }}
            .cell-detail-grid {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 0.75rem;
            }}
            .cell-detail-grid div {{
                background: rgba(0, 0, 0, 0.22);
                border-radius: 10px;
                padding: 0.65rem 0.5rem;
                text-align: center;
            }}
            .cell-detail-grid span {{
                display: block;
                color: {COLOR_TEXT_MUTED};
                font-size: 0.72rem;
                margin-bottom: 0.25rem;
            }}
            .cell-detail-grid strong {{
                color: #ffffff;
                font-size: 1.05rem;
            }}

            div[data-testid="column"] .stButton > button {{
                background: linear-gradient(180deg, #00b89a 0%, #008f78 100%) !important;
                color: #ffffff !important;
                border: 2px solid #00f5d4 !important;
                border-radius: 10px;
                font-size: 0.8rem;
                font-weight: 800;
                padding: 0.45rem 0.35rem;
                min-height: 2.4rem;
                transition: all 0.2s ease;
                box-shadow: 0 4px 12px rgba(0, 245, 212, 0.25);
            }}
            div[data-testid="column"] .stButton > button:hover {{
                background: linear-gradient(180deg, #00f5d4 0%, #00b89a 100%) !important;
                border-color: #ffffff !important;
                box-shadow: 0 0 18px rgba(0, 245, 212, 0.45);
                color: #042018 !important;
            }}

            .brand-tag {{
                display: inline-block;
                color: {COLOR_ACCENT};
                font-size: 0.8rem;
                font-weight: 800;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                padding: 0.25rem 0.65rem;
                border-radius: 999px;
                border: 1px solid rgba(0, 245, 212, 0.45);
                background: rgba(0, 245, 212, 0.08);
                box-shadow: 0 0 18px rgba(0, 245, 212, 0.15);
            }}
            .brand-title {{
                background: linear-gradient(90deg, {COLOR_TEXT} 0%, {COLOR_ACCENT} 55%, {COLOR_ACCENT_2} 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 2.45rem;
                font-weight: 800;
                margin: 0.6rem 0 0.35rem 0;
                letter-spacing: -0.02em;
            }}
            .brand-subtitle {{ color: {COLOR_TEXT_MUTED}; font-size: 0.98rem; margin-bottom: 1.1rem; }}

            .soc-card {{
                background: {COLOR_SURFACE_GRADIENT};
                border: 1px solid rgba(0, 245, 212, 0.25);
                border-radius: 18px;
                padding: 1.3rem 1.6rem;
                margin-bottom: 1rem;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255,255,255,0.06);
            }}
            .soc-label {{
                color: {COLOR_ACCENT};
                font-size: 0.78rem;
                font-weight: 800;
                letter-spacing: 0.1em;
                text-transform: uppercase;
            }}
            .soc-value {{
                font-size: 2.65rem;
                font-weight: 800;
                margin: 0.35rem 0 0.65rem 0;
                text-shadow: 0 0 24px currentColor;
            }}
            .soc-segments {{
                display: flex;
                gap: 4px;
                width: 100%;
                height: 38px;
                margin: 0.65rem 0 0.35rem 0;
            }}
            .soc-seg {{
                flex: 1;
                border-radius: 6px;
                min-height: 38px;
                transition: all 0.35s ease;
            }}
            .soc-seg-on {{
                background: linear-gradient(180deg, {COLOR_SOC_ON_GLOW} 0%, {COLOR_SOC_ON} 100%);
                box-shadow: 0 0 10px rgba(255, 159, 28, 0.55), 0 2px 4px rgba(0,0,0,0.3);
            }}
            .soc-seg-off {{
                background: {COLOR_SOC_OFF};
                border: 1px solid rgba(42, 90, 154, 0.5);
            }}
            .soc-scale {{
                display: flex;
                justify-content: space-between;
                color: {COLOR_TEXT_MUTED};
                font-size: 0.75rem;
            }}
            .soc-source {{
                color: {COLOR_TEXT_MUTED};
                font-size: 0.78rem;
                margin-top: 0.45rem;
            }}
            .autonomy-line {{
                color: {COLOR_ACCENT};
                font-size: 1.05rem;
                font-weight: 700;
                margin-top: 0.85rem;
                padding-top: 0.65rem;
                border-top: 1px dashed rgba(0, 245, 212, 0.25);
            }}

            .flow-strip {{
                display: flex;
                justify-content: space-between;
                gap: 0.65rem;
                margin-bottom: 1rem;
            }}
            .flow-item {{
                flex: 1;
                text-align: center;
                border-radius: 14px;
                padding: 0.85rem 0.6rem;
                font-size: 0.82rem;
                color: {COLOR_TEXT_MUTED};
                border: 1px solid transparent;
                box-shadow: 0 6px 20px rgba(0,0,0,0.25);
            }}
            .flow-item strong {{
                display: block;
                font-size: 1.15rem;
                font-weight: 800;
                margin-top: 0.25rem;
                color: {COLOR_TEXT};
            }}
            .flow-solar {{
                background: linear-gradient(160deg, rgba(255, 217, 61, 0.18) 0%, rgba(255, 159, 28, 0.08) 100%);
                border-color: rgba(255, 217, 61, 0.35);
            }}
            .flow-load {{
                background: linear-gradient(160deg, rgba(79, 195, 247, 0.18) 0%, rgba(41, 121, 255, 0.08) 100%);
                border-color: rgba(79, 195, 247, 0.35);
            }}
            .flow-battery {{
                background: linear-gradient(160deg, rgba(0, 230, 118, 0.18) 0%, rgba(0, 200, 83, 0.08) 100%);
                border-color: rgba(0, 230, 118, 0.35);
            }}
            .flow-grid {{
                background: linear-gradient(160deg, rgba(179, 136, 255, 0.18) 0%, rgba(123, 97, 255, 0.08) 100%);
                border-color: rgba(179, 136, 255, 0.35);
            }}

            .metric-card {{
                background: {COLOR_SURFACE_GRADIENT};
                border: 1px solid rgba(42, 90, 154, 0.45);
                border-radius: 16px;
                padding: 1.35rem 1.5rem;
                min-height: 168px;
                box-shadow: 0 8px 28px rgba(0, 0, 0, 0.28);
                border-top: 3px solid var(--accent, {COLOR_ACCENT});
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }}
            .metric-card:hover {{
                transform: translateY(-2px);
                box-shadow: 0 12px 32px rgba(0, 0, 0, 0.38);
            }}
            .metric-label {{
                color: var(--accent, {COLOR_ACCENT});
                font-size: 0.72rem;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                margin-bottom: 0.75rem;
            }}
            .metric-value {{
                color: {COLOR_TEXT};
                font-size: 2.55rem;
                font-weight: 800;
                line-height: 1;
                margin-bottom: 0.55rem;
                text-shadow: 0 0 20px rgba(255,255,255,0.08);
            }}
            .metric-detail {{ color: {COLOR_TEXT_MUTED}; font-size: 0.88rem; line-height: 1.35; }}

            .status-panel {{
                border-radius: 18px;
                padding: 2rem 1.5rem;
                text-align: center;
                margin-top: 0.6rem;
                box-shadow: 0 10px 40px rgba(0,0,0,0.35);
            }}
            .status-stable {{
                background: linear-gradient(135deg, #0a3d28 0%, #0f5a3a 50%, #0a3d28 100%);
                border: 2px solid {COLOR_GREEN};
                box-shadow: 0 0 30px rgba(0, 255, 136, 0.25);
            }}
            .status-warning {{
                background: linear-gradient(135deg, #4a3a00 0%, #6b5200 50%, #4a3a00 100%);
                border: 2px solid {COLOR_YELLOW};
                box-shadow: 0 0 30px rgba(255, 217, 61, 0.25);
            }}
            .status-critical {{
                background: linear-gradient(135deg, #4a0f14 0%, #7a1820 50%, #4a0f14 100%);
                border: 2px solid {COLOR_RED};
                box-shadow: 0 0 30px rgba(255, 71, 87, 0.3);
                animation: pulse-critical 2s ease-in-out infinite;
            }}
            @keyframes pulse-critical {{
                0%, 100% {{ box-shadow: 0 0 20px rgba(255, 71, 87, 0.25); }}
                50% {{ box-shadow: 0 0 40px rgba(255, 71, 87, 0.45); }}
            }}
            .status-title {{ font-size: 2rem; font-weight: 800; margin: 0; color: {COLOR_TEXT}; }}
            .status-subtitle {{ font-size: 0.95rem; margin-top: 0.55rem; opacity: 0.92; color: {COLOR_TEXT}; }}

            .health-badge {{
                border-radius: 12px;
                padding: 0.75rem 1rem;
                font-weight: 700;
                margin-bottom: 0.75rem;
                border: 1px solid transparent;
            }}
            .health-success {{
                background: linear-gradient(135deg, rgba(0,255,136,0.15), rgba(0,200,83,0.08));
                border-color: rgba(0,255,136,0.4);
                color: #b8ffda;
            }}
            .health-info {{
                background: linear-gradient(135deg, rgba(255,217,61,0.15), rgba(255,159,28,0.08));
                border-color: rgba(255,217,61,0.4);
                color: #ffeaa7;
            }}
            .health-warning {{
                background: linear-gradient(135deg, rgba(255,159,28,0.18), rgba(255,107,0,0.08));
                border-color: rgba(255,159,28,0.45);
                color: #ffd8a8;
            }}
            .health-error {{
                background: linear-gradient(135deg, rgba(255,71,87,0.2), rgba(200,30,50,0.1));
                border-color: rgba(255,71,87,0.5);
                color: #ffb3bc;
            }}

            .footer-bar {{
                background: rgba(15, 30, 53, 0.85);
                border: 1px solid rgba(0, 245, 212, 0.15);
                border-radius: 12px;
                padding: 0.8rem 1rem;
                color: {COLOR_TEXT_MUTED};
                font-size: 0.82rem;
                margin-top: 1rem;
            }}
            .alert-bar {{
                background: linear-gradient(90deg, rgba(255,71,87,0.2), rgba(255,159,28,0.12));
                border: 1px solid {COLOR_RED};
                border-radius: 12px;
                padding: 0.7rem 1rem;
                color: {COLOR_TEXT};
                font-size: 0.88rem;
                margin-bottom: 0.9rem;
                box-shadow: 0 0 20px rgba(255, 71, 87, 0.15);
            }}
            #MainMenu, footer, header {{ visibility: hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_soc_card(soc: float, autonomy_hours: float | None, capacity_kwh: float, soc_source: str = ""):
    segment_bar = build_soc_segment_bar(soc)
    autonomy_text = format_autonomy(autonomy_hours)
    soc_color = soc_glow_color(soc)
    source_line = f'<div class="soc-source">Fuente SoC: {soc_source}</div>' if soc_source else ""
    st.markdown(
        f"""
        <div class="soc-card">
            <div class="soc-label">Estado de Carga (banco completo)</div>
            <div class="soc-value" style="color:{soc_color};">⚡ SoC: {soc:.1f}%</div>
            {segment_bar}
            <div class="soc-scale"><span>0%</span><span>100%</span></div>
            {source_line}
            <div class="autonomy-line">⏱ Autonomía estimada: {autonomy_text} · Banco {capacity_kwh:.1f} kWh</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_energy_flow_strip(telemetry: dict):
    pv = telemetry.get("pv_power_w", 0)
    load = telemetry.get("house_consumption_w", 0)
    bat = telemetry.get("battery_power_w", 0)
    grid = telemetry.get("grid_power_w", 0)
    st.markdown(
        f"""
        <div class="flow-strip">
            <div class="flow-item flow-solar">☀️ Solar<strong style="color:{COLOR_SOLAR};">{format_power_watts(pv)}</strong></div>
            <div class="flow-item flow-load">🏠 Consumo<strong style="color:{COLOR_LOAD};">{format_power_watts(load)}</strong></div>
            <div class="flow-item flow-battery">🔋 Batería<strong style="color:{COLOR_BATTERY};">{format_power_watts(bat)}</strong></div>
            <div class="flow-item flow-grid">🔌 Red<strong style="color:{COLOR_GRID};">{format_power_watts(grid)}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: str, detail: str, accent: str = COLOR_ACCENT):
    st.markdown(
        f"""
        <div class="metric-card" style="--accent: {accent};">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-detail">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_panel(level: str, message: str):
    if level == "STABLE":
        css_class, subtitle = "status-stable", "Sin alertas activas en la planta"
    elif level == "WARNING":
        css_class, subtitle = "status-warning", "Acción preventiva recomendada"
    else:
        css_class, subtitle = "status-critical", "Contramedida Modbus activada o requerida"

    st.markdown(
        f"""
        <div class="status-panel {css_class}">
            <p class="status-title">{message}</p>
            <p class="status-subtitle">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard(cfg: dict, mode: str, telemetry: dict):
    level, message, _ = evaluate_plant_status(telemetry, cfg)
    process_whatsapp_alerts(telemetry, cfg, level)
    soc = telemetry["soc"]
    inject_corporate_theme()

    v_max = telemetry["highest_cell_voltage"]
    v_min = telemetry["lowest_cell_voltage"]
    t_max = telemetry["max_pack_temperature"]
    t_min = telemetry["min_pack_temperature"]
    now = datetime.now().strftime("%H:%M:%S")

    if mode != MODE_REAL or telemetry.get("source") in ("simulated", "modbus_error"):
        sim_soc = f"{telemetry['soc']:.1f}%"
        st.markdown(
            f'<div class="alert-bar" style="background:#3d2a00;border-color:#ff9f1c;">'
            f'⚠ Modo <b>{mode}</b> — SoC {sim_soc} es simulado. '
            f'Selecciona <b>Real (Modbus)</b> en el panel lateral y recarga (F5).</div>',
            unsafe_allow_html=True,
        )

    if telemetry.get("error"):
        st.markdown(
            f'<div class="alert-bar">⚠ Modbus: {telemetry["error"]} — mostrando respaldo simulado.</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<p class="brand-tag">B-Intelligent</p>', unsafe_allow_html=True)
    st.markdown('<h1 class="brand-title">BMS Cloud Auditor</h1>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="brand-subtitle">{cfg.get("plant_name", "B-Intelligent")} · Color Control GX · {cfg["victron_ip"]}:{cfg["modbus_port"]}</p>',
        unsafe_allow_html=True,
    )

    render_soc_card(
        soc,
        telemetry.get("autonomy_hours"),
        cfg.get("battery_capacity_kwh", 10.0),
        telemetry.get("soc_source_label", ""),
    )
    render_energy_flow_strip(telemetry)

    power_value, power_detail = format_house_power(telemetry.get("house_consumption_w", 0.0))
    pv_value = format_power_watts(telemetry.get("pv_power_w", 0))
    bat_value, bat_detail = format_battery_power(telemetry.get("battery_power_w", 0))
    grid_value, grid_detail = format_grid_power(telemetry.get("grid_power_w", 0))
    modbus_note = "Victron Modbus" if telemetry["source"] == "modbus" else "Simulación"

    col1, col2, col3 = st.columns(3, gap="medium")
    with col1:
        render_metric_card(
            "Voltaje de Celdas",
            f"{v_max:.2f} V",
            f"Mínima: {v_min:.2f} V · Δ celda: {(v_max - v_min) * 1000:.0f} mV · {modbus_note}",
            accent=METRIC_ACCENTS["cells"],
        )
    with col2:
        render_metric_card(
            "Temperatura del Pack",
            f"{t_max:.1f} °C",
            f"Mínima: {t_min:.1f} °C · Rango: {t_max - t_min:.1f} °C",
            accent=METRIC_ACCENTS["temperature"],
        )
    with col3:
        render_metric_card(
            "Consumo de la Casa",
            power_value,
            f"{power_detail} · reg 817",
            accent=METRIC_ACCENTS["consumption"],
        )

    col4, col5, col6 = st.columns(3, gap="medium")
    with col4:
        render_metric_card(
            "Producción Solar",
            pv_value,
            f"Potencia PV instantánea · reg 850 · {modbus_note}",
            accent=METRIC_ACCENTS["solar"],
        )
    with col5:
        render_metric_card(
            "Potencia Batería",
            bat_value,
            f"{bat_detail} · reg 842 · {modbus_note}",
            accent=METRIC_ACCENTS["battery"],
        )
    with col6:
        render_metric_card(
            "Potencia de Red",
            grid_value,
            f"{grid_detail} · reg 820 · {modbus_note}",
            accent=METRIC_ACCENTS["grid"],
        )

    render_status_panel(level, message)
    render_battery_cells_panel(telemetry.get("batteries") or [], cfg)

    source_label = {
        "simulated": "telemetría simulada",
        "modbus": "Victron Modbus TCP en vivo",
        "modbus_error": "Modbus con fallback simulado",
    }.get(telemetry["source"], telemetry["source"])

    jk_soc_debug = " · ".join(
        f"{b.get('name', '?')}: {b['soc']}%"
        for b in telemetry.get("batteries", [])
        if b.get("soc") is not None
    )
    soc_debug = f" · Victron: {telemetry.get('victron_soc', telemetry['soc'])}%"
    if jk_soc_debug:
        soc_debug += f" · JK [{jk_soc_debug}]"

    st.markdown(
        f"""
        <div class="footer-bar">
            Última actualización: {now} · Muestreo cada {cfg["sample_interval_s"]}s · Modo: {mode} · Fuente: {source_label}
            <br><span style="font-size:0.78rem;color:#9eb8d9;">SoC sistema: {telemetry['soc']:.1f}%{soc_debug}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(
        page_title="B-Intelligent — BMS Cloud Auditor",
        page_icon="🔋",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    cfg = load_configuration()
    default_index = 0 if cfg.get("default_mode", "simulated") == "simulated" else 1

    with st.sidebar:
        st.markdown(
            '<p style="font-size:0.72rem;font-weight:800;letter-spacing:0.12em;'
            f'color:{COLOR_ACCENT};text-transform:uppercase;margin-bottom:0.2rem;">Panel de Control</p>',
            unsafe_allow_html=True,
        )
        mode = st.selectbox(
            "Modo operativo",
            [MODE_SIM, MODE_REAL],
            index=default_index,
            key="bintelligent_mode",
        )
        st.caption("Recarga la página (F5) tras cambiar de modo.")
        st.markdown("---")
        st.markdown(f"**Gateway:** `{cfg['victron_ip']}`")
        st.markdown(f"**Intervalo:** `{cfg['sample_interval_s']} s`")
        st.markdown(f"**Batería:** `{cfg.get('battery_capacity_kwh', 10)} kWh`")
        wa = "✅ Activas" if cfg.get("whatsapp_alerts_enabled") else "❌ Off"
        wa_color = "#00ff88" if cfg.get("whatsapp_alerts_enabled") else "#ff6b6b"
        st.markdown(
            f'**WhatsApp:** <span style="color:{wa_color};font-weight:700;">{wa}</span>',
            unsafe_allow_html=True,
        )

    interval = cfg["sample_interval_s"]
    telemetry = fetch_telemetry(mode, cfg)
    render_cell_health_sidebar(telemetry, cfg)
    render_dashboard(cfg, mode, telemetry)

    # Auto-refresh sin duplicar widget keys (st.rerun reemplaza al while True).
    # Pausa el refresco mientras hay una celda seleccionada para no perder el detalle.
    if st.session_state.get("selected_cell") is None:
        time.sleep(interval)
        st.rerun()


if __name__ == "__main__":
    main()
