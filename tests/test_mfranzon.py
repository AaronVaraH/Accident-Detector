import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from huggingface_hub import hf_hub_download
from ultralytics import YOLO

print("Descargando mfranzon/fire-smoke-yolov8...")
try:
    ckpt = hf_hub_download(repo_id="mfranzon/fire-smoke-yolov8", filename="best.pt")
    print(f"Descargado en: {ckpt}")
    m = YOLO(ckpt)
    print("Clases:", m.names)
except Exception as e:
    print("Error:", e)
