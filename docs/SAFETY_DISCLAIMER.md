# Aviso de seguridad — B-Intelligent / solar-telemetry

**Lee esto antes de conectar el software a una planta real o de habilitar escrituras Modbus.**

## Qué es (y qué no es) este proyecto

| Es | No es |
|----|--------|
| Monitor de telemetría (Victron GX + JK BMS) | Un **BMS certificado** |
| Herramienta de laboratorio / planta propia | Un controlador de seguridad homologado (SIL/PL) |
| Supervisor **experimental** de umbrales | Sustituto de protecciones hardware |

Los cortes activos hacia Victron (`victron_industrial_bms_safety.py`) son **experimentales**. Por defecto operan en **DRY-RUN** (`safety_write_enabled: false`): solo registran lo que harían, **sin escribir** en el Color Control / Cerbo.

## Reglas operativas

1. **Dry-run por defecto.** No habilites `safety_write_enabled: true` salvo que entiendas el riesgo y tengas protecciones BMS hardware independientes.
2. **Nunca se escribe sobre datos simulados o fallback.** Si JK/Victron no entregan lectura real, el supervisor **niega** cualquier escritura.
3. **El monitor web debe distinguir** simulación, error de conexión y planta en vivo. No interpretes banners de laboratorio como estado real.
4. **LAN (`0.0.0.0`) exige contraseña** (`web_auth_password` en `config.json` o `.streamlit/secrets.toml`). Sin ella el launcher falla cerrado.
5. **Retén siempre** el BMS de celular/pack, fusibles, contactores y consignas Victron/ESS diseñadas por un instalador cualificado.

## Limitación de responsabilidad

EL SOFTWARE SE PROPORCIONA «TAL CUAL», SIN GARANTÍAS. Los autores no se responsabilizan de daños a baterías, inversores, incendios, pérdida de datos, interrupción de servicio ni cualquier daño directo o indirecto derivado del uso, mal uso o fallo del software — incluidos cortes Modbus erróneos, lecturas incorrectas o ausencia de actuación.

Si necesitas protección de batería para uso comercial o crítico, usa un **BMS certificado** y un diseño eléctrico revisado por un profesional.

## Contacto / uso comercial

Este repositorio es open source bajo licencia MIT (ver `LICENSE`). El uso comercial del código está permitido por MIT, pero **no implica certificación de producto**, soporte SLA ni responsabilidad de seguridad eléctrica.
