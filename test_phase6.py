import os
import sys
import time
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import cv2
from fastapi.testclient import TestClient

from backend.main import app
from backend.monitoring.registry import get_plugin
from backend.monitoring.base import DetectionBox
from backend.monitoring.cleanup import cleanup_expired_evidence

client = TestClient(app)


def test_phase6():
    print("\n=============================================================")
    print("      OMNISENSE AI — PHASE 6 INTEGRATION VERIFICATION")
    print("=============================================================")

    # 1. Login & Token
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    user_data = login_resp.json()["user"]
    assert user_data["is_default_password"] is True
    headers = {"Authorization": f"Bearer {token}"}
    print("✓ Login and default admin password warning flag verified")

    # 2. Test Security Intrusion Plugin
    print("\n--- Testing Security Monitoring Plugin ---")
    plugin = get_plugin("security_monitoring")
    assert plugin is not None, "security_monitoring plugin was not discovered!"

    config = {
        "zones": [
            {
                "name": "Restricted Sector 4",
                "polygon": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
            }
        ],
        "cooldown_seconds": 5.0
    }
    plugin.initialize(config)
    assert len(plugin.zones) == 1

    # Mock frame with an intruder detection inside zone
    frame = np.full((480, 640, 3), 50, dtype=np.uint8)
    # Inject a mock detection box at center (normalized ~0.5, 0.5)
    plugin.detector.detect = lambda f, conf_threshold=0.35, imgsz=320: [
        DetectionBox(x1=300, y1=200, x2=340, y2=280, confidence=0.94, class_id=0, class_name="person")
    ]

    res = plugin.process_frame(frame)
    assert res.metadata["intrusion_detected"] is True
    assert "Restricted Sector 4" in res.metadata["breached_zones"]
    assert res.density_level == "high"

    events = plugin.generate_events()
    assert len(events) == 1
    evt = events[0]
    assert evt.event_type == "restricted_zone_intrusion"
    assert evt.severity == "critical"
    assert evt.evidence_path is not None
    assert Path(ROOT_DIR / evt.evidence_path.lstrip("/")).exists()
    print("✓ Security intrusion detection, zone spatial test, and evidence snapshot verified")

    # 3. Test Reports Generation (CSV & PDF)
    print("\n--- Testing Reports System ---")
    # CSV report
    csv_resp = client.post("/api/reports/generate", json={"format": "csv"}, headers=headers)
    assert csv_resp.status_code == 200, f"CSV generation failed: {csv_resp.text}"
    csv_data = csv_resp.json()
    assert csv_data["format"] == "csv"
    assert csv_data["file_size_bytes"] > 0
    print(f"✓ CSV report generated: {csv_data['filename']} ({csv_data['file_size_bytes']} bytes)")

    # PDF report
    pdf_resp = client.post("/api/reports/generate", json={"format": "pdf"}, headers=headers)
    assert pdf_resp.status_code == 200, f"PDF generation failed: {pdf_resp.text}"
    pdf_data = pdf_resp.json()
    assert pdf_data["format"] == "pdf"
    assert pdf_data["file_size_bytes"] > 0
    print(f"✓ PDF report generated: {pdf_data['filename']} ({pdf_data['file_size_bytes']} bytes)")

    # Download report
    dl_resp = client.get(f"/api/reports/{pdf_data['id']}/download")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"
    print("✓ Report download endpoint verified")

    # 4. Test Monitoring Profiles
    print("\n--- Testing Monitoring Profiles ---")
    profiles_resp = client.get("/api/profiles", headers=headers)
    assert profiles_resp.status_code == 200
    profiles = profiles_resp.json()
    assert len(profiles) >= 3
    profile_names = [p["name"] for p in profiles]
    assert "Crowd Safety Mode" in profile_names
    assert "Fire & Hazard Detection Mode" in profile_names
    assert "Restricted Area Mode" in profile_names
    print(f"✓ Built-in profiles discovered: {profile_names}")

    # Activate profile
    act_resp = client.post(f"/api/profiles/{profiles[0]['id']}/activate", headers=headers)
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert act_data["plan"]["status"] == "pending_approval"
    print(f"✓ Profile activation through Approval Gate verified (Plan #{act_data['plan_id']})")

    # 5. Test Data Retention Cleanup
    print("\n--- Testing Data Retention Cleanup ---")
    res_cleanup = cleanup_expired_evidence(retention_days=0)
    assert "deleted_files" in res_cleanup
    print(f"✓ Data retention cleanup verified (Purged {res_cleanup['deleted_files']} expired test snapshots)")

    print("\n=============================================================")
    print("        ALL PHASE 6 VERIFICATION CHECKS PASSED! ✓")
    print("=============================================================\n")


if __name__ == "__main__":
    test_phase6()
