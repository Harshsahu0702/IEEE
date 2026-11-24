#!/usr/bin/env python3
"""
OmniSense AI - IoT Device Telemetry Simulator
Simulates a multi-sensor station (DHT22 + MQ-2 + PIR) publishing over MQTT.
Usage:
    python backend/iot/simulator.py --device-id env-station-01
    python backend/iot/simulator.py --spike  # Injects hazardous gas and heat spike
"""
import sys
import time
import json
import random
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import paho.mqtt.client as mqtt
from backend.config import settings


def run_simulator(
    host: str = "localhost",
    port: int = 1883,
    device_id: str = "simulated-env-01",
    interval: float = 2.0,
    count: int = 0,
    spike: bool = False,
    username: str = "",
    password: str = ""
):
    print("=" * 60)
    print(f"OMNISENSE AI - IOT TELEMETRY SIMULATOR")
    print(f"Target Broker : {host}:{port}")
    print(f"Device ID     : {device_id}")
    print(f"Interval      : {interval}s")
    print(f"Spike Mode    : {'ACTIVE (Simulating Gas & Temp Hazard!)' if spike else 'Normal Baseline'}")
    print("=" * 60)

    # Initialize MQTT client
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sim_{device_id}_{int(time.time())}"
        )
    else:
        client = mqtt.Client(client_id=f"sim_{device_id}_{int(time.time())}")

    if username:
        client.username_pw_set(username, password)

    try:
        client.connect(host, port, keepalive=60)
        client.loop_start()
        print(f"✓ Connected to MQTT Broker at {host}:{port}")
    except Exception as e:
        print(f"✗ Failed to connect to MQTT broker: {e}")
        print("Note: Ensure Mosquitto is running via docker-compose or locally.")
        return

    # Announce device online status
    status_topic = f"omnisense/devices/{device_id}/status"
    status_payload = {
        "device_id": device_id,
        "status": "online",
        "firmware_version": "1.0.0-sim",
        "timestamp": datetime.utcnow().isoformat()
    }
    client.publish(status_topic, json.dumps(status_payload), qos=1)
    print(f"✓ Published status 'online' to topic: {status_topic}")

    telemetry_topic = f"omnisense/devices/{device_id}/telemetry"
    published_count = 0

    try:
        while True:
            published_count += 1

            if spike:
                # Hazardous spike: Gas > 400 ppm, Temp > 32 °C
                temperature = round(36.0 + random.uniform(1.0, 5.0), 1)  # 37-41 °C
                humidity = round(68.0 + random.uniform(-2.0, 4.0), 1)
                gas_level = round(520.0 + random.uniform(10.0, 150.0), 1)  # 530-670 ppm (Hazard)
                motion = True
            else:
                # Normal nominal conditions
                temperature = round(23.5 + random.uniform(-0.8, 1.2), 1)  # 22.7-24.7 °C
                humidity = round(52.0 + random.uniform(-3.0, 3.0), 1)
                gas_level = round(120.0 + random.uniform(-15.0, 25.0), 1)  # 105-145 ppm (Safe)
                motion = random.random() > 0.7

            payload = {
                "device_id": device_id,
                "temperature": temperature,
                "humidity": humidity,
                "gas_level": gas_level,
                "motion": motion,
                "timestamp": datetime.utcnow().isoformat()
            }

            payload_json = json.dumps(payload)
            client.publish(telemetry_topic, payload_json, qos=1)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Packet #{published_count} -> {telemetry_topic}: Temp={temperature}°C, Gas={gas_level}ppm, Hum={humidity}%, Motion={motion}")

            if count > 0 and published_count >= count:
                break

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nSimulator stopped by operator.")
    finally:
        client.loop_stop()
        client.disconnect()
        print("Disconnected cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OmniSense AI IoT Telemetry Simulator")
    parser.add_argument("--host", default=settings.MQTT_BROKER_HOST, help="MQTT broker host")
    parser.add_argument("--port", type=int, default=settings.MQTT_BROKER_PORT, help="MQTT broker port")
    parser.add_argument("--device-id", default="simulated-env-01", help="Device identifier string")
    parser.add_argument("--interval", type=float, default=2.0, help="Publish interval in seconds")
    parser.add_argument("--count", type=int, default=0, help="Number of packets to publish (0 for continuous)")
    parser.add_argument("--spike", action="store_true", help="Inject critical gas and temperature spikes")
    parser.add_argument("--username", default=settings.MQTT_USERNAME, help="MQTT username")
    parser.add_argument("--password", default=settings.MQTT_PASSWORD, help="MQTT password")

    args = parser.parse_args()
    run_simulator(
        host=args.host,
        port=args.port,
        device_id=args.device_id,
        interval=args.interval,
        count=args.count,
        spike=args.spike,
        username=args.username,
        password=args.password
    )
