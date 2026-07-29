import time
import logging
from pathlib import Path

from pyModbusTCP.client import ModbusClient

from config_loader import load_configuration

# Configuración de logs con formato industrial
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')


class VictronBmsSafetySupervisor:
    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path else (
            Path(__file__).resolve().parent / "config.json"
        )
        self.config = load_configuration(self.config_path)

        # Inicialización de clientes Modbus para la red industrial
        self.victron_client = ModbusClient(
            host=self.config["victron_host"],
            port=self.config["modbus_port"],
            unit_id=self.config["victron_unit_id"],
            auto_open=True
        )

    def read_bms_telemetry(self):
        """
        En un entorno empresarial, aquí se realiza la lectura de la JK BMS
        vía Modbus RTU, MQTT o API corporativa.
        """
        # Simulación de telemetría de entrada para la pasarela de datos
        return {
            "highest_cell_voltage": 3.35,
            "lowest_cell_voltage": 3.31,
            "max_pack_temperature": 28.5,
            "min_pack_temperature": 27.0
        }

    def aplicar_contramedida_victron(self, register, value, descripcion):
        """Escribe directamente en los registros Modbus TCP de Venus OS / Color Control."""
        if self.victron_client.is_open:
            # Escritura en los registros de control de carga/descarga de Victron
            success = self.victron_client.write_single_register(register, value)
            if success:
                logging.warning(f"✔ Contramedida aplicada con éxito: {descripcion} (Reg: {register} -> Val: {value})")
            else:
                logging.error(f"❌ Fallo crítico al escribir en el registro Modbus de Victron: {register}")
        else:
            logging.error("Conexión Modbus TCP cerrada con el Color Control GX.")

    def supervisar_planta(self):
        telemetria = self.read_bms_telemetry()
        cfg = self.config

        v_max = telemetria["highest_cell_voltage"]
        v_min = telemetria["lowest_cell_voltage"]
        t_max = telemetria["max_pack_temperature"]
        t_min = telemetria["min_pack_temperature"]

        logging.info(f"Monitor de Planta -> Celda Máx: {v_max}V | Celda Mín: {v_min}V | Temp Máx: {t_max}°C")

        # --- ALGORITMO DE CONTROL DE SEGURIDAD ACTIVA ---

        # 1. Protección Térmica Estricta
        if t_max >= cfg["t_critical_high"]:
            # Registro 2706: Forzar apagado del inversor/cargador a través de Color Control
            self.aplicar_contramedida_victron(2706, 4, "APAGADO DE EMERGENCIA POR SOBRETEMPERATURA")
            return

        if t_min <= cfg["t_charge_low"]:
            # Registro 2704: Limitar corriente de carga del sistema a 0 Amperios (Evita daño LiFePO4)
            self.aplicar_contramedida_victron(2704, 0, "CORRIENTE DE CARGA A 0A POR TEMPERATURA BAJO CERO")
            return

        # 2. Protección de Celdas Individuales (Evita desbalanceos catastróficos)
        if v_max >= cfg["v_cell_critical_high"]:
            self.aplicar_contramedida_victron(2704, 0, "CORRIENTE DE CARGA A 0A POR VOLTAJE CRÍTICO DE CELDA")
            return

        if v_max >= cfg["v_cell_warning_high"]:
            # Reducción dinámica: Solicitamos una carga lenta de seguridad (ej. 10 Amperios)
            self.aplicar_contramedida_victron(2704, 10, "REDUCCIÓN DE CARGA PREVENTIVA (CELDA ALTA)")
            return

        if v_min <= cfg["v_cell_critical_low"]:
            # Registro 2705: Limitar corriente de descarga a 0 Amperios para evitar descarga profunda
            self.aplicar_contramedida_victron(2705, 0, "CORRIENTE DE DESCARGA A 0A POR SOBREDESCARGA DE CELDA")
            return

        logging.info("Infraestructura estable. No se requieren acciones de mitigación.")


if __name__ == "__main__":
    logging.info("=== Iniciando Supervisor Industrial de Baterías Victron-BMS ===")
    supervisor = VictronBmsSafetySupervisor()

    try:
        while True:
            supervisor.supervisar_planta()
            time.sleep(5)  # Muestreo industrial continuo cada 5 segundos
    except KeyboardInterrupt:
        logging.info("Supervisor industrial detenido por el operador del sistema.")
