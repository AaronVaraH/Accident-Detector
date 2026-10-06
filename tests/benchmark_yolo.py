import time
import numpy as np
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
dummy = np.zeros((480, 640, 3), dtype=np.uint8)

# Warmup
model(dummy, verbose=False)

times = []
for _ in range(10):
    t0 = time.time()
    model(dummy, verbose=False)
    times.append(time.time() - t0)

print(f"YOLOv8n CPU promedio: {np.mean(times)*1000:.2f} ms por frame (~{1.0/np.mean(times):.1f} FPS)")
