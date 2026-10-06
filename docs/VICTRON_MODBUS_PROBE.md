# Victron GX Modbus probe (planta)

Host de referencia: `192.168.1.37:502` · `battery_source=victron` (JK vía CAN).

Fuente del mapa: [victronenergy/dbus_modbustcp attributes.csv](https://github.com/victronenergy/dbus_modbustcp/blob/master/attributes.csv) y [ESS mode 2 and 3](https://www.victronenergy.com/live/ess:ess_mode_2_and_3).

## Unit IDs que responden

| Unit | Rol observado | Notas |
|------|---------------|--------|
| 100 (y 0) | `com.victronenergy.system` + settings ESS | Unit de config `victron_unit_id` |
| 225 | `com.victronenergy.battery` | Pack agregado (SoC ~35 %, temp reg **262**) |
| 247 | Otro servicio battery | SoC distinto; sin temp en 262 |
| 225 como inversor | **No** | `inverter_unit_id=225` en config histórica no es VE.Bus |

## Lecturas sistema (unit 100) — ya usadas por el monitor

| Reg | Path | Lectura ejemplo |
|-----|------|-----------------|
| 817–819 | AC Consumption L1–L3 | L1≈349 W |
| 820 | Grid L1 Power | ≈62 W |
| 840 | Battery Voltage | 52.7 V (×0.1) |
| 841 | Battery Current | 15.6 A (×0.1) |
| 842 | Battery Power | ≈822 W |
| 843 | Battery SoC | 35 % |
| 850 | DC PV Power | 0 W |

## ESS / relé — útiles y respondiendo (unit 100)

| Reg | Path | Ejemplo | Uso en Acciones |
|-----|------|---------|-----------------|
| 806 | Relay/0/State | 0=abierto | Lectura + toggle (dry-run) |
| 807 | Relay/1/State | 0 | Lectura (+ toggle opcional) |
| 2700 | CGwacs/AcPowerSetPoint | 50 W | Lectura + consigna (dry-run) |
| 2701 | MaxChargePercentage | 100 | Solo lectura insight |
| 2702 | MaxDischargePercentage | 100 | Solo lectura insight |
| 2900 | BatteryLife/State | 10 (BL off) | Lectura insight |
| 2901 | MinimumSocLimit | 30.0 % (raw/10) | Lectura insight |
| 2902 | Hub4Mode | 1 (ESS fase) | Lectura + cambio modo (dry-run) |

## Batería (unit 225)

| Reg | Path | Ejemplo |
|-----|------|---------|
| 259 | Dc/0/Voltage | 52.74 V (÷100) |
| 261 | Dc/0/Current | 13.3 A (÷10) |
| **262** | Dc/0/Temperature | **22.4 °C** (÷10) — usar en vez de 282 |
| 266 | Soc | 35.0 % (÷10) |
| 318/319 | Min/Max cell temp | 24.0 °C |

`config` histórico usaba `modbus_reg_battery_temperature=282` (History/LastDischarge). Preferir **262** si configuras `battery_unit_id: 225`.

## Escrituras — política

- **Permitidas en UI Acciones** (solo con `manual_write_enabled` + confirmación): 806, 807, 2700, 2902.
- **Bloqueadas** (cortes DVCC / supervisor): 2704, 2705, 2706 — no se reactivan desde Acciones ni en bucle automático sin auditoría.
- Sin `manual_write_enabled`: solo dry-run (log de intención).

## Próxima investigación de registros

1. Localizar Unit ID real de **VE.Bus / Multi** (setpoint Mode 3 regs 37/96) — no respondió en 225.
2. Confirmar si unit **247** es un segundo BMS/JK o un servicio duplicado del GX.
3. Venus ≥3.50: valorar setpoint 32-bit **2716** (esta planta no respondió 2711–2719).
4. Tras auditar cableado del relé GX, documentar qué carga conmuta el 806 antes de `manual_write_enabled=true`.
