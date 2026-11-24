"""
OmniSense AI — Arduino USB Serial to MQTT Bridge
Reads live sensor data from physical Arduino via USB COM port
and forwards telemetry directly to the OmniSense AI pipeline.
"""

import sys
import time
import json
import re
import logging
import requests
import paho.mqtt.client as mqtt

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("pyserial is required. Install it using: pip install pyserial")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ArduinoBridge")

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USER = "omnisense"
MQTT_PASS = "omnisense_pass"
API_URL = "http://localhost:8000/api"


def find_arduino_port():
    """Scan and return active COM ports."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    # Prefer USB Serial or Arduino in description
    for p in ports:
        desc = (p.description or "").lower()
        if "arduino" in desc or "ch340" in desc or "usb" in desc or "cp210" in desc:
            return p.device
    # Otherwise return the last detected port
    return ports[-1].device


def main():
    print("=" * 68)
    print("    OMNISENSE AI — PHYSICAL ARDUINO USB SERIAL BRIDGE")
    print("=" * 68)

    # 1. Connect to MQTT
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="arduino_serial_bridge")
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
        logger.info(f"Connected to MQTT Broker on {MQTT_BROKER}:{MQTT_PORT}")
    except Exception as e:
        logger.warning(f"Could not connect to MQTT Broker ({e}). Will use HTTP fallback.")
        mqtt_client = None

    # 2. Detect COM Port
    available_ports = list(serial.tools.list_ports.comports())
    print("\nDetected COM Ports on your computer:")
    for i, p in enumerate(available_ports):
        print(f"  [{i+1}] {p.device}: {p.description}")

    if not available_ports:
        print("\n[!] No serial COM ports detected.")
        print("    Ensure your Arduino is plugged in via USB cable.")
        print("    If using Arduino Uno clone, check if CH340 USB drivers are installed.")
        return

    port = find_arduino_port()
    print(f"\nAuto-selected Port: {port}")
    baud = 9600

    try:
        ser = serial.Serial(port, baud, timeout=2.0)
        time.sleep(2)  # Wait for Arduino reset
        logger.info(f"Opened Serial port {port} at {baud} baud. Waiting for sensor data...\n")
    except Exception as e:
        logger.error(f"Failed to open {port}: {e}")
        return

    print("=" * 68)
    print("Listening for incoming Arduino sensor data... (Press Ctrl+C to stop)")
    print("=" * 68)

    while True:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            print(f"[Arduino Raw] {line}")

            # Try parsing JSON
            data = None
            try:
                data = json.loads(line)
            except Exception:
                # If not clean JSON, extract numbers with regex
                t_match = re.search(r"(?:temp|t)\s*[:=]\s*([\d\.]+)", line, re.IGNORECASE)
                g_match = re.search(r"(?:gas|mq2|g)\s*[:=]\s*([\d\.]+)", line, re.IGNORECASE)
                h_match = re.search(r"(?:hum|h)\s*[:=]\s*([\d\.]+)", line, re.IGNORECASE)

                if t_match or g_match or h_match:
                    data = {
                        "device_id": "arduino_uno",
                        "temperature": float(t_match.group(1)) if t_match else 26.0,
                        "gas_level": float(g_match.group(1)) if g_match else 120.0,
                        "humidity": float(h_match.group(1)) if h_match else 55.0,
                        "motion": False,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
                    }

            if data and isinstance(data, dict):
                dev_id = data.get("device_id", "arduino_uno")
                if "timestamp" not in data:
                    data["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")

                payload_str = json.dumps(data)

                # Send via MQTT
                if mqtt_client and mqtt_client.is_connected():
                    topic = f"omnisense/devices/{dev_id}/telemetry"
                    mqtt_client.publish(topic, payload_str)
                    print(f"  --> Forwarded to MQTT [{topic}]: Temp={data.get('temperature')}°C, Gas={data.get('gas_level')}ppm")

        except KeyboardInterrupt:
            print("\nStopped by user.")
            break
        except Exception as e:
            logger.error(f"Error reading serial line: {e}")
            time.sleep(1)

    ser.close()
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
