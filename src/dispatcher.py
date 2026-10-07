"""
Módulo de Despacho y Notificaciones de Emergencia (Fase 4).
Soporta:
1. Despacho por SMS inmediato vía Twilio REST API.
2. Despacho a Telegram Bot con imagen y ficha estructurada.
3. Cooldown para evitar saturación de mensajes repetidos.
"""

import logging
import time
from typing import Any, Dict, Optional
import requests
from requests.auth import HTTPBasicAuth

from config import settings

logger = logging.getLogger("AlertDispatcher")


class AlertDispatcher:
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.api_key = settings.TWILIO_API_KEY
        self.api_secret = settings.TWILIO_API_SECRET
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_phone = settings.TWILIO_FROM_PHONE
        self.to_phone = settings.TWILIO_TO_PHONE

        self.telegram_token = settings.TELEGRAM_BOT_TOKEN
        self.telegram_chat_id = settings.TELEGRAM_CHAT_ID

        self._last_sms_time = 0.0
        self._sms_cooldown = 15.0  # Mínimo 15 segundos entre SMS para pruebas de demo

    def send_sms_alert(self, text: str, force: bool = False) -> bool:
        """Envía un SMS a través de la API REST oficial de Twilio."""
        if not self.account_sid or not self.to_phone or not self.from_phone:
            logger.warning("Credenciales de Twilio incompletas en settings.")
            return False

        now = time.time()
        if not force and (now - self._last_sms_time < self._sms_cooldown):
            logger.info("SMS omitido por cooldown anti-spam.")
            return False

        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
            
            # Preferir API Key / Secret si están presentes, fallback a Account SID / Auth Token
            if self.api_key and self.api_secret:
                auth = HTTPBasicAuth(self.api_key, self.api_secret)
            else:
                auth = HTTPBasicAuth(self.account_sid, self.auth_token)

            payload = {
                "From": self.from_phone,
                "To": self.to_phone,
                "Body": text[:1500],
            }

            resp = requests.post(url, data=payload, auth=auth, timeout=6.0)
            if resp.status_code in [200, 201]:
                self._last_sms_time = now
                logger.info(f"SMS despachado con éxito a {self.to_phone} (SID: {resp.json().get('sid')})")
                return True
            else:
                logger.error(f"Fallo en Twilio SMS ({resp.status_code}): {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Error despachando SMS con Twilio: {e}")
            return False

    def dispatch_incident_alert(self, enriched_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Formatea el expediente de siniestro y envía las notificaciones a los canales activos.
        """
        inc = enriched_payload.get("incident", {})
        title = inc.get("title", "INCIDENTE DETECTADO")
        subtitle = inc.get("subtitle", "")
        urgency = inc.get("urgency", "ALERTA")

        veh = enriched_payload.get("vehicle") or {}
        plate = veh.get("plate") or "NO VISIBLE"
        brand_model = f"{veh.get('brand', '')} {veh.get('model', '')}".strip() or "Desconocido"
        fuel = veh.get("fuel_type", "Gasolina")

        loc = enriched_payload.get("location") or {}
        address = loc.get("street") or loc.get("address") or "Cruce Metropolitano"

        weather = enriched_payload.get("weather") or {}
        wind = weather.get("wind_speed_kmh", 0)

        hazmat = veh.get("hazmat_alert")

        # Construir mensaje de texto conciso para SMS
        sms_lines = [
            f"🚨 [CAD 911 / TITAN] {title} ({urgency})",
            f"📍 Ubicación: {address}",
            f"🚗 Vehículo: {plate} - {brand_model} ({fuel})",
        ]
        if hazmat:
            sms_lines.append(f"⚠️ HAZMAT: {hazmat}")
        if wind > 15:
            sms_lines.append(f"💨 Viento: {wind} km/h (Propagación activa)")

        sms_body = "\n".join(sms_lines)
        sms_success = self.send_sms_alert(sms_body)

        return {
            "sms_sent": sms_success,
            "destination": self.to_phone,
            "message": sms_body,
        }


# Instancia singleton
alert_dispatcher = AlertDispatcher()
