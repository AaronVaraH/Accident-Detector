import logging
import os
import tempfile
from typing import Any, Dict, List, Optional
import cv2

from config import settings

logger = logging.getLogger(__name__)

try:
    from inference_sdk import InferenceConfiguration, InferenceHTTPClient
except ImportError:
    InferenceHTTPClient = None
    InferenceConfiguration = None


class RoboflowClient:
    """Cliente para ejecutar workflows serverless de Roboflow (Fuego, Humo, Vehículos y Placas)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        workspace: Optional[str] = None,
        api_url: str = settings.ROBOFLOW_API_URL,
    ):
        self.api_key = api_key or settings.ROBOFLOW_API_KEY
        self.workspace = workspace or settings.ROBOFLOW_WORKSPACE
        self.api_url = api_url
        self.client = None

        if not self.api_key:
            logger.warning("No se proporcionó ROBOFLOW_API_KEY. Los workflows de Roboflow estarán deshabilitados.")
            return

        if InferenceHTTPClient is None:
            logger.warning("inference-sdk no está instalado aún en el entorno.")
            return

        try:
            self.client = InferenceHTTPClient(
                api_url=self.api_url,
                api_key=self.api_key,
            ).configure(InferenceConfiguration(api_key_transport="header"))
            logger.info(f"Cliente Roboflow inicializado para workspace: {self.workspace}")
        except Exception as e:
            logger.error(f"Error al inicializar InferenceHTTPClient: {e}")
            self.client = None

    def _run_workflow_on_frame(
        self,
        workflow_id: str,
        frame,
        parameters: Optional[Dict[str, Any]] = None,
        workspace_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Guarda el frame en buffer temporal y ejecuta el workflow en Roboflow."""
        if not self.client or not workflow_id:
            return None

        ws = workspace_name or self.workspace
        tmp_path = None
        try:
            # Crear imagen temporal para el cliente HTTP
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name
            cv2.imwrite(tmp_path, frame)

            result = self.client.run_workflow(
                workspace_name=ws,
                workflow_id=workflow_id,
                images={"image": tmp_path},
                parameters=parameters or {},
                use_cache=True,
            )
            return result
        except Exception as e:
            logger.error(f"Error al ejecutar workflow '{workflow_id}' en Roboflow: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def detect_fire(self, frame) -> Optional[Dict[str, Any]]:
        """Ejecuta el workflow de detección/segmentación de fuego."""
        if not settings.ROBOFLOW_FIRE_WORKFLOW:
            return None
        return self._run_workflow_on_frame(
            workflow_id=settings.ROBOFLOW_FIRE_WORKFLOW,
            frame=frame,
            parameters={"classes": "fire, smoke, Metal, object, 0"},
        )

    def detect_smoke(self, frame) -> Optional[Dict[str, Any]]:
        """Ejecuta el workflow de detección de humo."""
        if not settings.ROBOFLOW_SMOKE_WORKFLOW:
            return None
        return self._run_workflow_on_frame(
            workflow_id=settings.ROBOFLOW_SMOKE_WORKFLOW,
            frame=frame,
            parameters={"classes": "smoke_belching"},
        )

    def detect_vehicles(self, frame, workspace: Optional[str] = None, workflow_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Ejecuta el workflow de vehículos si está configurado."""
        wf = workflow_id or settings.ROBOFLOW_VEHICLE_WORKFLOW
        if not wf:
            return None
        return self._run_workflow_on_frame(
            workflow_id=wf,
            frame=frame,
            parameters={"classes": "car, truck, bus, motobike"},
            workspace_name=workspace or self.workspace,
        )

    def detect_license_plates(self, frame, workspace: Optional[str] = None, workflow_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Ejecuta el workflow de patentes/placas vehiculares si está configurado."""
        wf = workflow_id or settings.ROBOFLOW_PLATE_WORKFLOW
        if not wf:
            return None
        return self._run_workflow_on_frame(
            workflow_id=wf,
            frame=frame,
            parameters={"classes": "License_Plate"},
            workspace_name=workspace or self.workspace,
        )
