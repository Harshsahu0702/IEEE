from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database import crud
from backend.database.models import User, Event
from backend.api.auth import get_current_user

router = APIRouter(prefix="/events", tags=["Events & Alerts"])


# ==========================================
# Schemas
# ==========================================

class EventResponse(BaseModel):
    id: int
    event_type: str
    source: str
    confidence: float
    severity: str
    description: str
    evidence_screenshot_path: Optional[str]
    metrics: Dict[str, Any]
    status: str
    reviewer_notes: Optional[str]
    reviewed_at: Optional[Any]
    created_at: Any

    class Config:
        from_attributes = True


class EventReviewRequest(BaseModel):
    status: str = Field(..., pattern="^(confirmed|false_positive|resolved)$")
    reviewer_notes: Optional[str] = None


# ==========================================
# Endpoints
# ==========================================

@router.get("", response_model=List[EventResponse])
def list_events(
    status: Optional[str] = Query(None, description="Filter by status: pending_review, confirmed, false_positive, resolved"),
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high, critical"),
    source: Optional[str] = Query(None, description="Filter by source plugin"),
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve detected events.
    Strict Rule: All AI detections default to 'pending_review' and must be inspected.
    """
    return crud.get_events(
        db=db,
        status=status,
        severity=severity,
        source=source,
        skip=skip,
        limit=limit
    )


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get single event details with evidence screenshot path and metrics."""
    event = crud.get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}/review", response_model=EventResponse)
def review_event(
    event_id: int,
    req: EventReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Operator review endpoint: Mark an event as confirmed, false_positive, or resolved.
    Enforces human-in-the-loop oversight.
    """
    event = crud.get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    updated = crud.review_event(
        db=db,
        event_id=event_id,
        status=req.status,
        reviewer_notes=req.reviewer_notes
    )
    return updated
