from datetime import datetime, date
from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database.connection import get_db
from backend.database import crud
from backend.database.models import User, MonitoringTask, Device, Event
from backend.api.auth import get_current_user

router = APIRouter(prefix="/overview", tags=["Overview Dashboard"])


@router.get("/stats")
def get_overview_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Aggregated real-time metrics for the Security Operations overview cards."""
    # Active tasks
    active_tasks = db.query(MonitoringTask).filter(MonitoringTask.status == "running").all()

    # Devices
    all_devices = db.query(Device).all()
    devices_online = sum(1 for d in all_devices if d.status == "online")
    devices_pending = sum(1 for d in all_devices if getattr(d, "approval_status", "approved") == "pending")

    # Events
    open_events = db.query(Event).filter(Event.status == "pending_review").count()

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_alerts = db.query(Event).filter(Event.created_at >= today_start).count()

    # Recent 6 events
    recent_events = (
        db.query(Event)
        .order_by(Event.created_at.desc())
        .limit(6)
        .all()
    )

    # System Status logic
    if any(e.severity == "critical" and e.status == "pending_review" for e in recent_events):
        system_status = "hazard_alert"
    elif open_events > 0:
        system_status = "elevated"
    else:
        system_status = "operational"

    return {
        "active_tasks_count": len(active_tasks),
        "devices_online": devices_online,
        "devices_online_count": devices_online,
        "devices_pending": devices_pending,
        "total_devices": len(all_devices),
        "open_events": open_events,
        "open_events_count": open_events,
        "today_alerts": today_alerts,
        "system_status": system_status,
        "recent_events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "source": e.source,
                "confidence": e.confidence,
                "severity": e.severity,
                "description": e.description,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "evidence_path": e.evidence_screenshot_path
            }
            for e in recent_events
        ],
        "active_tasks": [
            {
                "id": t.id,
                "plugin_name": t.plugin_name,
                "target_source": t.target_source,
                "status": t.status,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "config": t.config
            }
            for t in active_tasks
        ]
    }
