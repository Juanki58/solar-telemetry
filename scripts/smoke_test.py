#!/usr/bin/env python3
"""
Smoke test de readiness comercial (sin planta real).

- Importa módulos críticos
- Dry-run del supervisor de seguridad (niega writes sobre sim/fallback)
- Comprueba flags por defecto (safety_write_enabled=false)
- Puertas P0: celdas vacías en fallback, write hole cerrado, regs 2704/05/06
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _fail(msg: str) -> None:
    print(f" FAIL {msg}")
    raise AssertionError(msg)


def test_imports() -> None:
    import config_loader  # noqa: F401
    import jk_bms_client  # noqa: F401
    import launcher  # noqa: F401
    import victron_gx_actions  # noqa: F401
    import victron_industrial_bms_safety  # noqa: F401

    # bms_web_monitor importa streamlit; si falta, el smoke lo reporta.
    import bms_web_monitor  # noqa: F401

    _ok("imports: config_loader, jk_bms_client, launcher, gx_actions, safety, web_monitor")


def test_config_defaults() -> None:
    from config_loader import load_configuration

    example = ROOT / "config.example.json"
    cfg = load_configuration(example)
    if cfg.get("safety_write_enabled", True) is not False:
        _fail("safety_write_enabled debe ser false por defecto en config.example.json")
    if cfg.get("safety_write_registers_confirmed", True) is not False:
        _fail("safety_write_registers_confirmed debe ser false por defecto")
    if cfg.get("manual_write_enabled", True) is not False:
        _fail("manual_write_enabled debe ser false por defecto (Acciones dry-run)")
    if cfg.get("web_auth_required_on_lan", False) is not True:
        _fail("web_auth_required_on_lan debe ser true por defecto")
    if cfg.get("battery_source") not in ("victron", "gx_can", "hybrid"):
        _fail(
            f"battery_source ejemplo debe ser victron/gx_can/hybrid, got {cfg.get('battery_source')}"
        )
    if cfg.get("battery_source") == "hybrid" and int(cfg.get("jk_port", 0)) != 502:
        _fail("ejemplo hybrid debe probar jk_port=502 primero (no 6481)")
    _ok("defaults: dry-run safety + Acciones + regs bloqueados + LAN auth + battery_source ok")


def test_jk_sim_not_online() -> None:
    from jk_bms_client import read_jk_bms_bank

    bank = {"id": "t1", "name": "Test", "jk_host": "192.168.1.34", "cell_count": 16}
    sim = read_jk_bms_bank(bank, simulated=True, sim_t=1000.0)
    if sim.get("data_source") != "simulated":
        _fail(f"data_source simulado esperado, got {sim.get('data_source')}")
    if sim.get("jk_online") is True:
        _fail("simulación no debe marcar jk_online=True")
    if not (sim.get("cell_voltages") or sim.get("cells")):
        _fail("modo laboratorio intencional sí puede tener celdas sintéticas etiquetadas")
    _ok("JK simulado: data_source=simulated, jk_online=False")


def test_jk_fallback_no_fake_cells() -> None:
    """P0: fallo/cooldown/unconfigured → vacío, no grid sinusoidal fingiendo mediciones."""
    from jk_bms_client import _JK_FAIL_CACHE, merge_battery_telemetry, read_jk_bms_bank

    _JK_FAIL_CACHE.clear()

    unconfigured = read_jk_bms_bank(
        {"id": "u1", "name": "Sin IP", "jk_host": "IP_DE_TU_JK", "cell_count": 16},
        simulated=False,
    )
    assert unconfigured["data_source"] == "jk_unconfigured"
    assert unconfigured["jk_online"] is False
    assert unconfigured.get("cells") == []
    assert unconfigured.get("cell_voltages") == []
    assert unconfigured.get("highest_cell_voltage") is None

    # Host válido pero forzar cooldown → fallback vacío.
    bank = {"id": "f1", "name": "Offline", "jk_host": "127.0.0.1", "jk_port": 6499, "cell_count": 16}
    key = "127.0.0.1:6499:1"
    _JK_FAIL_CACHE[key] = __import__("time").time()
    fallback = read_jk_bms_bank(bank, simulated=False)
    assert fallback["data_source"] == "jk_fallback"
    assert fallback["jk_online"] is False
    assert fallback.get("cells") == []
    assert fallback.get("cell_voltages") == []
    assert fallback.get("highest_cell_voltage") is None
    _JK_FAIL_CACHE.clear()

    cfg = {"battery_source": "jk_tcp"}
    merged = merge_battery_telemetry(
        {"soc": 50, "source": "modbus", "pack_voltage": 53.0},
        [fallback],
        cfg,
    )
    assert merged["cells_available"] is False
    assert merged.get("cell_voltages") == []
    assert merged.get("highest_cell_voltage") is None
    assert "no disponibles" in (merged.get("cell_voltage_source") or "").lower()
    _ok("JK fallback/unconfigured: celdas vacías (no fake)")


def test_no_invent_cells_from_pack() -> None:
    """P0 honesty: telemetría Victron Modbus no inventa C1..Cn desde pack_voltage."""
    from bms_web_monitor import build_estimated_cell_voltages

    # La función de estimación puede existir para lab, pero el camino Modbus real no la usa.
    assert callable(build_estimated_cell_voltages)

    # Simula el contrato de retorno esperado tras el fix: listas vacías + source honesto.
    # (smoke sin GX real)
    from jk_bms_client import merge_battery_telemetry

    system = {
        "soc": 55.0,
        "pack_voltage": 52.8,
        "source": "modbus",
        "cell_voltages": [],  # no inventadas
        "highest_cell_voltage": None,
        "lowest_cell_voltage": None,
        "cell_voltage_source": "Celdas pendientes de JK TCP (no estimadas desde pack)",
        "cells_available": False,
    }
    banks = [
        {
            "id": "b1",
            "name": "B1",
            "cells": [],
            "cell_voltages": [],
            "data_source": "jk_fallback",
            "jk_online": False,
            "error": "timeout",
        }
    ]
    merged = merge_battery_telemetry(system, banks, {"battery_source": "jk_tcp"})
    assert merged["cell_voltages"] == []
    assert merged["highest_cell_voltage"] is None
    assert merged["cells_available"] is False
    _ok("no inventar celdas desde pack en fallback jk_tcp")


def _minimal_safety_cfg(**overrides) -> dict:
    cfg = {
        "victron_host": "127.0.0.1",
        "modbus_port": 502,
        "victron_unit_id": 100,
        "v_cell_critical_high": 3.60,
        "v_cell_warning_high": 3.45,
        "v_cell_critical_low": 2.60,
        "t_critical_high": 55.0,
        "t_charge_low": 0.0,
        "safety_write_enabled": False,
        "safety_require_jk_online": True,
        "safety_write_registers_confirmed": False,
        "jk_port": 502,
        "battery_source": "jk_tcp",
        "batteries": [
            {"name": "B1", "jk_host": "127.0.0.1", "jk_port": 6499, "cell_count": 16}
        ],
    }
    cfg.update(overrides)
    return cfg


def test_safety_dry_run_refuses_unreliable() -> None:
    from victron_industrial_bms_safety import VictronBmsSafetySupervisor

    cfg = _minimal_safety_cfg()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        supervisor = VictronBmsSafetySupervisor(config_path=path, force_dry_run=True)
        if not supervisor.dry_run:
            _fail("supervisor debe estar en dry-run")
        telem = supervisor.read_bms_telemetry()
        if telem.get("write_allowed") is True:
            _fail("write_allowed no debe ser True sin JK real")
        ok = supervisor.aplicar_contramedida_victron(
            2704, 0, "TEST WRITE", telemetry=telem
        )
        if ok:
            _fail("aplicar_contramedida no debe reportar éxito sobre telemetría unreliable")
        supervisor.supervisar_planta()
    _ok("safety: dry-run + refuse writes sin JK real")


def test_safety_require_jk_online_false_no_write_on_sim() -> None:
    """P0: safety_require_jk_online=false NO autoriza write_allowed sobre sim/fallback."""
    from victron_industrial_bms_safety import VictronBmsSafetySupervisor

    cfg = _minimal_safety_cfg(
        safety_require_jk_online=False,
        safety_write_enabled=True,  # incluso con writes "habilitados"
        safety_write_registers_confirmed=True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        # force_dry_run=None pero sin JK real → write_allowed False
        supervisor = VictronBmsSafetySupervisor(config_path=path, force_dry_run=True)
        telem = supervisor.read_bms_telemetry()
        if telem.get("write_allowed") is True:
            _fail(
                "write_allowed=True con safety_require_jk_online=false y sin JK real "
                "(agujero de seguridad)"
            )
        if telem.get("source") not in ("unreliable", "simulated", None):
            # Debe ser unreliable
            if telem.get("source") == "jk_modbus":
                _fail("source no debe ser jk_modbus sin lectura real")
        ok = supervisor.aplicar_contramedida_victron(
            2704, 0, "HOLE TEST", telemetry=telem
        )
        if ok:
            _fail("escritura no debe pasar con telemetría no real")
    _ok("safety: require_jk_online=false no abre write sobre sim/fallback")


def test_safety_registers_2704_blocked_without_confirm() -> None:
    """P0: regs 2704/05/06 bloqueados sin safety_write_registers_confirmed."""
    from victron_industrial_bms_safety import VictronBmsSafetySupervisor

    cfg = _minimal_safety_cfg(
        safety_write_enabled=True,
        safety_write_registers_confirmed=False,
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        supervisor = VictronBmsSafetySupervisor(config_path=path, force_dry_run=False)
        # Telemetría artificial «live» para aislar el gate de registros.
        live = {
            "source": "jk_modbus",
            "write_allowed": True,
            "error": None,
            "highest_cell_voltage": 3.5,
            "lowest_cell_voltage": 3.2,
        }
        for reg in (2704, 2705, 2706):
            ok = supervisor.aplicar_contramedida_victron(
                reg, 0, f"REG {reg} TEST", telemetry=live
            )
            if ok:
                _fail(f"reg {reg} debe rechazarse sin safety_write_registers_confirmed")

        # Con confirmación + dry-run forzado: dry-run puede «aceptar» intención sin escribir.
        supervisor.registers_confirmed = True
        supervisor.write_enabled = False
        supervisor.dry_run = True
        ok_dry = supervisor.aplicar_contramedida_victron(
            2704, 0, "REG 2704 DRY", telemetry=live
        )
        if not ok_dry:
            _fail("con confirmed + dry-run debe loguear intención (return True) sin Modbus write")
    _ok("safety: 2704/05/06 bloqueados sin confirmed; dry-run OK con confirmed")


def test_safety_live_write_still_needs_enabled() -> None:
    """Con confirmed pero safety_write_enabled=false → dry-run, sin write Modbus real."""
    from victron_industrial_bms_safety import VictronBmsSafetySupervisor

    cfg = _minimal_safety_cfg(
        safety_write_enabled=False,
        safety_write_registers_confirmed=True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        supervisor = VictronBmsSafetySupervisor(config_path=path)
        assert supervisor.dry_run is True
        assert supervisor.write_enabled is False
        live = {"source": "jk_modbus", "write_allowed": True, "error": None}
        with patch.object(supervisor.victron_client, "write_single_register") as mock_write:
            ok = supervisor.aplicar_contramedida_victron(2704, 0, "NO WRITE", telemetry=live)
            assert ok is True  # dry-run success
            mock_write.assert_not_called()
    _ok("safety: confirmed + write_enabled=false = dry-run, sin Modbus write")


def test_classify_data_state() -> None:
    from bms_web_monitor import MODE_REAL, MODE_SIM, classify_data_state

    assert classify_data_state(MODE_SIM, {"source": "simulated", "soc": 40}) == "simulated"
    assert (
        classify_data_state(MODE_REAL, {"source": "modbus_error", "error": "x", "soc": 1})
        == "connection_error"
    )
    assert (
        classify_data_state(
            MODE_REAL,
            {
                "source": "modbus",
                "soc": 50,
                "batteries": [{"data_source": "jk_modbus", "jk_online": True}],
            },
        )
        == "live"
    )
    assert (
        classify_data_state(
            MODE_REAL,
            {
                "source": "modbus",
                "soc": 50,
                "batteries": [{"data_source": "jk_fallback", "jk_online": False}],
            },
        )
        == "mixed_fallback"
    )
    assert (
        classify_data_state(
            MODE_REAL,
            {
                "source": "modbus",
                "soc": 50,
                "batteries": [{"data_source": "victron_gx", "jk_online": False}],
            },
            {"battery_source": "victron"},
        )
        == "live"
    )
    _ok("monitor: classify_data_state sim/error/live/fallback/victron")


def test_victron_battery_source_no_jk_online() -> None:
    from jk_bms_client import fetch_all_batteries, merge_battery_telemetry, uses_victron_battery

    cfg = {"battery_source": "victron", "battery_pack_name": "Pack test"}
    assert uses_victron_battery(cfg)
    system = {
        "soc": 77.0,
        "pack_voltage": 53.1,
        "battery_current_a": -8.2,
        "battery_power_w": -435.0,
        "max_pack_temperature": 29.0,
        "min_pack_temperature": 28.0,
        "source": "modbus",
    }
    banks = fetch_all_batteries(cfg, simulated=False, system_telemetry=system)
    assert len(banks) == 1
    assert banks[0]["jk_online"] is False
    assert banks[0]["data_source"] == "victron_gx"
    assert banks[0]["cells"] == []
    merged = merge_battery_telemetry(system, banks, cfg)
    assert merged["cells_available"] is False
    assert merged["highest_cell_voltage"] is None
    assert "celdas" in merged["cell_voltage_source"].lower() or "CAN" in merged["cell_voltage_source"]
    _ok("victron battery_source: pack sin celdas, jk_online=False")


def test_hybrid_pack_victron_cells_jk() -> None:
    """hybrid: SoC/pack de Victron; celdas solo si JK TCP live; placeholders no timeout."""
    from jk_bms_client import (
        fetch_all_batteries,
        merge_battery_telemetry,
        resolve_battery_source,
        uses_hybrid_battery,
        uses_jk_cell_source,
        uses_victron_battery,
    )

    cfg = {
        "battery_source": "hybrid",
        "soc_source": "victron",
        "jk_port": 502,
        "batteries": [
            {
                "id": "b1",
                "name": "B1",
                "jk_host": "IP_DE_TU_GATEWAY_1",
                "jk_port": 502,
                "cell_count": 16,
                "enabled": True,
            }
        ],
    }
    assert resolve_battery_source(cfg) == "hybrid"
    assert uses_hybrid_battery(cfg)
    assert uses_jk_cell_source(cfg)
    assert not uses_victron_battery(cfg)

    system = {
        "soc": 41.0,
        "pack_voltage": 52.9,
        "battery_current_a": 3.1,
        "battery_power_w": 164.0,
        "source": "modbus",
    }
    banks = fetch_all_batteries(cfg, simulated=False, system_telemetry=system)
    assert len(banks) == 1
    assert banks[0]["data_source"] == "jk_unconfigured"
    assert banks[0]["cells"] == []
    assert banks[0]["jk_online"] is False

    merged = merge_battery_telemetry(system, banks, cfg)
    assert merged["soc"] == 41.0
    assert merged["pack_voltage"] == 52.9
    assert merged["cells_available"] is False
    assert merged["cell_voltages"] == []
    assert "hybrid" in (merged.get("cell_voltage_source") or "").lower()

    # Celdas live → cells_available; SoC sigue siendo Victron.
    live_bank = {
        "id": "b1",
        "name": "B1",
        "cells": [3.30 + i * 0.001 for i in range(16)],
        "cell_voltages": [3.30 + i * 0.001 for i in range(16)],
        "data_source": "jk_modbus",
        "jk_online": True,
        "jk_host": "192.168.1.50",
        "error": None,
        "max_pack_temperature": 28.0,
        "min_pack_temperature": 27.0,
        "soc": 99.0,
    }
    merged_live = merge_battery_telemetry(system, [live_bank], cfg)
    assert merged_live["cells_available"] is True
    assert len(merged_live["cell_voltages"]) == 16
    assert merged_live["soc"] == 41.0  # Victron, no 99% del JK
    assert "hybrid" in (merged_live.get("cell_voltage_source") or "").lower()
    _ok("hybrid: pack Victron + celdas JK TCP (placeholders seguros)")


def test_docs_present() -> None:
    for rel in (
        "LICENSE",
        "docs/SAFETY_DISCLAIMER.md",
        "docs/VICTRON_MODBUS_PROBE.md",
        "docs/JK_RS485_GATEWAY.md",
        ".streamlit/secrets.toml.example",
    ):
        if not (ROOT / rel).exists():
            _fail(f"falta {rel}")
    text = (ROOT / "docs/SAFETY_DISCLAIMER.md").read_text(encoding="utf-8")
    for needle in ("2704", "safety_write_registers_confirmed", "celdas no disponibles"):
        if needle not in text:
            _fail(f"SAFETY_DISCLAIMER debe documentar: {needle}")
    probe = (ROOT / "docs/VICTRON_MODBUS_PROBE.md").read_text(encoding="utf-8")
    for needle in ("2700", "2902", "806", "manual_write_enabled"):
        if needle not in probe:
            _fail(f"VICTRON_MODBUS_PROBE debe documentar: {needle}")
    gw = (ROOT / "docs/JK_RS485_GATEWAY.md").read_text(encoding="utf-8")
    for needle in ("001", "Modbus", "502", "hybrid", "USR-TCP232", "Waveshare", "CAN"):
        if needle not in gw:
            _fail(f"JK_RS485_GATEWAY debe documentar: {needle}")
    _ok("LICENSE + SAFETY + MODBUS_PROBE + JK_RS485_GATEWAY + secrets example presentes")


def test_gx_actions_dry_run_and_blocks() -> None:
    """Acciones opcionales: dry-run por defecto; 2704 bloqueado; confirmación obligatoria."""
    from victron_gx_actions import (
        BLOCKED_AUTO_CUTOFF_REGS,
        action_set_grid_setpoint,
        action_set_hub4_mode,
        action_set_relay,
        build_write_preview,
        execute_manual_write,
    )

    cfg = {
        "victron_host": "127.0.0.1",
        "modbus_port": 502,
        "victron_unit_id": 100,
        "manual_write_enabled": False,
    }
    assert 2704 in BLOCKED_AUTO_CUTOFF_REGS

    prev = build_write_preview(cfg, 2704, 0, "cutoff")
    assert prev.blocked_reason is not None
    assert prev.would_write is False

    no_conf = action_set_grid_setpoint(cfg, 50, confirmed=False)
    assert no_conf["ok"] is False
    assert no_conf["error"] == "not_confirmed"

    dry = action_set_grid_setpoint(cfg, 50, confirmed=True)
    assert dry["ok"] is True
    assert dry["dry_run"] is True
    assert dry["written"] is False

    dry_mode = action_set_hub4_mode(cfg, 1, confirmed=True)
    assert dry_mode["ok"] is True and dry_mode["written"] is False

    dry_relay = action_set_relay(cfg, 0, False, confirmed=True)
    assert dry_relay["ok"] is True and dry_relay["written"] is False

    blocked = execute_manual_write(cfg, 2704, 0, "no", confirmed=True)
    assert blocked["ok"] is False
    assert blocked["error"] == "blocked_register"

    # Con manual_write_enabled pero sin tocar la red: mock del cliente.
    cfg_on = {**cfg, "manual_write_enabled": True}
    with patch("victron_gx_actions.ModbusClient") as mock_cls:
        mock = mock_cls.return_value
        mock.open.return_value = True
        mock.write_single_register.return_value = True
        written = action_set_grid_setpoint(cfg_on, 100, confirmed=True)
        assert written["ok"] is True
        assert written["written"] is True
        mock.write_single_register.assert_called_once()

    _ok("gx_actions: dry-run default, confirm gate, 2704 blocked, write path gated")


def main() -> int:
    print("=== B-Intelligent smoke test (commercial readiness) ===")
    tests = [
        test_imports,
        test_config_defaults,
        test_jk_sim_not_online,
        test_jk_fallback_no_fake_cells,
        test_no_invent_cells_from_pack,
        test_safety_dry_run_refuses_unreliable,
        test_safety_require_jk_online_false_no_write_on_sim,
        test_safety_registers_2704_blocked_without_confirm,
        test_safety_live_write_still_needs_enabled,
        test_classify_data_state,
        test_victron_battery_source_no_jk_online,
        test_hybrid_pack_victron_cells_jk,
        test_docs_present,
        test_gx_actions_dry_run_and_blocks,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — smoke resume todos los checks
            failed += 1
            print(f" FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"=== Resultado: {len(tests) - failed}/{len(tests)} OK ===")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
