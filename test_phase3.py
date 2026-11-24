"""
OmniSense AI - Phase 3 Comprehensive Test Suite
Tests:
1. Pydantic Telemetry Schema Validation (Valid, invalid, malformed, malicious fields)
2. Auto-registration of untrusted/unknown devices as 'pending'
3. Admin Device Approval Gate (POST /devices/{id}/approve)
4. Device Health diagnostics endpoint (GET /devices/{id}/health)
5. Background Offline Checker (marks stale devices offline after 30s)
6. Integration test: Ingest Spiked Telemetry -> DB -> Environment Monitoring Task -> Event ('pending_review')
"""
import os
import sys
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

# Set project root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import SessionLocal
from backend.database.init_db import init_database
from backend.database import crud
from backend.database.models import Device, DeviceTelemetry, Event
from backend.iot.telemetry_schema import TelemetryPayload, DeviceStatusPayload
from backend.iot.telemetry import telemetry_handler
from backend.monitoring.runner import task_manager


def test_telemetry_schema_validation():
    print("\n--- [Test 1] Pydantic Schema Validation Tests ---")

    # 1. Valid Telemetry
    valid_data = {
        "device_id": "sensor-alpha-01",
        "temperature": 26.5,
        "humidity": 48.2,
        "gas_level": 115.0,
        "motion": True,
        "timestamp": datetime.utcnow().isoformat()
    }
    obj = TelemetryPayload(**valid_data)
    assert obj.device_id == "sensor-alpha-01"
    assert obj.temperature == 26.5
    print("✓ Valid telemetry payload validated successfully.")

    # 2. Malformed JSON handled cleanly
    malformed_raw = b"this is not json {{"
    res = telemetry_handler.handle_raw_telemetry(malformed_raw)
    assert res is None, "Malformed payload should be dropped and return None!"
    print("✓ Malformed non-JSON payload cleanly rejected.")

    # 3. Invalid field values (e.g. negative gas level)
    invalid_data = {
        "device_id": "sensor-01",
        "temperature": 25.0,
        "humidity": 50.0,
        "gas_level": -10.0,  # Invalid: negative
        "motion": False
    }
    res = telemetry_handler.handle_raw_telemetry(json.dumps(invalid_data).encode("utf-8"))
    assert res is None, "Payload with negative gas level must be rejected!"
    print("✓ Negative gas_level payload rejected by schema validator.")

    # 4. Invalid device ID (special characters / path traversal)
    bad_id_data = {
        "device_id": "../../etc/passwd",
        "temperature": 25.0,
        "humidity": 50.0,
        "gas_level": 100.0,
        "motion": False
    }
    res = telemetry_handler.handle_raw_telemetry(json.dumps(bad_id_data).encode("utf-8"))
    assert res is None, "Suspicious device_id rejected by pattern validation."
    print("✓ Suspicious device_id with invalid characters cleanly dropped.")


def test_auto_registration_and_approval():
    print("\n--- [Test 2] Device Auto-Registration & Admin Approval Gate ---")
    init_database()
    db = SessionLocal()

    new_device_id = f"auto-sensor-{int(time.time())}"

    # Verify device doesn't exist yet
    assert crud.get_device_by_id(db, new_device_id) is None

    # Ingest valid telemetry from new device
    payload = {
        "device_id": new_device_id,
        "temperature": 22.0,
        "humidity": 45.0,
        "gas_level": 95.0,
        "motion": False,
        "timestamp": datetime.utcnow().isoformat()
    }
    res = telemetry_handler.handle_raw_telemetry(json.dumps(payload).encode("utf-8"))
    assert res is not None

    # Verify device was auto-registered with 'pending' status
    db.expire_all()
    device = crud.get_device_by_id(db, new_device_id)
    assert device is not None
    assert device.status == "pending"
    assert device.approval_status == "pending"
    print(f"✓ Unknown device '{new_device_id}' auto-registered as PENDING approval.")

    # Test Admin Approval via API
    with TestClient(app) as client:
        # Login as admin
        login_res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Approve device
        approve_res = client.post(f"/api/devices/{new_device_id}/approve", headers=headers)
        assert approve_res.status_code == 200
        approved = approve_res.json()
        assert approved["approval_status"] == "approved"
        assert approved["status"] == "online"
        print(f"✓ Admin approved device #{new_device_id}. Status transitioned to ONLINE.")

        # Test Health Endpoint
        health_res = client.get(f"/api/devices/{new_device_id}/health", headers=headers)
        assert health_res.status_code == 200
        health = health_res.json()
        assert health["is_healthy"] is True
        assert health["status"] == "online"
        assert health["approval_status"] == "approved"
        assert health["latest_telemetry"] is not None
        print(f"✓ GET /api/devices/{new_device_id}/health verified (is_healthy=True).")

    db.close()


