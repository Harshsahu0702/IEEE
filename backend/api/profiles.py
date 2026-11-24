from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, MonitoringProfile, AgentPlan
from backend.api.auth import get_current_user

router = APIRouter(prefix="/profiles", tags=["Monitoring Profiles"])


class ProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str
    domain: str = Field(..., pattern="^(vision|iot|multimodal)$")
    modules: List[str]
    source: str
    rules: Dict[str, Any]
    duration_minutes: Optional[int] = None


class ProfileResponse(BaseModel):
    id: int
    name: str
    description: str
    domain: str
    modules: List[str]
    source: str
    rules: Dict[str, Any]
    duration_minutes: Optional[int]
    is_builtin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ProfileActivationResponse(BaseModel):
    message: str
    profile_id: int
    profile_name: str
    plan_id: int
    plan: Dict[str, Any]


@router.get("", response_model=List[ProfileResponse])
def list_profiles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List available monitoring profiles (built-ins and user-defined presets)."""
    return db.query(MonitoringProfile).order_by(MonitoringProfile.is_builtin.desc(), MonitoringProfile.name).all()


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    req: ProfileCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save a custom reusable monitoring profile."""
    existing = db.query(MonitoringProfile).filter(MonitoringProfile.name == req.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Profile with name '{req.name}' already exists.")

    profile = MonitoringProfile(
        name=req.name,
        description=req.description,
        domain=req.domain,
        modules=req.modules,
        source=req.source,
        rules=req.rules,
        duration_minutes=req.duration_minutes,
        is_builtin=False,
        created_at=datetime.utcnow()
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/{profile_id}/activate", response_model=ProfileActivationResponse)
def activate_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    One-click profile activation: converts preset into an AgentPlan awaiting operator approval.
    Strict Rule: Activation still routes through the Plan Approval Gate.
    """
    profile = db.query(MonitoringProfile).filter(MonitoringProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    plan = AgentPlan(
        natural_command=f"Activate profile: {profile.name}",
        intent="start_monitoring",
        domain=profile.domain,
        modules=profile.modules,
        source=profile.source,
        rules=profile.rules,
        status="pending_approval",
        raw_response=f"Profile '{profile.name}' prepared for execution. Review configuration thresholds and click Approve to start.",
        user_id=current_user.id,
        created_at=datetime.utcnow()
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return ProfileActivationResponse(
        message=f"Profile '{profile.name}' staged. Operator approval required to launch background tasks.",
        profile_id=profile.id,
        profile_name=profile.name,
        plan_id=plan.id,
        plan={
            "id": plan.id,
            "intent": plan.intent,
            "domain": plan.domain,
            "modules": plan.modules,
            "source": plan.source,
            "rules": plan.rules,
            "status": plan.status,
            "raw_response": plan.raw_response
        }
    )


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a custom profile (built-in profiles cannot be deleted)."""
    profile = db.query(MonitoringProfile).filter(MonitoringProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot delete default built-in profile.")

    db.delete(profile)
    db.commit()
    return None
