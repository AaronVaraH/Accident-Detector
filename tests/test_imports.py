import sys
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")

try:
    import cv2
    print(f"OpenCV version: {cv2.__version__}")
except ImportError as e:
    print(f"OpenCV import error: {e}")

try:
    import supervision as sv
    print(f"Supervision version: {sv.__version__}")
except ImportError as e:
    print(f"Supervision import error: {e}")

try:
    from ultralytics import YOLO
    print("Ultralytics YOLO imported successfully.")
except ImportError as e:
    print(f"Ultralytics import error: {e}")

try:
    import requests
    print(f"Requests version: {requests.__version__}")
except ImportError as e:
    print(f"Requests import error: {e}")

try:
    from inference_sdk import InferenceHTTPClient
    print("InferenceHTTPClient imported successfully.")
except ImportError as e:
    print(f"InferenceHTTPClient import error: {e}")
