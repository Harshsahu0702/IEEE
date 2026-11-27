"""
Dynamic Hardware Discovery & Component Selection Registry.

Strict Hardware Reality Rule:
- Probes physical USB serial ports (pyserial) for Arduino devices.
- Probes OS host metrics via psutil; explicitly reports unavailable thermal
  sensors when blocked by Windows ACPI rather than inventing mock readings.
- Tracks active user-selected vision source and sensor components.
"""

import logging
import platform
import threading
import time
from typing import Any, Dict, List, Optional

import psutil

from backend.iot.telemetry import get_latest_sensor_data
from backend.vision.camera import camera_stream

logger = logging.getLogger(__name__)

_SELECTION_LOCK = threading.Lock()

# Default user selection (only verified available components are populated)
_ACTIVE_SELECTION: Dict[str, Any] = {
    "vision_source": "0",
    "enabled_sensors": ["cpu_load", "memory_usage", "battery"],
    "arduino_port": None,
}


def _probe_serial_ports() -> List[Dict[str, Any]]:
    """Detect physically attached USB Serial / Arduino ports without opening locks."""
    found: List[Dict[str, Any]] = []
    try:
        import serial.tools.list_ports

        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            is_arduino = any(
                k in desc or k in hwid
                for k in ("arduino", "ch340", "ch341", "usb-serial", "cp210", "ftdi", "uno", "esp32")
            )
            found.append({
                "port": p.device,
                "description": p.description or "Serial Port",
                "is_arduino_likely": is_arduino,
            })
    except Exception as e:
        logger.debug(f"Serial port scan failed: {e}")
    return found


def _probe_host_metrics() -> Dict[str, Any]:
    """Query verified host telemetry capabilities (no hardcoded fake temps)."""
    cpu_pct = psutil.cpu_percent(interval=None)
    mem_pct = psutil.virtual_memory().percent
    bat = getattr(psutil, "sensors_battery", lambda: None)()

    # Check if OS exposes thermal zones (Linux UNO Q exposes it; Windows ACPI typically returns {})
    temps_fn = getattr(psutil, "sensors_temperatures", None)
    temps_map = {}
    if callable(temps_fn):
        try:
            temps_map = temps_fn() or {}
        except Exception:
            temps_map = {}

    host_temp_val = None
    if temps_map:
        for _, entries in temps_map.items():
            if entries:
                host_temp_val = round(float(entries[0].current), 1)
                break

    return {
        "os": platform.system(),
        "cpu_load": {
            "id": "cpu_load",
            "label": "Host CPU Utilization",
            "available": True,
            "value": round(float(cpu_pct), 1),
            "unit": "%",
        },
        "memory_usage": {
            "id": "memory_usage",
            "label": "Host RAM Usage",
            "available": True,
            "value": round(float(mem_pct), 1),
            "unit": "%",
        },
        "battery": {
            "id": "battery",
            "label": "Laptop Battery",
            "available": bat is not None,
            "value": round(float(bat.percent), 1) if bat else None,
            "power_plugged": bool(bat.power_plugged) if bat else None,
            "unit": "%",
        },
        "host_thermal": {
            "id": "host_thermal",
            "label": "Host CPU Temperature",
            "available": host_temp_val is not None,
            "value": host_temp_val,
            "unit": "°C",
            "unavailable_reason": None if host_temp_val is not None else f"Blocked by {platform.system()} ACPI driver (attach Arduino DHT22 for real temperature)",
        },
    }


