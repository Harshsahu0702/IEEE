import os
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

client = TestClient(app)

def test_phase5_integration():
    print("\n--- Running Phase 5 Integration Tests ---")

    # 1. Login as Admin
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✓ Auth & JWT generation verified")

    # 2. Test Overview Stats endpoint
    stats_resp = client.get("/api/overview/stats", headers=headers)
    assert stats_resp.status_code == 200, f"Overview stats failed: {stats_resp.text}"
    stats = stats_resp.json()
    assert "active_tasks_count" in stats
    assert "devices_online" in stats
    assert "open_events" in stats
    assert "system_status" in stats
    print(f"✓ Overview stats verified: {stats}")

    # 3. Test Video Stream with Query Token
    stream_resp = client.get(f"/api/video/stream?token={token}&max_frames=1")
    assert stream_resp.status_code == 200, f"Stream query token auth failed: {stream_resp.status_code}"
    assert "multipart/x-mixed-replace" in stream_resp.headers.get("content-type", "")
    print("✓ Video stream with query token auth verified")

    # 4. Test Evidence Static File Serving
    evidence_dir = Path(settings.EVIDENCE_DIR)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    test_evidence_file = evidence_dir / "test_snapshot.jpg"
    test_evidence_file.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C")
    evidence_resp = client.get("/evidence/test_snapshot.jpg")
    assert evidence_resp.status_code == 200, f"Static evidence serving failed: {evidence_resp.status_code}"
    print("✓ Evidence static file serving verified (/evidence/test_snapshot.jpg)")

    # 5. Test Event Review Flow
    # Create an event candidate if none exist
    from backend.database.connection import SessionLocal
    from backend.database import crud
    from backend.database.models import Event

    db = SessionLocal()
    try:
        events = crud.get_events(db, limit=1)
        if not events:
            evt = Event(
                event_type="test_incident",
                source="test_pipeline",
                confidence=0.92,
                severity="high",
                description="Test incident for review verification",
                metrics={"test_metric": 42},
                status="pending_review"
            )
            db.add(evt)
            db.commit()
            db.refresh(evt)
            event_id = evt.id
        else:
            event_id = events[0].id
    finally:
        db.close()

    # Operator review action
    review_resp = client.patch(
        f"/api/events/{event_id}/review",
        json={"status": "confirmed", "reviewer_notes": "Verified by automated Phase 5 operator check"},
        headers=headers
    )
    assert review_resp.status_code == 200, f"Event review failed: {review_resp.text}"
    reviewed_event = review_resp.json()
    assert reviewed_event["status"] == "confirmed"
    assert "Verified by automated Phase 5" in (reviewed_event["reviewer_notes"] or "")
    print(f"✓ Event review workflow verified for Event #{event_id}")

    # 6. Test Audit Logs endpoint (Admin only)
    audit_resp = client.get("/api/agent/audit-logs", headers=headers)
    assert audit_resp.status_code == 200, f"Audit logs failed: {audit_resp.text}"
    logs = audit_resp.json()
    assert isinstance(logs, list)
    print(f"✓ Audit logs endpoint verified ({len(logs)} records retrieved)")

    print("\n>>> ALL PHASE 5 INTEGRATION CHECKS PASSED SUCCESSFULLY! <<<\n")

if __name__ == "__main__":
    test_phase5_integration()
