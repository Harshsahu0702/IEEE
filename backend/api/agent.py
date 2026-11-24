from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database import crud
from backend.database.models import User, AgentPlan
from backend.api.auth import get_current_user
from backend.monitoring import universal_runner
from backend.agents.master_agent import master_agent
from backend.agents.schemas import CommandResponse, PlanExplanation
from backend.agents.scheduler import duration_scheduler
from backend.api.limiter import rate_limit_agent


router = APIRouter(prefix="/agent", tags=["AI Agent"])


# ==========================================
# Schemas
# ==========================================

class CommandRequest(BaseModel):
    command: str = Field(..., example="Monitor this camera for crowd density limit 5 people for 30 minutes")


class AgentPlanResponse(BaseModel):
    id: int
    natural_command: str
    intent: str
    domain: str
    modules: List[str]
    source: str
    rules: Dict[str, Any]
    status: str
    raw_response: Optional[str] = None
    created_at: Any
    approved_at: Optional[Any] = None

    class Config:
        from_attributes = True


class PlanApprovalRequest(BaseModel):
    approved: bool = True
    comment: Optional[str] = None


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int]
    command: str
    decision: str
    safety_notes: Optional[str]
    details: Dict[str, Any]
    timestamp: Any

    class Config:
        from_attributes = True


# ==========================================
# Endpoints
# ==========================================

@router.post("/command", response_model=CommandResponse, dependencies=[Depends(rate_limit_agent)])
def handle_agent_command(
    req: CommandRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Parses a natural-language command with Gemini LLM / Fallback parser.
    Enforces ethical safety policy (blocking facial recognition/injections).
    Returns strict JSON plan + explanation ('what I understood', 'why', confidence).
    Strict Rule: Plan requires explicit user approval before execution.
    """
    return master_agent.process_command(
        command=req.command,
        user_id=current_user.id,
        db=db
    )


@router.get("/plans", response_model=List[AgentPlanResponse])
def list_plans(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List recent agent plans with approval statuses."""
    return crud.get_plans(db, skip=skip, limit=limit)


@router.post("/plans/{plan_id}/approve", response_model=AgentPlanResponse)
def approve_plan(
    plan_id: int,
    req: PlanApprovalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Plan approval gate: User confirms or rejects the agent's plan.
    Supports start_monitoring, switch_monitoring (stops active, starts new),
    and stop_monitoring intents. Also schedules auto-stop if duration_minutes is set.
    """
    plan = crud.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    new_status = "approved" if req.approved else "rejected"
    updated_plan = crud.update_plan_status(db, plan_id, new_status)

    if req.approved:
        # Handle switch_monitoring: stop existing tasks first
        if plan.intent == "switch_monitoring":
            active_tasks = [t for t in crud.get_tasks(db) if t.status == "running"]
            for active in active_tasks:
                universal_runner.stop_universal_task(active.id)
                crud.update_task_status(db, active.id, "stopped", error_message="Stopped via switch_monitoring plan.")

        # Handle stop_monitoring
        if plan.intent == "stop_monitoring":
            active_tasks = [t for t in crud.get_tasks(db) if t.status == "running"]
            for active in active_tasks:
                universal_runner.stop_universal_task(active.id)
                crud.update_task_status(db, active.id, "stopped", error_message="Stopped by approved operator plan.")
            return updated_plan

        # Start universal monitoring task with the operator's natural language command as goal
        duration_minutes = (plan.rules or {}).get("duration_minutes")
        user_goal = plan.natural_command  # Pass the original command as the monitoring goal

        task_config = {
            **(plan.rules or {}),
            "user_goal": user_goal,
        }
        task = crud.create_task(
            db=db,
            plugin_name="universal_vlm_monitor",
            target_source=plan.source,
            config=task_config,
            plan_id=plan.id,
            status="running",
        )
        # Launch Universal VLM Monitor runner
        universal_runner.start_universal_task(
            task_id=task.id,
            user_goal=user_goal,
            config=task_config,
        )

        # Schedule auto-stop if duration was specified
        if duration_minutes and int(duration_minutes) > 0:
            duration_scheduler.schedule_auto_stop(task.id, int(duration_minutes))

    return updated_plan


@router.get("/audit-logs", response_model=List[AuditLogResponse])
def get_audit_trail(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve immutable audit log history for compliance and safety audit."""
    return crud.get_audit_logs(db, limit=limit)
