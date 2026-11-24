"""
OmniSense AI - Phase 1 Verification Test Suite
Tests:
- Database connection and SQLite table schemas
- Database initialization and seed data
- User model, authentication, bcrypt hashing, and JWT tokens
- AgentPlan model, status transitions, and approval gate
- MonitoringTask model and status updates
- Device and Telemetry models
- Event model, 'pending_review' rule enforcement, and review updates
- FastAPI endpoints via TestClient
"""
import os
import sys
from pathlib import Path

# Set PYTHONPATH to include project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import Base, engine, SessionLocal
from backend.database.init_db import init_database
from backend.database import crud
from backend.database.models import User, AgentPlan, MonitoringTask, Device, DeviceTelemetry, Event


def run_tests():
    print("=" * 60)
    print("OMNISENSE AI - PHASE 1 VERIFICATION TEST")
    print("=" * 60)

    # 1. Initialize DB and Tables
    print("\n[Step 1] Initializing SQLite database and tables...")
    init_database()
    print("✓ Base.metadata.create_all successfully executed.")

    db = SessionLocal()
    try:
        # 2. Check Seed Data
        print("\n[Step 2] Verifying seed data...")
        admin = crud.get_user_by_username(db, "admin")
        assert admin is not None, "Admin user was not seeded!"
        assert admin.role == "admin", "Admin role mismatch!"
        print(f"✓ Default admin found: id={admin.id}, username='{admin.username}', role='{admin.role}'")

        cam = crud.get_device_by_id(db, "webcam_0")
        assert cam is not None, "Camera device was not seeded!"
        print(f"✓ Default camera found: device_id='{cam.device_id}', type='{cam.device_type}'")

        sensor = crud.get_device_by_id(db, "env-sensor-01")
        assert sensor is not None, "Environmental sensor was not seeded!"
        print(f"✓ Default sensor found: device_id='{sensor.device_id}', type='{sensor.device_type}'")

        # 3. Model CRUD Operations
        print("\n[Step 3] Testing database CRUD & business rules...")

        # Test AgentPlan creation
        plan = crud.create_plan(
            db=db,
            natural_command="Monitor this camera for crowd density",
            intent="monitor_crowd_density",
            domain="vision",
            modules=["crowd_monitoring", "yolov8n"],
            source="webcam_0",
            rules={"threshold": 4, "density_levels": {"low": 2, "medium": 5, "high": 8}},
            user_id=admin.id
        )
        assert plan.status == "pending_approval", "Strict rule violated: New plans must default to 'pending_approval'!"
        print(f"✓ Created AgentPlan (id={plan.id}): status='{plan.status}' (Approval Gate enforced)")

        # Test Plan Approval
        approved_plan = crud.update_plan_status(db, plan.id, "approved")
        assert approved_plan.status == "approved"
        assert approved_plan.approved_at is not None
        print(f"✓ Plan approved at {approved_plan.approved_at}")

        # Test Task Creation
        task = crud.create_task(
            db=db,
            plugin_name="crowd_monitoring",
            target_source="webcam_0",
            config=approved_plan.rules,
            plan_id=approved_plan.id,
            status="running"
        )
        assert task.status == "running"
        print(f"✓ MonitoringTask created: id={task.id}, plugin='{task.plugin_name}', status='{task.status}'")

        # Test Telemetry Ingestion
        telemetry = crud.create_telemetry(
            db=db,
            device_id="env-sensor-01",
            temperature=28.5,
            humidity=55.0,
            gas_level=120.0,
            motion=True
        )
        assert telemetry.id is not None
        assert telemetry.temperature == 28.5
        print(f"✓ Telemetry recorded: Temp={telemetry.temperature}°C, Gas={telemetry.gas_level}ppm")

        # Test Event Creation & Strict 'pending_review' rule
        event = crud.create_event(
            db=db,
            event_type="crowd_density_high",
            source="crowd_monitoring",
            description="Crowd count crossed threshold (6 > 4)",
            confidence=0.92,
            severity="high",
            evidence_screenshot_path="/evidence/crowd_alert_001.jpg",
            metrics={"count": 6, "threshold": 4, "density": "medium"}
        )
        assert event.status == "pending_review", "Strict rule violated: AI detections must start with 'pending_review'!"
        print(f"✓ Event created (id={event.id}): status='{event.status}', severity='{event.severity}'")

        # Review Event
        reviewed = crud.review_event(db, event.id, "confirmed", "Operator verified crowd gathering in lobby")
        assert reviewed.status == "confirmed"
        assert reviewed.reviewed_at is not None
        print(f"✓ Event reviewed: new_status='{reviewed.status}', notes='{reviewed.reviewer_notes}'")

    finally:
        db.close()

    # 4. Test API via FastAPI TestClient
    print("\n[Step 4] Testing FastAPI Endpoints via TestClient...")
    with TestClient(app) as client:
        # Health check
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"
        print("✓ GET /api/health returned 200 OK")

        # Auth: Login as admin
        res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert res.status_code == 200
        token_data = res.json()
        token = token_data["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print("✓ POST /api/auth/login successful, JWT token received")

        # Auth: Current user profile
        res = client.get("/api/auth/me", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["username"] == "admin"
        print("✓ GET /api/auth/me returned authenticated user")

        # Agent: Post command
        res = client.post(
            "/api/agent/command",
            headers=auth_headers,
            json={"command": "Monitor this camera for crowd density"}
        )
        assert res.status_code == 200
        plan_data = res.json()
        assert plan_data["status"] == "pending_approval"
        plan_id = plan_data["id"]
        print(f"✓ POST /api/agent/command generated plan id={plan_id} with status='pending_approval'")

        # Agent: Approve plan
        res = client.post(
            f"/api/agent/plans/{plan_id}/approve",
            headers=auth_headers,
            json={"approved": True, "comment": "Approved by security team"}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "approved"
        print(f"✓ POST /api/agent/plans/{plan_id}/approve changed status to 'approved'")

        # Devices list
        res = client.get("/api/devices", headers=auth_headers)
        assert res.status_code == 200
        devices = res.json()
        assert len(devices) >= 2
        print(f"✓ GET /api/devices returned {len(devices)} devices")

        # Events list
        res = client.get("/api/events", headers=auth_headers)
        assert res.status_code == 200
        events = res.json()
        assert len(events) >= 1
        print(f"✓ GET /api/events returned {len(events)} events")

    print("\n" + "=" * 60)
    print("ALL PHASE 1 TESTS PASSED SUCCESSFULLY! ✓")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
