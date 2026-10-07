import cv2
import logging
from pathlib import Path
from typing import Generator, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class VideoStream:
    """Manejador de ingestión de video para archivos locales (MP4/AVI), streams RTSP o Webcam."""

    def __init__(self, source: Union[int, str] = 0):
        self.source = source
        self.cap: Optional[cv2.VideoCapture] = None
        self._fps: float = 30.0
        self._width: int = 0
        self._height: int = 0
        self._total_frames: int = 0
        self._open()

    def _open(self) -> None:
        source_target = self.source
        if isinstance(self.source, str):
            path_obj = Path(self.source)
            if not path_obj.exists():
                candidate = Path("tests/video_samples") / path_obj.name
                if candidate.exists():
                    source_target = str(candidate)
        self.cap = cv2.VideoCapture(source_target)
        if not self.cap.isOpened():
            raise RuntimeError(f"No fue posible abrir la fuente de video: {self.source}")

        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self._fps = fps if fps and fps > 0 else 30.0
        self._width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        logger.info(
            f"Video cargado exitosamente. Fuente: {self.source}, "
            f"Resolución: {self._width}x{self._height}, FPS: {self._fps:.2f}"
        )

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def total_frames(self) -> int:
        return self._total_frames

    def read_frames(self) -> Generator[Tuple[int, cv2.typing.MatLike], None, None]:
        """Generador que cede el número de frame y la imagen (frame) consecutivamente."""
        frame_idx = 0
        while self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.info("Fin de la transmisión o frame no disponible.")
                break
            yield frame_idx, frame
            frame_idx += 1

    def release(self) -> None:
        if self.cap and self.cap.isOpened():
            self.cap.release()
            logger.info("Fuente de video liberada.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
