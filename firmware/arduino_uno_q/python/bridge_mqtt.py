#!/usr/bin/env python3
"""
OmniSense AI - Arduino Uno Q Linux Bridge MQTT Publisher
Runs on the embedded Linux side of Arduino Uno Q.
Reads JSON from the MCU serial bridge and publishes to Mosquitto MQTT.

[VERIFICATION REQUIRED]:
Verify serial device node (/dev/ttyATH0 vs /dev/ttyS0 vs Bridge)
against official Arduino Uno Q documentation.
"""
import os
import sys
import json
import time
import serial
import paho.mqtt.client as mqtt

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {
        "mqtt_host": "localhost",
        "mqtt_port": 1883,
        "mqtt_username": "omnisense_user",
        "mqtt_password": "omnisense_pass",
        "device_id": "uno-q-env-01",
        "serial_port": "/dev/ttyATH0",
        "baud_rate": 115200
    }


def main():
    cfg = load_config()
    device_id = cfg.get("device_id", "uno-q-env-01")
    telemetry_topic = f"omnisense/devices/{device_id}/telemetry"
    status_topic = f"omnisense/devices/{device_id}/status"

    print(f"Connecting to MQTT broker {cfg['mqtt_host']}:{cfg['mqtt_port']}...")
    client = mqtt.Client(client_id=f"uno_q_bridge_{device_id}")

    if cfg.get("mqtt_username"):
        client.username_pw_set(cfg["mqtt_username"], cfg["mqtt_password"])

    client.connect(cfg["mqtt_host"], cfg["mqtt_port"], 60)
    client.loop_start()

    # Announce status
    client.publish(status_topic, json.dumps({
        "device_id": device_id,
        "status": "online",
        "firmware": "uno-q-1.0.0"
    }), qos=1)

    print(f"Opening Serial bridge {cfg['serial_port']} at {cfg['baud_rate']} baud...")
    ser = serial.Serial(cfg["serial_port"], cfg["baud_rate"], timeout=2.0)

    while True:
        try:
            line = ser.readline().decode("utf-8").strip()
            if not line:
                continue

            # Validate valid JSON schema before publishing
            data = json.loads(line)
            if "device_id" in data and "temperature" in data and "gas_level" in data:
                payload = json.dumps(data)
                client.publish(telemetry_topic, payload, qos=1)
                print(f"Published telemetry -> {payload}")
            else:
                print(f"Skipped invalid sensor packet: {line}")
        except json.JSONDecodeError:
            print(f"Malformed serial line: {line}")
        except Exception as e:
            print(f"Bridge loop error: {e}")
            time.sleep(1.0)


if __name__ == "__main__":
    main()
