"""
Alertas WhatsApp vía Cloud API (Meta) con plantillas aprobadas.

Plantilla esperada en Meta Business Manager: alerta_bintelligent
Cuerpo: "🚨 Alerta en {{1}}: {{2}}"
"""

import json
import os
import urllib.error
import urllib.request

WHATSAPP_API_VERSION = "v22.0"
DEFAULT_TEMPLATE_NAME = "alerta_bintelligent"
DEFAULT_TEMPLATE_LANGUAGE = "es"


def send_whatsapp_alert(
    message_text: str,
    plant_name: str = "Casa B-Intelligent",
    *,
    access_token: str | None = None,
    phone_number_id: str | None = None,
    recipient: str | None = None,
    template_name: str | None = None,
    template_language: str | None = None,
) -> tuple[bool, str]:
    """
    Envía una alerta usando plantillas de WhatsApp Cloud API (Meta)
    para saltar la restricción de la ventana de 24 horas.

    Estructura esperada de la plantilla 'alerta_bintelligent':
    "🚨 Alerta en {{1}}: {{2}}"
    """
    token = access_token or os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    recipient = recipient or os.environ.get("WHATSAPP_RECIPIENT")
    template_name = template_name or os.environ.get("WHATSAPP_TEMPLATE_NAME", DEFAULT_TEMPLATE_NAME)
    template_language = template_language or os.environ.get(
        "WHATSAPP_TEMPLATE_LANGUAGE", DEFAULT_TEMPLATE_LANGUAGE
    )

    if not token or not phone_id or not recipient:
        return False, "Faltan variables de entorno de WhatsApp."

    recipient = recipient.lstrip("+").replace(" ", "")
    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_language},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": plant_name},
                        {"type": "text", "text": message_text},
                    ],
                }
            ],
        },
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = json.loads(response.read().decode("utf-8"))
        if "messages" in res_body:
            return True, "Mensaje enviado correctamente mediante plantilla."
        return False, f"Respuesta inesperada de la API: {res_body}"
    except urllib.error.HTTPError as exc:
        err_response = exc.read().decode("utf-8", errors="replace")
        return False, f"Error HTTP {exc.code}: {err_response}"
    except urllib.error.URLError as exc:
        return False, f"Error de conexión: {exc.reason}"
    except Exception as exc:
        return False, f"Error de conexión: {exc}"
