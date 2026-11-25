#!/usr/bin/env python3
"""
OmniSense AI - Arduino UNO Q Edge Camera & Motion Node
Runs on the Qualcomm QRB2210 Debian Linux side of the Arduino UNO Q.

What it does (Zero Laptop CPU used for motion detection):
1. Captures frames from a USB webcam plugged into the Arduino UNO Q (/dev/video0).
2. Runs lightweight edge motion detection directly on the Arduino UNO Q.
3. Streams live MJPEG video at http://<ARDUINO_IP>:8080/video for OmniSense UI.
4. Publishes motion events to the OmniSense MQTT broker on the laptop.
"""

import os
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import cv2
import paho.mqtt.client as mqtt

# Configuration (override via environment variables or edit defaults)
LAPTOP_MQTT_HOST = os.environ.get("OMNISENSE_HOST", "192.168.1.100")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
DEVICE_ID = os.environ.get("DEVICE_ID", "uno-q-cam-01")
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
STREAM_PORT = int(os.environ.get("STREAM_PORT", "8080"))
MOTION_THRESHOLD = float(os.environ.get("MOTION_THRESHOLD", "0.008"))

latest_jpeg = None
jpeg_lock = threading.Lock()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/video", "/"):
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()

        while True:
            with jpeg_lock:
                frame_bytes = latest_jpeg
            if frame_bytes:
                try:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                    self.wfile.write(frame_bytes + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    break
            time.sleep(0.05)

    def log_message(self, format, *args):
        pass


def main():
    global latest_jpeg

    # 1. Connect to OmniSense MQTT broker on laptop
    client = mqtt.Client(client_id=f"uno_q_edge_{DEVICE_ID}")
    client.username_pw_set("omnisense_user", "omnisense_pass")
    try:
        client.connect(LAPTOP_MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        print(f"[MQTT] Connected to {LAPTOP_MQTT_HOST}:{MQTT_PORT}")
    except Exception as e:
        print(f"[MQTT] Warning: Could not connect to {LAPTOP_MQTT_HOST}:{MQTT_PORT} ({e})")

    # 2. Start MJPEG HTTP server on Arduino UNO Q
    server = ThreadedHTTPServer(("0.0.0.0", STREAM_PORT), MJPEGHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[STREAM] Serving MJPEG at http://0.0.0.0:{STREAM_PORT}/video")

    # 3. Open USB webcam attached to Arduino UNO Q
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    prev_gray = None
    last_motion_pub = 0.0
    topic = f"omnisense/devices/{DEVICE_ID}/telemetry"

    print("[EDGE] Running motion detection on Arduino UNO Q (0% laptop CPU)...")
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(0.1)
            continue

        # Edge motion detection on Arduino QRB2210
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        motion_detected = False
        if prev_gray is not None:
            delta = cv2.absdiff(prev_gray, gray)
            thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
            changed_ratio = cv2.countNonZero(thresh) / float(thresh.size)
            motion_detected = changed_ratio >= MOTION_THRESHOLD
        prev_gray = gray

        # Publish edge motion signal to laptop
        now = time.time()
        if motion_detected and (now - last_motion_pub >= 1.0):
            last_motion_pub = now
            payload = {
                "device_id": DEVICE_ID,
                "temperature": 0.0,
                "humidity": 0.0,
                "gas_level": 0.0,
                "motion": True,
                "timestamp": int(now),
            }
            try:
                client.publish(topic, json.dumps(payload), qos=0)
            except Exception:
                pass

        # Encode JPEG for HTTP stream
        ok_jpg, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok_jpg:
            with jpeg_lock:
                latest_jpeg = buf.tobytes()

        time.sleep(0.03)


if __name__ == "__main__":
    main()
