import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from huggingface_hub import hf_hub_download
from ultralytics import YOLO
import urllib.request
import numpy as np
import cv2

ckpt = hf_hub_download(repo_id="rabahdev/fire-smoke-yolov8n", filename="best.pt")
model = YOLO(ckpt)

test_urls = [
    ("Llama / Fogata", "https://images.unsplash.com/photo-1508873696983-2df5293cb395?w=640&q=80"),
    ("Fuego forestal", "https://images.unsplash.com/photo-1602980085566-4c40b82b9a7c?w=640&q=80"),
    ("Vela / Llama", "https://images.unsplash.com/photo-1603555501671-8f96b3fce8b4?w=640&q=80")
]

for label, url in test_urls:
    try:
        req = urllib.request.urlopen(url)
        arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
        img = cv2.imdecode(arr, -1)
        res = model(img, conf=0.15, verbose=False)[0]
        print(f"\n{label} ({len(res.boxes)} detecciones):")
        for b in res.boxes:
            print(f"   {model.names[int(b.cls[0])]}: {float(b.conf[0]):.2f}")
    except Exception as e:
        print(f"Error {label}: {e}")
