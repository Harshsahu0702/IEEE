import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, ReportRecord
from backend.api.auth import get_current_user
from backend.reports.generator import ReportGenerator

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])


class ReportGenerateRequest(BaseModel):
    format: str = Field("pdf", pattern="^(pdf|csv)$")
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ReportResponse(BaseModel):
    id: int
    report_id: str
    format: str
    filename: str
    file_size_bytes: int
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    summary_metrics: Dict[str, Any]
    created_at: datetime
    download_url: str

    class Config:
        from_attributes = True


@router.post("/generate", response_model=ReportResponse)
def generate_report(
    req: ReportGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generates an operational PDF or CSV report filtered by optional date range."""
    start_dt = None
    end_dt = None

    if req.start_date:
        try:
            start_dt = datetime.fromisoformat(req.start_date.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start_date ISO format")

    if req.end_date:
        try:
            end_dt = datetime.fromisoformat(req.end_date.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid end_date ISO format")

    try:
        record = ReportGenerator.generate(
            db=db,
            format_type=req.format,
            start_date=start_dt,
            end_date=end_dt
        )
        return ReportResponse(
            id=record.id,
            report_id=record.report_id,
            format=record.format,
            filename=record.filename,
            file_size_bytes=record.file_size_bytes,
            start_date=record.start_date,
            end_date=record.end_date,
            summary_metrics=record.summary_metrics,
            created_at=record.created_at,
            download_url=f"/api/reports/{record.id}/download"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("", response_model=List[ReportResponse])
def list_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List historical generated compliance and audit reports."""
    records = db.query(ReportRecord).order_by(ReportRecord.created_at.desc()).limit(50).all()
    res = []
    for r in records:
        res.append(ReportResponse(
            id=r.id,
            report_id=r.report_id,
            format=r.format,
            filename=r.filename,
            file_size_bytes=r.file_size_bytes,
            start_date=r.start_date,
            end_date=r.end_date,
            summary_metrics=r.summary_metrics,
            created_at=r.created_at,
            download_url=f"/api/reports/{r.id}/download"
        ))
    return res


@router.get("/{report_id}/download")
def download_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Download a generated PDF or CSV report file."""
    record = db.query(ReportRecord).filter(ReportRecord.id == report_id).first()
    if not record or not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Report file not found")

    media_type = "application/pdf" if record.format == "pdf" else "text/csv"
    return FileResponse(
        path=record.file_path,
        filename=record.filename,
        media_type=media_type
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a report record and underlying file."""
    record = db.query(ReportRecord).filter(ReportRecord.id == report_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Report not found")

    if os.path.exists(record.file_path):
        try:
            os.remove(record.file_path)
        except Exception:
            pass

    db.delete(record)
    db.commit()
    return None
