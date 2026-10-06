"""
Módulo de Internacionalización (i18n) para el Sistema de Seguridad Vial.
Permite alternar y configurar el idioma de la interfaz HUD, alertas y telemetría (Español / Inglés).
"""

from typing import Dict, Any


class LocalizationManager:
    """Gestor de traducción y textos dinámicos con soporte para Español (es) e Inglés (en)."""

    TRANSLATIONS: Dict[str, Dict[str, str]] = {
        "es": {
            # Encabezado
            "live_badge": "EN VIVO",
            "system_title": "SISTEMA DE SEGURIDAD VIAL",
            "webcam_source": "WEBCAM EN VIVO",
            "video_source": "CANAL DE VÍDEO",
            "motion_label": "MOV",
            "motion_calm": "CALMO",
            "motion_dynamic": "DINAMICO",
            "motion_fast": "RAPIDO",
            "motion_high": "ALTO",
            
            # Ventana
            "window_title": "Monitor de Incidentes Viales",

            # Entidades detectadas
            "person": "Persona",
            "car": "Auto",
            "motorcycle": "Moto",
            "bus": "Bus",
            "truck": "Camion",
            "entity": "Entidad",

            # Fuego y Humo
            "fire": "FUEGO",
            "smoke": "HUMO",
            "fire_detected_title": "FUEGO DETECTADO",
            "fire_detected_sub": "Llama activa o incendio en la zona de monitoreo",
            "smoke_detected_title": "HUMO DETECTADO",
            "smoke_detected_sub": "Emision de humo o combustion en la zona de monitoreo",
            "fire_smoke_detected_title": "FUEGO Y HUMO DETECTADOS",
            "fire_smoke_detected_sub": "Incendio activo y emision de humo confirmados",

            # Incidentes Cinemáticos
            "collision_fire_title": "COLISION CON INCENDIO",
            "collision_fire_sub": "Colision critica en vehiculo #{id} con presencia de fuego",
            "collision_smoke_title": "COLISION CON HUMO",
            "collision_smoke_sub": "Colision critica en vehiculo #{id} con emision de humo",
            "critical_brake_title": "FRENADO CRITICO / COLISION",
            "critical_brake_sub": "Desaceleracion violenta o impacto en vehiculo #{id}",

            # Pie de página (Footer)
            "status_active": "VIGILANCIA ACTIVA",
            "status_alert": "ALERTA ACTIVA",
            "incidents_count": "SINIESTROS CONFIRMADOS",
            "footer_shortcuts": "[Q] Salir  [P] Pausar  [L] Idioma ({lang})  [F] Pantalla Completa",
            "language_name": "ESP",
        },
        "en": {
            # Header
            "live_badge": "LIVE",
            "system_title": "ROAD SAFETY SYSTEM",
            "webcam_source": "LIVE WEBCAM",
            "video_source": "VIDEO FEED",
            "motion_label": "MOTION",
            "motion_calm": "CALM",
            "motion_dynamic": "DYNAMIC",
            "motion_fast": "FAST",
            "motion_high": "HIGH",

            # Window
            "window_title": "Road Incident Monitor",

            # Detected Entities
            "person": "Person",
            "car": "Car",
            "motorcycle": "Motorcycle",
            "bus": "Bus",
            "truck": "Truck",
            "entity": "Entity",

            # Fire & Smoke
            "fire": "FIRE",
            "smoke": "SMOKE",
            "fire_detected_title": "FIRE DETECTED",
            "fire_detected_sub": "Active flame or fire in monitoring area",
            "smoke_detected_title": "SMOKE DETECTED",
            "smoke_detected_sub": "Smoke emission or combustion in monitoring area",
            "fire_smoke_detected_title": "FIRE & SMOKE DETECTED",
            "fire_smoke_detected_sub": "Active fire and confirmed smoke emission",

            # Kinematic Incidents
            "collision_fire_title": "COLLISION WITH FIRE",
            "collision_fire_sub": "Critical collision on vehicle #{id} with active fire",
            "collision_smoke_title": "COLLISION WITH SMOKE",
            "collision_smoke_sub": "Critical collision on vehicle #{id} with smoke emission",
            "critical_brake_title": "CRITICAL BRAKING / IMPACT",
            "critical_brake_sub": "Violent deceleration or impact on vehicle #{id}",

            # Footer
            "status_active": "ACTIVE MONITORING",
            "status_alert": "ACTIVE ALERT",
            "incidents_count": "CONFIRMED INCIDENTS",
            "footer_shortcuts": "[Q] Quit  [P] Pause  [L] Lang ({lang})  [F] Fullscreen",
            "language_name": "ENG",
        },
    }

    def __init__(self, default_lang: str = "es"):
        self.set_language(default_lang)

    def normalize_lang(self, lang: str) -> str:
        code = str(lang).lower().strip()
        if code in ["en", "eng", "english", "ingles"]:
            return "en"
        return "es"

    def set_language(self, lang: str) -> None:
        self.current_lang = self.normalize_lang(lang)

    def toggle_language(self) -> str:
        self.current_lang = "en" if self.current_lang == "es" else "es"
        return self.current_lang

    def get(self, key: str, **kwargs) -> str:
        lang_dict = self.TRANSLATIONS.get(self.current_lang, self.TRANSLATIONS["es"])
        text = lang_dict.get(key, self.TRANSLATIONS["es"].get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def get_class_name(self, coco_name: str) -> str:
        mapping = {
            "person": self.get("person"),
            "persona": self.get("person"),
            "car": self.get("car"),
            "auto": self.get("car"),
            "motorcycle": self.get("motorcycle"),
            "moto": self.get("motorcycle"),
            "bus": self.get("bus"),
            "truck": self.get("truck"),
            "camion": self.get("truck"),
        }
        return mapping.get(coco_name.lower(), coco_name.capitalize())


# Instancia global accesible
i18n = LocalizationManager(default_lang="es")
