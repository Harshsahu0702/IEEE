from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database import crud
from backend.database.models import User, MonitoringTask
from backend.api.auth import get_current_user
from backend.monitoring.runner import task_manager

router = APIRouter(prefix="/tasks", tags=["Monitoring Tasks"])


# ==========================================
# Schemas
# ==========================================

class TaskCreateRequest(BaseModel):
    plugin_name: str
    target_source: str
    config: Dict[str, Any] = {}
    plan_id: Optional[int] = None


class TaskResponse(BaseModel):
    id: int
    plan_id: Optional[int]
    plugin_name: str
    target_source: str
    status: str
    config: Dict[str, Any]
    error_message: Optional[str]
    started_at: Optional[Any]
    stopped_at: Optional[Any]
    created_at: Any

    class Config:
        from_attributes = True


# ==========================================
# Endpoints
# ==========================================

@router.get("", response_model=List[TaskResponse])
def list_tasks(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all monitoring tasks."""
    return crud.get_tasks(db, skip=skip, limit=limit)


@router.post("", response_model=TaskResponse)
def create_manual_task(
    req: TaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually register and start a monitoring task."""
    task = crud.create_task(
        db=db,
        plugin_name=req.plugin_name,
        target_source=req.target_source,
        config=req.config,
        plan_id=req.plan_id,
        status="running"
    )
    task_manager.start_task(
        task_id=task.id,
        plugin_name=task.plugin_name,
        target_source=task.target_source,
        config=task.config
    )
    return task


@router.post("/{task_id}/start", response_model=TaskResponse)
def start_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start or resume a monitoring task."""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updated = crud.update_task_status(db, task_id, "running")
    task_manager.start_task(
        task_id=task.id,
        plugin_name=task.plugin_name,
        target_source=task.target_source,
        config=task.config
    )
    return updated


@router.post("/{task_id}/stop", response_model=TaskResponse)
def stop_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stop an active monitoring task cleanly."""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task_manager.stop_task(task_id)
    return crud.update_task_status(db, task_id, "stopped")
