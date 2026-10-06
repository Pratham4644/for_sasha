import io
import time
import numpy as np
import cv2
from PIL import Image
from ultralytics import YOLO

MODEL_PATH = r"C:\Users\saran\OneDrive\Desktop\Saakh\REMOTE-CAMERA-FINAL\friend-system\for_sasha\sagemaker_yolo\yolo26s.pt"

print(f"Loading YOLO model from {MODEL_PATH}...")
model = YOLO(MODEL_PATH)
print("Model loaded successfully.")

# Test 1: Synthetic test image with NO objects (blank wall / solid color)
blank_img = np.zeros((720, 1280, 3), dtype=np.uint8)
blank_img[:] = (200, 200, 200) # light gray wall
res_blank = model.predict(source=blank_img, conf=0.25, verbose=False)
blank_dets = []
for r in res_blank:
    for box in r.boxes:
        blank_dets.append({
            "class_id": int(box.cls[0]),
            "class_name": r.names[int(box.cls[0])],
            "confidence": float(box.conf[0]),
            "bbox": [float(x) for x in box.xyxy[0].tolist()]
        })
print(f"Test 1 (Blank/No Object): Detected {len(blank_dets)} objects (Expected: 0). Result: {'PASS' if len(blank_dets) == 0 else 'FAIL'}")

# Test 2: Standard test image with person and bicycle from ultralytics sample
# Ultralytics has a built-in bus image or we can test with a real sample
import urllib.request
test_url = "https://ultralytics.com/images/bus.jpg"
print(f"Downloading standard benchmark image ({test_url})...")
try:
    urllib.request.urlretrieve(test_url, "scratch/bus.jpg")
    bus_img = cv2.imread("scratch/bus.jpg")
    start = time.monotonic()
    res_bus = model.predict(source=bus_img, conf=0.25, verbose=False)
    lat = (time.monotonic() - start) * 1000.0
    bus_dets = []
    for r in res_bus:
        for box in r.boxes:
            bus_dets.append({
                "class_id": int(box.cls[0]),
                "class_name": r.names[int(box.cls[0])],
                "confidence": round(float(box.conf[0]), 2),
                "bbox": [round(float(x), 1) for x in box.xyxy[0].tolist()]
            })
    print(f"Test 2 (Benchmark Image): latency={lat:.1f}ms, detected {len(bus_dets)} items:")
    for d in bus_dets:
        print(f"   - {d['class_name']} ({d['confidence']*100:.0f}%) bbox={d['bbox']}")
    has_person = any(d['class_name'] == 'person' for d in bus_dets)
    has_bus = any(d['class_name'] == 'bus' for d in bus_dets)
    print(f"Person detected: {has_person}, Bus detected: {has_bus}. Benchmark test: {'PASS' if (has_person and has_bus) else 'FAIL'}")
except Exception as e:
    print(f"Failed benchmark download/inference: {e}")
