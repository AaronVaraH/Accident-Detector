import time
import numpy as np
from ultralytics import YOLO

v_model = YOLO("yolov8n.pt")
f_model = YOLO("models/fire_smoke.pt")

dummy = np.zeros((480, 640, 3), dtype=np.uint8)

# Warmup
v_model(dummy, verbose=False)
f_model(dummy, verbose=False)

t0 = time.time()
for _ in range(10):
    v_model(dummy, verbose=False)
    f_model(dummy, verbose=False)
total = time.time() - t0
print(f"Ambos modelos juntos en el mismo frame: {total/10*1000:.1f} ms (~{10/total:.1f} FPS reales directos)")
