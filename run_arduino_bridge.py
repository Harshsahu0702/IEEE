"""
OmniSense Arduino USB Serial Bridge (MQTT Event-Push Edition).
- Auto-detects connected Arduino COM port.
- Relays real-time sensor telemetry to OmniSense MQTT broker.
- Subscribes to MQTT topic `omnisense/alerts/strobe` for sub-15ms hardware strobe/buzzer activation.
"""

import os
import sys
import time
import json
import threading
import requests
import serial.tools.list_ports
import serial
import paho.mqtt.client as mqtt

API_URL = os.environ.get("OMNISENSE_API_URL", "http://localhost:8000/api")
MQTT_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USERNAME", "omnisense_user")
MQTT_PASS = os.environ.get("MQTT_PASSWORD", "omnisense_pass")
DEFAULT_BAUD = 9600

alarm_active = False
mqtt_connected = False
mqtt_client = None
_last_serial_state = False
_state_lock = threading.Lock()


def list_ports():
    return list(serial.tools.list_ports.comports())


def _apply_alarm_state(ser, is_active: bool, threat_type: str = "", source: str = "MQTT"):
    global _last_serial_state, alarm_active
    with _state_lock:
        alarm_active = is_active
        if is_active and not _last_serial_state:
            ser.write(b"ALARM:ON\n")
            print(f"\n🚨 [{source} PUSH] Threat detected ({threat_type}) -> Sent ALARM:ON to Arduino!")
            _last_serial_state = True
        elif not is_active and _last_serial_state:
            ser.write(b"ALARM:OFF\n")
            print(f"\n🟢 [{source} CLEARED] Sent ALARM:OFF to Arduino (Standby).")
            _last_serial_state = False


def start_mqtt_listener(ser):
    """Connect to OmniSense MQTT broker for <15ms push-based strobe/buzzer triggers."""
    global mqtt_connected, mqtt_client

    def on_connect(client, userdata, flags, rc, properties=None):
        global mqtt_connected
        rc_val = rc.value if hasattr(rc, "value") else rc
        if rc_val == 0:
            mqtt_connected = True
            client.subscribe("omnisense/alerts/strobe", qos=1)
            print(f"✓ [MQTT] Subscribed to omnisense/alerts/strobe ({MQTT_HOST}:{MQTT_PORT}) — push latency <15ms!")

    def on_disconnect(client, userdata, flags=None, rc=None, properties=None):
        global mqtt_connected
        mqtt_connected = False

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            _apply_alarm_state(ser, bool(data.get("alarm_active", False)), data.get("threat_type", ""), source="MQTT")
        except Exception as e:
            print(f"MQTT alarm parse error: {e}")

    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="arduino_usb_bridge")
    else:
        client = mqtt.Client(client_id="arduino_usb_bridge")

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    mqtt_client = client

    def _connect_loop():
        while True:
            try:
                client.connect(MQTT_HOST, MQTT_PORT, 60)
                client.loop_forever()
            except Exception:
                time.sleep(3.0)

    threading.Thread(target=_connect_loop, daemon=True).start()


def alarm_fallback_thread(ser):
    """Safety-net fallback ONLY if MQTT broker is unavailable (polls slowly at 1.5s)."""
    while True:
        if not mqtt_connected:
            try:
                res = requests.get(f"{API_URL}/devices/alarm", timeout=1.5)
                if res.status_code == 200:
                    data = res.json()
                    _apply_alarm_state(
                        ser,
                        bool(data.get("alarm_active", False)),
                        data.get("threat_type", ""),
                        source="HTTP-FALLBACK",
                    )
            except Exception:
                pass
        time.sleep(1.5)

def main():
    print("=" * 64)
    print("  OmniSense AI - Arduino Hardware Alarm & Telemetry Bridge")
    print("=" * 64)

    ports = list_ports()
    if not ports:
        print("\n❌ Koi bhi COM Port detect nahi hua!")
        print("\n[Troubleshooting Steps]:")
        print("1. Data Cable Check: Phone ki data cable use karein (sirf charging cable nahi).")
        print("2. USB Port Badlein: Laptop ke dusre USB port me lagakar dekhein.")
        print("3. CH340 Driver: Agar clone Arduino hai, toh CH341SER driver install karein.")
        return

    print("\nDetect huye Ports:")
    for i, p in enumerate(ports):
        print(f" [{i+1}] {p.device} - {p.description}")

    selected_port = ports[0].device
    for p in ports:
        desc = p.description.lower()
        if "arduino" in desc or "ch340" in desc or "usb-serial" in desc or "ch341" in desc:
            selected_port = p.device
            break

    print(f"\nConnecting to {selected_port} at {DEFAULT_BAUD} baud...")
    try:
        ser = serial.Serial(selected_port, DEFAULT_BAUD, timeout=1)
        print(f"✓ Connected to {selected_port}! Arduino Hardware Ready.")
        print("  - Pin 13: Built-in LED (Will flash RED on Threat Alert)")
        print("  - Pin 8 : External Alert Buzzer/LED")
    except Exception as e:
        print(f"❌ Port open nahi ho paya: {e}")
        return

    print("\n[Active] Reading Arduino sensor telemetry & ready for threat alarms...")
    print("Tip: Test alarm manually by typing 'alarm' or 'off' in this terminal.\n")

    # Start instant MQTT push subscriber + disconnected safety fallback
    start_mqtt_listener(ser)
    threading.Thread(target=alarm_fallback_thread, args=(ser,), daemon=True).start()

    # Interactive input thread for instant manual testing
    def manual_input_loop():
        global alarm_active
        while True:
            try:
                cmd = sys.stdin.readline().strip().lower()
                if cmd in ["alarm", "on", "1"]:
                    ser.write(b"ALARM:ON\n")
                    print("\n🚨 [MANUAL TRIGGER] Sent ALARM:ON to Arduino -> RED LED FLASHING!")
                elif cmd in ["off", "0", "stop"]:
                    ser.write(b"ALARM:OFF\n")
                    print("\n🟢 [MANUAL CLEAR] Sent ALARM:OFF to Arduino -> Normal Mode.")
            except Exception:
                break

    threading.Thread(target=manual_input_loop, daemon=True).start()

    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if not line:
                continue
            if line.startswith("{") and line.endswith("}"):
                data = json.loads(line)
                t = data.get("temperature", 25.0)
                g = data.get("gas_level", 120.0)
                m = data.get("motion", False)
                al = data.get("alarm", False)
                status_symbol = "🚨 ALARM ACTIVE" if al else "🟢 NORMAL"
                print(f"[{status_symbol}] Temp: {t}°C | Gas: {g}ppm | Motion: {m}")
                if mqtt_client and mqtt_connected:
                    telemetry_payload = {
                        "device_id": data.get("device_id", "uno-usb-01"),
                        "temperature": float(t),
                        "humidity": float(data.get("humidity", 50.0)),
                        "gas_level": float(g),
                        "motion": bool(m),
                        "timestamp": int(time.time()),
                    }
                    mqtt_client.publish(
                        f"omnisense/devices/{telemetry_payload['device_id']}/telemetry",
                        json.dumps(telemetry_payload),
                        qos=0,
                    )
            else:
                print(f"Arduino: {line}")
        except KeyboardInterrupt:
            print("\nStopping Arduino bridge...")
            try:
                ser.write(b"ALARM:OFF\n")
            except Exception:
                pass
            break
        except Exception as ex:
            pass

if __name__ == "__main__":
    main()
