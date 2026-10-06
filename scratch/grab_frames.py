import cv2
import os
import sys

cameras = [
    ("cam_102", "rtsp://admin:admin@123@192.168.1.3:554/Streaming/Channels/102"),
    ("cam_202", "rtsp://admin:admin@123@192.168.1.3:554/Streaming/Channels/202"),
    ("cam_302", "rtsp://admin:admin@123@192.168.1.3:554/Streaming/Channels/302"),
    ("saru_cam", "rtsp://192.168.1.11:8080/h264.sdp"),
]

os.makedirs("scratch/frames", exist_ok=True)

for cam_id, url in cameras:
    print(f"Connecting to {cam_id}...")
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print(f"  FAILED to open {cam_id}")
        continue
    ret, frame = cap.read()
    cap.release()
    if ret and frame is not None:
        path = f"scratch/frames/{cam_id}.jpg"
        cv2.imwrite(path, frame)
        h, w, c = frame.shape
        print(f"  SUCCESS {cam_id}: {w}x{h}, shape={frame.shape}, dtype={frame.dtype}, saved to {path}")
    else:
        print(f"  FAILED to read frame from {cam_id}")
