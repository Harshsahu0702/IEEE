"""
Universal Monitoring Tasks API.

Replaces the old plugin_name-based task API with a goal-based API.
When an operator approves a plan, the backend:
  1. Creates a MonitoringTask record (goal stored in config["user_goal"]).
  2. Launches a UniversalMonitorRunner for that task.
  3. The runner uses Motion Filter + VLM Reasoner to monitor the scene.

Backward-compatible: old plugin_name tasks still work via legacy task_manager.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database import crud
from backend.database.models import User
from backend.api.auth import get_current_user
from backend.monitoring import universal_runner

router = APIRouter(prefix="/tasks", tags=["Monitoring Tasks"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class UniversalTaskCreateRequest(BaseModel):
    """Create a new universal monitoring task with a natural language goal."""
    user_goal: str                          # e.g. "Watch for cheating in exam"
    target_source: str = "webcam_0"
    plan_id: Optional[int] = None
    config: Dict[str, Any] = {}


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[TaskResponse])
def list_tasks(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all monitoring tasks."""
    return crud.get_tasks(db, skip=skip, limit=limit)


@router.post("", response_model=TaskResponse)
def create_universal_task(
    req: UniversalTaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create and immediately start a Universal Monitoring task.
    The task monitors ANY scenario described by user_goal in natural language.
    """
    task_config = {
        **req.config,
        "user_goal": req.user_goal,
    }

    task = crud.create_task(
        db=db,
        plugin_name="universal_vlm_monitor",
        target_source=req.target_source,
        config=task_config,
        plan_id=req.plan_id,
        status="running",
    )

    universal_runner.start_universal_task(
        task_id=task.id,
        user_goal=req.user_goal,
        config=task_config,
    )

    return task


@router.post("/{task_id}/start", response_model=TaskResponse)
def start_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start or resume a monitoring task."""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    user_goal = task.config.get("user_goal", "Monitor the scene for any anomaly")
    updated = crud.update_task_status(db, task_id, "running")

    universal_runner.start_universal_task(
        task_id=task.id,
        user_goal=user_goal,
        config=task.config or {},
    )

    return updated


@router.post("/{task_id}/stop", response_model=TaskResponse)
def stop_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stop an active monitoring task."""
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    universal_runner.stop_universal_task(task_id)
    return crud.update_task_status(db, task_id, "stopped")