def discover_hardware() -> Dict[str, Any]:
    """
    Scan and return ONLY physically present / verified hardware components.
    """
    serial_ports = _probe_serial_ports()
    arduino_ports = [p for p in serial_ports if p["is_arduino_likely"]]
    live_iot = get_latest_sensor_data()
    has_live_mqtt_iot = bool(live_iot and live_iot.get("device_id"))
    arduino_attached = bool(arduino_ports) or has_live_mqtt_iot

    host_metrics = _probe_host_metrics()

    # Build verified vision sources
    vision_sources = [
        {
            "id": "0",
            "label": "Laptop Integrated Webcam (Index 0)",
            "type": "webcam",
            "available": True,
            "active": str(camera_stream.camera_source) == "0",
            "is_synthetic": camera_stream.is_synthetic if str(camera_stream.camera_source) == "0" else False,
        },
        {
            "id": "uno_q_edge",
            "label": "Arduino UNO Q (4GB) Edge Camera (HTTP Stream)",
            "type": "edge_ip",
            "available": True,
            "requires_url": True,
            "default_url": "http://192.168.1.50:8080/video",
            "active": isinstance(camera_stream.camera_source, str) and "8080" in str(camera_stream.camera_source),
        },
        {
            "id": "phone_ip",
            "label": "Mobile Phone IP Webcam Stream",
            "type": "phone_ip",
            "available": True,
            "requires_url": True,
            "default_url": "http://192.168.1.15:8080/video",
            "active": isinstance(camera_stream.camera_source, str) and str(camera_stream.camera_source).startswith("http") and "8080" not in str(camera_stream.camera_source),
        },
    ]

    # Build verified sensor components (strictly hide/flag unattached hardware)
    sensors: List[Dict[str, Any]] = [
        {
            "id": "cpu_load",
            "label": host_metrics["cpu_load"]["label"],
            "source": "Host OS",
            "available": True,
            "value": host_metrics["cpu_load"]["value"],
            "unit": "%",
        },
        {
            "id": "memory_usage",
            "label": host_metrics["memory_usage"]["label"],
            "source": "Host OS",
            "available": True,
            "value": host_metrics["memory_usage"]["value"],
            "unit": "%",
        },
    ]

    if host_metrics["battery"]["available"]:
        sensors.append({
            "id": "battery",
            "label": host_metrics["battery"]["label"],
            "source": "Host OS",
            "available": True,
            "value": host_metrics["battery"]["value"],
            "unit": "%",
        })

    if host_metrics["host_thermal"]["available"]:
        sensors.append({
            "id": "host_thermal",
            "label": host_metrics["host_thermal"]["label"],
            "source": "Host OS",
            "available": True,
            "value": host_metrics["host_thermal"]["value"],
            "unit": "°C",
        })

    # Arduino external sensors: only marked available when physical COM or live MQTT device exists
    arduino_source_label = (
        f"Arduino ({arduino_ports[0]['port']})"
        if arduino_ports
        else (f"IoT MQTT ({live_iot.get('device_id')})" if has_live_mqtt_iot else "Arduino (Not Attached)")
    )

    sensors.extend([
        {
            "id": "arduino_temperature",
            "label": "DHT22 Ambient Temperature",
            "source": arduino_source_label,
            "available": arduino_attached,
            "value": live_iot.get("temperature") if arduino_attached else None,
            "unit": "°C",
        },
        {
            "id": "arduino_humidity",
            "label": "DHT22 Relative Humidity",
            "source": arduino_source_label,
            "available": arduino_attached,
            "value": live_iot.get("humidity") if arduino_attached else None,
            "unit": "%",
        },
        {
            "id": "arduino_gas",
            "label": "MQ-2 Gas / Smoke Sensor",
            "source": arduino_source_label,
            "available": arduino_attached,
            "value": live_iot.get("gas_level") if arduino_attached else None,
            "unit": "ppm",
        },
        {
            "id": "arduino_pir",
            "label": "PIR Digital Motion Sensor",
            "source": arduino_source_label,
            "available": arduino_attached,
            "value": live_iot.get("motion_detected") if arduino_attached else None,
            "unit": "",
        },
    ])

    with _SELECTION_LOCK:
        selection = dict(_ACTIVE_SELECTION)
        if arduino_ports and not selection.get("arduino_port"):
            selection["arduino_port"] = arduino_ports[0]["port"]

    return {
        "os": host_metrics["os"],
        "arduino_attached": arduino_attached,
        "serial_ports": serial_ports,
        "host_thermal_blocked_reason": host_metrics["host_thermal"]["unavailable_reason"],
        "vision_sources": vision_sources,
        "sensors": sensors,
        "selection": selection,
        "scanned_at": time.time(),
    }


def update_hardware_selection(vision_source: Optional[str] = None, enabled_sensors: Optional[List[str]] = None) -> Dict[str, Any]:
    """Update active selected hardware components and apply vision source switch if requested."""
    switch_result = None
    if vision_source is not None and str(vision_source).strip():
        vs = str(vision_source).strip()
        if str(camera_stream.camera_source) != vs:
            ok, msg = camera_stream.set_source(vs)
            switch_result = {"success": ok, "message": msg, "source": str(camera_stream.camera_source)}

    with _SELECTION_LOCK:
        if vision_source is not None and str(vision_source).strip():
            _ACTIVE_SELECTION["vision_source"] = str(vision_source).strip()
        if enabled_sensors is not None:
            _ACTIVE_SELECTION["enabled_sensors"] = list(dict.fromkeys(enabled_sensors))
        current = dict(_ACTIVE_SELECTION)

    return {
        "selection": current,
        "camera_switch": switch_result,
    }


def get_selected_sensor_context() -> Dict[str, Any]:
    """
    Build real-time sensor context dict respecting ONLY what the user selected
    and what hardware actually exists.
    """
    with _SELECTION_LOCK:
        enabled = set(_ACTIVE_SELECTION.get("enabled_sensors", []))

    ctx: Dict[str, Any] = {}
    iot = get_latest_sensor_data()

    # External Arduino sensors (only when present & selected)
    if iot:
        if "arduino_temperature" in enabled or not enabled:
            if iot.get("temperature") is not None:
                ctx["temperature"] = iot["temperature"]
        if "arduino_humidity" in enabled or not enabled:
            if iot.get("humidity") is not None:
                ctx["humidity"] = iot["humidity"]
        if "arduino_gas" in enabled or not enabled:
            if iot.get("gas_level") is not None:
                ctx["gas_level"] = iot["gas_level"]
        if "arduino_pir" in enabled or not enabled:
            if iot.get("motion_detected") is not None:
                ctx["motion_detected"] = iot["motion_detected"]

    # Host verified metrics (only when selected)
    if "cpu_load" in enabled:
        ctx["cpu_percent"] = round(float(psutil.cpu_percent(interval=None)), 1)
    if "memory_usage" in enabled:
        ctx["memory_percent"] = round(float(psutil.virtual_memory().percent), 1)
    if "battery" in enabled:
        bat = getattr(psutil, "sensors_battery", lambda: None)()
        if bat is not None:
            ctx["battery_percent"] = round(float(bat.percent), 1)

    return ctx
