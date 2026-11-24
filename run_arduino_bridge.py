"""
OmniSense Arduino USB Serial Bridge.
- Auto-detects connected Arduino COM port.
- Relays real-time sensor telemetry to OmniSense.
- Listens for Threat / Security Alarms and signals Arduino to trigger Red Strobe LED (Pin 13 & 8).
"""

import sys
import time
import json
import threading
import requests
import serial.tools.list_ports
import serial

API_URL = "http://localhost:8000/api"
DEFAULT_BAUD = 9600

alarm_active = False

def list_ports():
    return list(serial.tools.list_ports.comports())

def alarm_listener_thread(ser):
    """Polls OmniSense backend for active alarms and controls Arduino Red LED."""
    global alarm_active
    last_state = False
    
    while True:
        try:
            res = requests.get(f"{API_URL}/devices/alarm", timeout=2)
            if res.status_code == 200:
                data = res.json()
                is_active = data.get("alarm_active", False)
                if is_active and not last_state:
                    ser.write(b"ALARM:ON\n")
                    print(f"\n🚨 [ALARM SYNC] Threat detected on camera ({data.get('threat_type')}) -> Sent ALARM:ON to Arduino!")
                    last_state = True
                elif not is_active and last_state:
                    ser.write(b"ALARM:OFF\n")
                    print("\n🟢 [ALARM CLEARED] Sent ALARM:OFF to Arduino (Standby).")
                    last_state = False
            time.sleep(0.4)
        except Exception:
            time.sleep(1.0)

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

    # Start automated backend alarm synchronization thread
    threading.Thread(target=alarm_listener_thread, args=(ser,), daemon=True).start()

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
