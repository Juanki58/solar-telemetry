"""
B-Intelligent — BMS Cloud Auditor
Panel gráfico de monitorización en tiempo real (tkinter / Windows).
"""

import tkinter as tk
from datetime import datetime
from pathlib import Path

from config_loader import load_configuration

SAMPLE_INTERVAL_MS = 5000
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

# Paleta corporativa B-Intelligent
COLOR_BG = "#0a1628"
COLOR_SURFACE = "#132238"
COLOR_SURFACE_LIGHT = "#1c3254"
COLOR_BORDER = "#2a4a72"
COLOR_TEXT = "#f0f4f8"
COLOR_TEXT_MUTED = "#8fa3bf"
COLOR_ACCENT = "#00d4aa"
COLOR_GREEN = "#00e676"
COLOR_YELLOW = "#ffc107"
COLOR_RED = "#ff5252"
COLOR_GREEN_DARK = "#0d4d2a"


def read_bms_telemetry() -> dict:
    """Simulación de telemetría (misma fuente que el supervisor industrial)."""
    return {
        "highest_cell_voltage": 3.35,
        "lowest_cell_voltage": 3.31,
        "max_pack_temperature": 28.5,
        "min_pack_temperature": 27.0,
    }


def evaluate_plant_status(telemetry: dict, cfg: dict) -> tuple[str, str, str]:
    """
    Evalúa alertas según el algoritmo del supervisor Victron-BMS.
    Retorna: (nivel, mensaje, color_fondo)
    """
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


class BmsCloudAuditorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config = load_configuration()
        self.title("B-Intelligent — BMS Cloud Auditor")
        self.configure(bg=COLOR_BG)
        self.geometry("920x620")
        self.minsize(820, 560)

        self._build_ui()
        self.refresh_dashboard()

    def _build_ui(self):
        # ── Cabecera ──────────────────────────────────────────────────────
        header = tk.Frame(self, bg=COLOR_BG, padx=28, pady=22)
        header.pack(fill="x")

        tk.Label(
            header,
            text="B-Intelligent",
            font=("Helvetica", 11, "bold"),
            fg=COLOR_ACCENT,
            bg=COLOR_BG,
        ).pack(anchor="w")

        tk.Label(
            header,
            text="BMS Cloud Auditor",
            font=("Helvetica", 26, "bold"),
            fg=COLOR_TEXT,
            bg=COLOR_BG,
        ).pack(anchor="w")

        tk.Label(
            header,
            text=f"Color Control GX  ·  {self.config['victron_host']}:{self.config['modbus_port']}  ·  Unit ID {self.config['victron_unit_id']}",
            font=("Helvetica", 10),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_BG,
        ).pack(anchor="w", pady=(6, 0))

        divider = tk.Frame(self, bg=COLOR_BORDER, height=1)
        divider.pack(fill="x", padx=28)

        # ── Tarjetas de telemetría ────────────────────────────────────────
        cards = tk.Frame(self, bg=COLOR_BG, padx=28, pady=24)
        cards.pack(fill="both", expand=True)
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)

        self.voltage_card = self._create_metric_card(
            cards, "Voltaje de Celdas", column=0
        )
        self.temperature_card = self._create_metric_card(
            cards, "Temperatura del Pack", column=1
        )

        # ── Semáforo de estado ────────────────────────────────────────────
        status_frame = tk.Frame(self, bg=COLOR_BG, padx=28)
        status_frame.pack(fill="x", pady=(0, 28))

        self.status_panel = tk.Frame(
            status_frame,
            bg=COLOR_GREEN_DARK,
            highlightbackground=COLOR_GREEN,
            highlightthickness=2,
            padx=20,
            pady=28,
        )
        self.status_panel.pack(fill="x")

        self.status_label = tk.Label(
            self.status_panel,
            text="SISTEMA ESTABLE",
            font=("Helvetica", 28, "bold"),
            fg=COLOR_TEXT,
            bg=COLOR_GREEN_DARK,
        )
        self.status_label.pack()

        self.status_subtitle = tk.Label(
            self.status_panel,
            text="Sin alertas activas en la planta",
            font=("Helvetica", 11),
            fg=COLOR_TEXT,
            bg=COLOR_GREEN_DARK,
        )
        self.status_subtitle.pack(pady=(8, 0))

        # ── Barra inferior ────────────────────────────────────────────────
        footer = tk.Frame(self, bg=COLOR_SURFACE, padx=28, pady=10)
        footer.pack(fill="x", side="bottom")

        self.footer_label = tk.Label(
            footer,
            text="",
            font=("Helvetica", 9),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
        )
        self.footer_label.pack(anchor="w")

    def _create_metric_card(self, parent, title: str, column: int) -> dict:
        outer = tk.Frame(
            parent,
            bg=COLOR_SURFACE,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            padx=24,
            pady=22,
        )
        outer.grid(row=0, column=column, sticky="nsew", padx=(0, 12) if column == 0 else (12, 0))

        tk.Label(
            outer,
            text=title.upper(),
            font=("Helvetica", 10, "bold"),
            fg=COLOR_ACCENT,
            bg=COLOR_SURFACE,
        ).pack(anchor="w")

        value_label = tk.Label(
            outer,
            text="—",
            font=("Helvetica", 36, "bold"),
            fg=COLOR_TEXT,
            bg=COLOR_SURFACE,
        )
        value_label.pack(anchor="w", pady=(16, 4))

        detail_label = tk.Label(
            outer,
            text="",
            font=("Helvetica", 11),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_SURFACE,
        )
        detail_label.pack(anchor="w")

        return {"frame": outer, "value": value_label, "detail": detail_label}

    def refresh_dashboard(self):
        telemetry = read_bms_telemetry()
        level, message, status_color = evaluate_plant_status(telemetry, self.config)

        v_max = telemetry["highest_cell_voltage"]
        v_min = telemetry["lowest_cell_voltage"]
        t_max = telemetry["max_pack_temperature"]
        t_min = telemetry["min_pack_temperature"]

        self.voltage_card["value"].config(text=f"{v_max:.2f} V")
        self.voltage_card["detail"].config(
            text=f"Mínima: {v_min:.2f} V   ·   Δ celda: {(v_max - v_min) * 1000:.0f} mV"
        )

        self.temperature_card["value"].config(text=f"{t_max:.1f} °C")
        self.temperature_card["detail"].config(
            text=f"Mínima: {t_min:.1f} °C   ·   Rango: {t_max - t_min:.1f} °C"
        )

        if level == "STABLE":
            panel_bg = COLOR_GREEN_DARK
            border = COLOR_GREEN
            subtitle = "Sin alertas activas en la planta"
        elif level == "WARNING":
            panel_bg = "#4a3f00"
            border = COLOR_YELLOW
            subtitle = "Acción preventiva recomendada"
        else:
            panel_bg = "#4a1212"
            border = COLOR_RED
            subtitle = "Contramedida Modbus activada o requerida"

        self.status_panel.config(bg=panel_bg, highlightbackground=border)
        self.status_label.config(text=message, bg=panel_bg)
        self.status_subtitle.config(text=subtitle, bg=panel_bg)

        now = datetime.now().strftime("%H:%M:%S")
        self.footer_label.config(
            text=f"Última actualización: {now}  ·  Muestreo cada {SAMPLE_INTERVAL_MS // 1000}s  ·  Modo: telemetría simulada"
        )

        self.after(SAMPLE_INTERVAL_MS, self.refresh_dashboard)


if __name__ == "__main__":
    app = BmsCloudAuditorApp()
    app.mainloop()