def test_offline_checker():
    print("\n--- [Test 3] Background Offline Checker ---")
    db = SessionLocal()
    stale_id = f"stale-dev-{int(time.time())}"

    # Create an approved online device with old timestamp
    stale_device = crud.create_device(
        db=db,
        device_id=stale_id,
        name="Stale Device",
        device_type="environment",
        status="online",
        approval_status="approved"
    )
    # Set last_seen to 45 seconds ago
    stale_device.last_seen = datetime.utcnow() - timedelta(seconds=45)
    db.commit()

    # Run offline check
    offline_marked = telemetry_handler.check_offline_devices(timeout_sec=30)
    assert stale_id in offline_marked

    # Verify status changed to offline
    db.expire_all()
    updated = crud.get_device_by_id(db, stale_id)
    assert updated.status == "offline"
    print(f"✓ Offline checker marked stale device '{stale_id}' as OFFLINE after 30s timeout.")
    db.close()


def test_integration_telemetry_to_event():
    print("\n--- [Test 4] Full Integration: Telemetry -> DB -> Environment Plugin -> Event ---")
    db = SessionLocal()
    dev_id = "env-sensor-01"  # Default seeded approved device

    # 1. Start an Environment Monitoring Task
    task_config = {
        "gas_threshold": 400.0,
        "temp_threshold": 32.0,
        "cooldown_seconds": 1.0
    }
    task = crud.create_task(
        db=db,
        plugin_name="environment_monitoring",
        target_source=dev_id,
        config=task_config,
        status="running"
    )
    task_manager.start_task(
        task_id=task.id,
        plugin_name="environment_monitoring",
        target_source=dev_id,
        config=task_config
    )
    print(f"✓ Environment monitoring task #{task.id} started.")

    # 2. Ingest Normal Telemetry (no alert)
    normal_payload = {
        "device_id": dev_id,
        "temperature": 24.5,
        "humidity": 55.0,
        "gas_level": 120.0,
        "motion": False,
        "timestamp": datetime.utcnow().isoformat()
    }
    res = telemetry_handler.handle_raw_telemetry(json.dumps(normal_payload).encode("utf-8"))
    assert res is not None

    # Verify telemetry stored in DB
    latest_telem = crud.get_latest_telemetry(db, dev_id)
    assert latest_telem is not None
    assert latest_telem.gas_level == 120.0
    print(f"✓ Normal telemetry recorded in SQLite: Gas={latest_telem.gas_level}ppm")

    # 3. Ingest Critical Hazardous Spike Telemetry (Gas > 400.0 ppm, Temp > 32.0 °C)
    spike_payload = {
        "device_id": dev_id,
        "temperature": 39.5,   # Critical temperature spike (> 32)
        "humidity": 65.0,
        "gas_level": 620.0,    # Hazardous gas leak (> 400)
        "motion": True,
        "timestamp": datetime.utcnow().isoformat()
    }
    res_spike = telemetry_handler.handle_raw_telemetry(json.dumps(spike_payload).encode("utf-8"))
    assert res_spike is not None
    print("✓ Hazardous spike telemetry ingested.")

    # 4. Check for generated events in database
    time.sleep(0.5)
    events = crud.get_events(db, source="environment_monitoring", limit=10)
    assert len(events) >= 1, "Expected environment alert event generated in DB!"

    # Find the gas leak or temperature event
    gas_events = [e for e in events if e.event_type == "gas_leak_risk"]
    assert len(gas_events) >= 1, "Expected 'gas_leak_risk' event in DB!"
    event = gas_events[0]

    # Verify Strict Rules
    assert event.status == "pending_review", "Strict Rule: AI and automated detections MUST have status 'pending_review'!"
    assert event.severity == "critical"
    assert event.metrics["gas_level"] == 620.0
    print(f"✓ Critical incident event generated in DB:")
    print(f"  - Event ID   : #{event.id}")
    print(f"  - Event Type : {event.event_type}")
    print(f"  - Severity   : {event.severity}")
    print(f"  - Status     : {event.status} (Human-in-the-loop pending review verified)")
    print(f"  - Description: {event.description}")

    # Stop task cleanly
    task_manager.stop_task(task.id)
    crud.update_task_status(db, task.id, "stopped")
    db.close()
    print("✓ Environment task cleanly stopped.")


if __name__ == "__main__":
    print("=" * 65)
    print("OMNISENSE AI - PHASE 3 TEST SUITE")
    print("=" * 65)
    test_telemetry_schema_validation()
    test_auto_registration_and_approval()
    test_offline_checker()
    test_integration_telemetry_to_event()
    print("\n" + "=" * 65)
    print("ALL PHASE 3 TESTS PASSED! ✓")
    print("=" * 65)
