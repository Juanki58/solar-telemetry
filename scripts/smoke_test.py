#!/usr/bin/env python3
"""
Smoke test de readiness comercial (sin planta real).

- Importa módulos críticos
- Dry-run del supervisor de seguridad (niega writes sobre sim/fallback)
- Comprueba flags por defecto (safety_write_enabled=false)
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

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
    import victron_industrial_bms_safety  # noqa: F401

    # bms_web_monitor importa streamlit; si falta, el smoke lo reporta.
    import bms_web_monitor  # noqa: F401

    _ok("imports: config_loader, jk_bms_client, launcher, safety, web_monitor")


def test_config_defaults() -> None:
    from config_loader import load_configuration

    example = ROOT / "config.example.json"
    cfg = load_configuration(example)
    if cfg.get("safety_write_enabled", True) is not False:
        _fail("safety_write_enabled debe ser false por defecto en config.example.json")
    if cfg.get("web_auth_required_on_lan", False) is not True:
        _fail("web_auth_required_on_lan debe ser true por defecto")
    _ok("defaults: dry-run safety + LAN auth required")


def test_jk_sim_not_online() -> None:
    from jk_bms_client import read_jk_bms_bank

    bank = {"id": "t1", "name": "Test", "jk_host": "192.168.1.34", "cell_count": 16}
    sim = read_jk_bms_bank(bank, simulated=True, sim_t=1000.0)
    if sim.get("data_source") != "simulated":
        _fail(f"data_source simulado esperado, got {sim.get('data_source')}")
    if sim.get("jk_online") is True:
        _fail("simulación no debe marcar jk_online=True")
    _ok("JK simulado: data_source=simulated, jk_online=False")


def test_safety_dry_run_refuses_unreliable() -> None:
    from victron_industrial_bms_safety import VictronBmsSafetySupervisor

    # Config mínima con hosts inventados → sin JK real → unreliable → no write.
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
        "jk_port": 6481,
        "batteries": [
            {"name": "B1", "jk_host": "127.0.0.1", "jk_port": 6499, "cell_count": 16}
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        supervisor = VictronBmsSafetySupervisor(config_path=path, force_dry_run=True)
        if not supervisor.dry_run:
            _fail("supervisor debe estar en dry-run")
        telem = supervisor.read_bms_telemetry()
        if telem.get("write_allowed") is True:
            _fail("write_allowed no debe ser True sin JK real")
        # Intento de escritura debe negarse
        ok = supervisor.aplicar_contramedida_victron(
            2704, 0, "TEST WRITE", telemetry=telem
        )
        if ok:
            _fail("aplicar_contramedida no debe reportar éxito sobre telemetría unreliable")
        supervisor.supervisar_planta()
    _ok("safety: dry-run + refuse writes sin JK real")


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
    _ok("monitor: classify_data_state sim/error/live/fallback")


def test_docs_present() -> None:
    for rel in ("LICENSE", "docs/SAFETY_DISCLAIMER.md", ".streamlit/secrets.toml.example"):
        if not (ROOT / rel).exists():
            _fail(f"falta {rel}")
    _ok("LICENSE + SAFETY_DISCLAIMER + secrets example presentes")


def main() -> int:
    print("=== B-Intelligent smoke test (commercial readiness) ===")
    tests = [
        test_imports,
        test_config_defaults,
        test_jk_sim_not_online,
        test_safety_dry_run_refuses_unreliable,
        test_classify_data_state,
        test_docs_present,
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
