from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from backend.database.models import (
    User,
    AgentPlan,
    MonitoringTask,
    Device,
    DeviceTelemetry,
    Event
)


# ==========================================
# User CRUD
# ==========================================

def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, username: str, email: str, hashed_password: str, role: str = "operator") -> User:
    user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ==========================================
# AgentPlan CRUD
# ==========================================

def create_plan(
    db: Session,
    natural_command: str,
    intent: str,
    domain: str,
    modules: List[str],
    source: str,
    rules: Dict[str, Any],
    raw_response: Optional[str] = None,
    user_id: Optional[int] = None
) -> AgentPlan:
    plan = AgentPlan(
        natural_command=natural_command,
        intent=intent,
        domain=domain,
        modules=modules,
        source=source,
        rules=rules,
        raw_response=raw_response,
        user_id=user_id,
        status="pending_approval"
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def get_plan(db: Session, plan_id: int) -> Optional[AgentPlan]:
    return db.query(AgentPlan).filter(AgentPlan.id == plan_id).first()


def get_plans(db: Session, skip: int = 0, limit: int = 50) -> List[AgentPlan]:
    return db.query(AgentPlan).order_by(AgentPlan.created_at.desc()).offset(skip).limit(limit).all()


def update_plan_status(db: Session, plan_id: int, status: str) -> Optional[AgentPlan]:
    plan = get_plan(db, plan_id)
    if plan:
        plan.status = status
        if status == "approved":
            plan.approved_at = datetime.utcnow()
        db.commit()
        db.refresh(plan)
    return plan


# ==========================================
# MonitoringTask CRUD
# ==========================================

def create_task(
    db: Session,
    plugin_name: str,
    target_source: str,
    config: Dict[str, Any],
    plan_id: Optional[int] = None,
    status: str = "running"
) -> MonitoringTask:
    task = MonitoringTask(
        plugin_name=plugin_name,
        target_source=target_source,
        config=config,
        plan_id=plan_id,
        status=status,
        started_at=datetime.utcnow() if status == "running" else None
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> Optional[MonitoringTask]:
    return db.query(MonitoringTask).filter(MonitoringTask.id == task_id).first()


def get_tasks(db: Session, skip: int = 0, limit: int = 50) -> List[MonitoringTask]:
    return db.query(MonitoringTask).order_by(MonitoringTask.created_at.desc()).offset(skip).limit(limit).all()


def update_task_status(
    db: Session,
    task_id: int,
    status: str,
    error_message: Optional[str] = None
) -> Optional[MonitoringTask]:
    task = get_task(db, task_id)
    if task:
        task.status = status
        if status == "running" and not task.started_at:
            task.started_at = datetime.utcnow()
        elif status in ["stopped", "failed"]:
            task.stopped_at = datetime.utcnow()
        if error_message:
            task.error_message = error_message
        db.commit()
        db.refresh(task)
    return task


# ==========================================
# Device & Telemetry CRUD
# ==========================================

def get_device_by_id(db: Session, device_id: str) -> Optional[Device]:
    return db.query(Device).filter(Device.device_id == device_id).first()


def get_devices(db: Session) -> List[Device]:
    return db.query(Device).order_by(Device.created_at.desc()).all()


def create_device(
    db: Session,
    device_id: str,
    name: str,
    device_type: str,
    location: str = "Main Zone",
    status: str = "pending",
    approval_status: str = "pending",
    config: Optional[Dict[str, Any]] = None
) -> Device:
    device = Device(
        device_id=device_id,
        name=name,
        device_type=device_type,
        location=location,
        status=status,
        approval_status=approval_status,
        config=config or {}
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def approve_device(db: Session, device_id: str) -> Optional[Device]:
    """Approve a pending device (admin only). Sets approval_status to 'approved' and status to 'online'."""
    device = get_device_by_id(db, device_id)
    if device:
        device.approval_status = "approved"
        device.status = "online"
        device.last_seen = datetime.utcnow()
        db.commit()
        db.refresh(device)
    return device


def update_device_status(db: Session, device_id: str, status: str, update_last_seen: bool = True) -> Optional[Device]:
    device = get_device_by_id(db, device_id)
    if device:
        device.status = status
        if update_last_seen:
            device.last_seen = datetime.utcnow()
        db.commit()
        db.refresh(device)
    return device


def create_telemetry(
    db: Session,
    device_id: str,
    temperature: Optional[float],
    humidity: Optional[float],
    gas_level: Optional[float],
    motion: Optional[bool],
    raw_payload: Optional[Dict[str, Any]] = None,
    timestamp: Optional[datetime] = None
) -> DeviceTelemetry:
    telemetry = DeviceTelemetry(
        device_id=device_id,
        temperature=temperature,
        humidity=humidity,
        gas_level=gas_level,
        motion=motion,
        raw_payload=raw_payload,
        timestamp=timestamp or datetime.utcnow()
    )
    db.add(telemetry)
    # Also update device last seen, and update status to online only if approved
    device = get_device_by_id(db, device_id)
    if device:
        device.last_seen = datetime.utcnow()
        if getattr(device, "approval_status", "approved") == "approved":
            device.status = "online"
    db.commit()
    db.refresh(telemetry)
    return telemetry


def get_latest_telemetry(db: Session, device_id: str) -> Optional[DeviceTelemetry]:
    return (
        db.query(DeviceTelemetry)
        .filter(DeviceTelemetry.device_id == device_id)
        .order_by(DeviceTelemetry.timestamp.desc())
        .first()
    )


def get_telemetry_history(db: Session, device_id: str, limit: int = 50) -> List[DeviceTelemetry]:
    return (
        db.query(DeviceTelemetry)
        .filter(DeviceTelemetry.device_id == device_id)
        .order_by(DeviceTelemetry.timestamp.desc())
        .limit(limit)
        .all()
    )


# ==========================================
# Event CRUD
# ==========================================

def create_event(
    db: Session,
    event_type: str,
    source: str,
    description: str,
    confidence: float = 0.0,
    severity: str = "medium",
    evidence_screenshot_path: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None
) -> Event:
    """Creates a new event. Notice initial status is strictly 'pending_review'."""
    event = Event(
        event_type=event_type,
        source=source,
        description=description,
        confidence=confidence,
        severity=severity,
        evidence_screenshot_path=evidence_screenshot_path,
        metrics=metrics or {},
        status="pending_review"  # Rule: AI detections are never treated as confirmed automatically
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_events(
    db: Session,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    source: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
) -> List[Event]:
    query = db.query(Event)
    if status:
        query = query.filter(Event.status == status)
    if severity:
        query = query.filter(Event.severity == severity)
    if source:
        query = query.filter(Event.source == source)
    return query.order_by(Event.created_at.desc()).offset(skip).limit(limit).all()


def get_event_by_id(db: Session, event_id: int) -> Optional[Event]:
    return db.query(Event).filter(Event.id == event_id).first()


def review_event(
    db: Session,
    event_id: int,
    status: str,  # "confirmed", "false_positive", "resolved"
    reviewer_notes: Optional[str] = None
) -> Optional[Event]:
    event = get_event_by_id(db, event_id)
    if event:
        event.status = status
        event.reviewer_notes = reviewer_notes
        event.reviewed_at = datetime.utcnow()
        db.commit()
        db.refresh(event)
    return event


# ==========================================
# AuditLog CRUD
# ==========================================

def create_audit_log(
    db: Session,
    command: str,
    decision: str,
    user_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    safety_notes: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Any:
    from backend.database.models import AuditLog
    log = AuditLog(
        command=command,
        decision=decision,
        user_id=user_id,
        plan_id=plan_id,
        safety_notes=safety_notes,
        details=details or {}
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_audit_logs(db: Session, limit: int = 50) -> List[Any]:
    from backend.database.models import AuditLog
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()

