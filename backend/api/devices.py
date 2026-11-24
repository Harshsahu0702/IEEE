from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database import crud
from backend.database.models import User, Device
from backend.api.auth import get_current_user
from backend.monitoring.runner import task_manager
from backend.iot.telemetry import telemetry_handler

router = APIRouter(prefix="/devices", tags=["IoT Devices"])


# ==========================================
# Schemas
# ==========================================

class DeviceCreateRequest(BaseModel):
    device_id: str
    name: str
    device_type: str  # "environment", "camera", "multisensor"
    location: str = "Main Zone"
    config: Dict[str, Any] = {}


class DeviceResponse(BaseModel):
    id: int
    device_id: str
    name: str
    device_type: str
    location: str
    status: str
    approval_status: Optional[str] = "pending"
    last_seen: Optional[Any]
    config: Dict[str, Any]
    created_at: Any

    class Config:
        from_attributes = True


class DeviceHealthResponse(BaseModel):
    device_id: str
    name: str
    device_type: str
    status: str
    approval_status: str
    is_healthy: bool
    last_seen: Optional[Any]
    seconds_since_last_seen: Optional[float]
    latest_telemetry: Optional[Dict[str, Any]]


class TelemetryResponse(BaseModel):
    id: int
    device_id: str
    temperature: Optional[float]
    humidity: Optional[float]
    gas_level: Optional[float]
    motion: Optional[bool]
    timestamp: Any

    class Config:
        from_attributes = True


class TelemetryCreateRequest(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    gas_level: Optional[float] = None
    motion: Optional[bool] = None
    raw_payload: Optional[Dict[str, Any]] = None


# ==========================================
# Endpoints
# ==========================================

@router.get("", response_model=List[DeviceResponse])
def list_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve all registered IoT devices."""
    return crud.get_devices(db)


@router.post("", response_model=DeviceResponse)
def register_device(
    req: DeviceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Register a new device or physical sensor."""
    existing = crud.get_device_by_id(db, req.device_id)
    if existing:
        raise HTTPException(status_code=400, detail="Device with this ID already registered")

    # If created by admin, pre-approve it; otherwise pending
    initial_approval = "approved" if current_user.role == "admin" else "pending"
    initial_status = "offline"

    return crud.create_device(
        db=db,
        device_id=req.device_id,
        name=req.name,
        device_type=req.device_type,
        location=req.location,
        status=initial_status,
        approval_status=initial_approval,
        config=req.config
    )


# ==========================================
# Real-Time Threat Alarm Sync (Arduino Wi-Fi & USB)
# ==========================================

GLOBAL_ALARM_STATE: Dict[str, Any] = {
    "alarm_active": False,
    "threat_type": "none",
    "description": "Standby - All secure",
    "timestamp": 0.0
}


def set_global_alarm(active: bool, threat_type: str = "none", description: str = ""):
    GLOBAL_ALARM_STATE["alarm_active"] = active
    GLOBAL_ALARM_STATE["threat_type"] = threat_type
    GLOBAL_ALARM_STATE["description"] = description
    GLOBAL_ALARM_STATE["timestamp"] = datetime.utcnow().timestamp()


class AlarmControlRequest(BaseModel):
    alarm_active: bool
    threat_type: Optional[str] = "manual"
    description: Optional[str] = "Operator trigger"


@router.get("/alarm")
def get_global_alarm():
    """
    Polled by Wi-Fi Arduino or local USB bridge to control Red Alert LED.
    Zero auth required so low-power IoT microcontrollers can read it in 1 GET request.
    """
    return GLOBAL_ALARM_STATE


@router.post("/alarm")
def update_global_alarm(req: AlarmControlRequest):
    """Trigger or silence alarm globally across Arduino hardware and dashboard."""
    set_global_alarm(req.alarm_active, req.threat_type or "manual", req.description or "")
    return GLOBAL_ALARM_STATE


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get device specifications and current health status."""
    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("/{device_id}/health", response_model=DeviceHealthResponse)
def get_device_health(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns live health diagnostics, ping staleness, and latest telemetry for a device.
    """
    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    now = datetime.utcnow()
    sec_since = (now - device.last_seen).total_seconds() if device.last_seen else None
    # Healthy if online, approved, and last seen within 30 seconds
    is_healthy = bool(
        device.approval_status == "approved"
        and device.status == "online"
        and sec_since is not None
        and sec_since <= 30.0
    )

    latest = crud.get_latest_telemetry(db, device_id)
    latest_dict = None
    if latest:
        latest_dict = {
            "temperature": latest.temperature,
            "humidity": latest.humidity,
            "gas_level": latest.gas_level,
            "motion": latest.motion,
            "timestamp": latest.timestamp.isoformat() if latest.timestamp else None
        }

    return {
        "device_id": device.device_id,
        "name": device.name,
        "device_type": device.device_type,
        "status": device.status,
        "approval_status": getattr(device, "approval_status", "approved"),
        "is_healthy": is_healthy,
        "last_seen": device.last_seen,
        "seconds_since_last_seen": round(sec_since, 1) if sec_since is not None else None,
        "latest_telemetry": latest_dict
    }


@router.post("/{device_id}/approve", response_model=DeviceResponse)
def approve_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Admin Only: Approve an untrusted or pending IoT device.
    Transitions device from 'pending' to 'approved' and marks it 'online'.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative authorization required to approve new hardware devices."
        )

    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    approved_device = crud.approve_device(db, device_id)
    return approved_device


@router.get("/{device_id}/telemetry", response_model=List[TelemetryResponse])
def get_device_telemetry(
    device_id: str,
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve recent time-series telemetry data for a device."""
    device = crud.get_device_by_id(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return crud.get_telemetry_history(db, device_id, limit=limit)


@router.post("/{device_id}/telemetry", response_model=TelemetryResponse)
def ingest_telemetry_manual(
    device_id: str,
    req: TelemetryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manual/HTTP telemetry ingestion endpoint. Routes through TelemetryHandler."""
    payload_dict = {
        "device_id": device_id,
        "temperature": req.temperature,
        "humidity": req.humidity,
        "gas_level": req.gas_level,
        "motion": req.motion,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Pass through strict telemetry handler
    raw_bytes = bytes(str(payload_dict).replace("'", '"'), "utf-8")
    processed = telemetry_handler.handle_raw_telemetry(raw_bytes, topic=f"omnisense/devices/{device_id}/telemetry")
    if not processed:
        raise HTTPException(status_code=400, detail="Invalid telemetry payload format")

    latest = crud.get_latest_telemetry(db, device_id)
    return latest
