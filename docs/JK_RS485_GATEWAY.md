# Guía práctica: JK BMS RS485-1 → gateway LAN (celdas) + Victron CAN intacto

Objetivo: **seguir usando el pack por CAN/DVCC hacia el Color Control / Cerbo** (SoC, V, I, potencia Victron) y **añadir celdas C1…C16** vía **RS485-1 → gateway Ethernet/WiFi Modbus TCP**, sin tocar el cableado CAN.

Config del software: `"battery_source": "hybrid"` — pack Victron + celdas JK TCP.  
Detalle de seguridad: [`SAFETY_DISCLAIMER.md`](SAFETY_DISCLAIMER.md). Mapa GX: [`VICTRON_MODBUS_PROBE.md`](VICTRON_MODBUS_PROBE.md).

---

## Lista de compra (genérica, sin enlaces de tienda)

| Qué | Tipo de producto (busca por modelo/familia) | Notas |
|-----|-----------------------------------------------|--------|
| Gateway RS485 → LAN | **USR-TCP232** (serie RS485↔ETH/WiFi) o **Waveshare RS485 TO ETH** (Modbus gateway) | Preferir modelos que hablen **Modbus TCP** (no solo “TCP raw transparente” sin modo Modbus) |
| Cable RS485 | Par trenzado A/B (+ GND si el gateway lo pide) | Corto, lejos de potencia DC |
| Alimentación gateway | 5 V / 9–24 V según el modelo | Independiente del bus CAN |
| (Opcional) 2.º gateway | Igual que el primero | Solo si tienes **2 baterías** y quieres un IP por BMS |

No hace falta comprar adaptadores USB-RS485 en el PC si el gateway ya publica Modbus TCP en la LAN.

---

## Pasos 1-2-3

### 1) App JK: protocolo Modbus en RS485-1

1. Abre la app oficial JK / menú de protocolo del BMS.
2. En el puerto **RS485-1** (o “RS485 Protocol”), elige **`001` = Modbus** (no el protocolo propietario JK si quieres un gateway Modbus estándar).
3. Anota **baud rate** (suele ser 115200 en JK; confirma en tu firmware), **parity** (normalmente 8N1) y **Modbus slave / unit ID** (a menudo `1`).
4. **No desconectes ni reconfigures el CAN** hacia Victron. El CAN sigue siendo la fuente de verdad del pack para el GX.

### 2) Cableado RS485-1 → gateway

```text
JK BMS RS485-1          Gateway RS485
─────────────────       ─────────────────
  A (Data+)     ─────►    A / D+
  B (Data−)     ─────►    B / D−
  GND (si hay)  ─────►    GND (si el gateway lo exige)
```

- CAN Victron: **intacto** (mismo bus que ya tienes al Cerbo / Color Control).
- RS485-1: **solo** hacia el gateway (otra “vía” de datos, solo lectura de celdas).
- Si el enlace no responde: prueba cruzar A/B una vez; termina el bus si el manual del gateway lo indica (resistencia 120 Ω).

Configura el gateway en modo **Modbus TCP ↔ Modbus RTU** (slave RS485 = unit ID del JK). IP fija en tu LAN.

### 3) Software: `battery_source: hybrid`

En `config.json` (copia desde `config.example.json`):

```json
{
  "victron_host": "192.168.1.XX",
  "modbus_port": 502,
  "battery_source": "hybrid",
  "soc_source": "victron",
  "jk_port": 502,
  "batteries": [
    {
      "name": "Batería 1",
      "jk_host": "IP_DEL_GATEWAY",
      "jk_port": 502,
      "jk_unit_id": 1,
      "cell_count": 16
    }
  ]
}
```

- **Puerto TCP:** prueba **`502` primero** (estándar Modbus TCP). No asumas `6481` salvo que el fabricante del gateway/JK lo documente.
- Pack / SoC / corriente: siguen saliendo del **Victron GX**.
- Celdas: salen del **gateway** cuando responde; si el gateway aún no tiene IP, verás “celdas no disponibles” sin inventar voltajes.

---

## Dos BMS en paralelo (2 baterías)

| Escenario | Recomendación |
|-----------|----------------|
| Un gateway + bus RS485 compartido | Posible si cada JK tiene **unit ID distinto** (1 y 2) y el gateway permite varios slaves. Más frágil. |
| Un gateway por BMS (recomendado) | Cada gateway con su IP; en `batteries` dos entradas (`jk_host` distinto, `jk_unit_id` suele ser 1 en cada uno). |
| CAN Victron | Ambos BMS pueden seguir en el **mismo bus CAN** hacia el GX (como ahora). No mezclar la topología CAN con el RS485 del gateway. |

Con `"battery_bank_mode": "parallel"`, el SoC del sistema es el del **Cerbo** (no se suman SoC de los JK).

---

## Comprobar que el gateway responde

Desde el PC en la misma LAN (PowerShell), con la IP del gateway:

```powershell
# Sustituye IP_GATEWAY; puerto 502 primero
Test-NetConnection IP_GATEWAY -Port 502
```

Luego arranca el monitor (`battery_source: hybrid`). Si Victron OK y JK sin lectura: banner naranja “celdas no disponibles”; cuando el gateway responda, aparecerán C1…C16.

---

## Qué NO hacer

- No quitar el CAN “para probar TCP”: el híbrido existe precisamente para **mantener** Victron.
- No poner `"battery_source": "jk_tcp"` si quieres seguir mostrando el pack del GX como fuente principal de SoC/V/I.
- No confiar en tiendas dudosas con “JK BMS WiFi magic”; usa gateways Modbus conocidos (USR / Waveshare y equivalentes industriales).
- No habilitar `safety_write_enabled` hasta tener celdas **reales** live y haber leído el disclaimer.

---

## Cuando tengas la IP del gateway

Dile al asistente / anota:

1. **IP del gateway** (y si hay segundo BMS: IP del 2.º).
2. **Puerto TCP** que deja abierto (¿502? ¿otro?).
3. **Unit ID** Modbus del JK (¿1?).
4. Confirmación: app JK en **001 Modbus** en RS485-1.
5. IP del **Cerbo / Color Control** (ya suele estar en `victron_host`).

Con eso se rellena `config.json` local y se valida la lectura de celdas sin tocar el CAN.
