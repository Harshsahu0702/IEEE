import os
import csv
import io
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database.models import Event, Device, MonitoringTask, ReportRecord
from backend.config import settings

logger = logging.getLogger(__name__)

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


class ReportGenerator:
    """
    Generates formal SOC analytical and compliance reports in PDF and CSV format.
    Covers:
    - Incident event distribution by type, severity, and review outcome
    - Device health, connectivity status, and telemetry volume
    - Historical operator review decisions
    - Strict privacy assurance declaration
    """

    @classmethod
    def generate(
        cls,
        db: Session,
        format_type: str = "pdf",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> ReportRecord:
        format_type = format_type.lower()
        if format_type not in ["pdf", "csv"]:
            format_type = "pdf"

        report_id = f"REP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        # 1. Query Data
        query = db.query(Event)
        if start_date:
            query = query.filter(Event.created_at >= start_date)
        if end_date:
            query = query.filter(Event.created_at <= end_date)
        events: List[Event] = query.order_by(Event.created_at.desc()).all()

        devices: List[Device] = db.query(Device).all()
        tasks: List[MonitoringTask] = db.query(MonitoringTask).all()

        # 2. Compute Aggregates
        total_events = len(events)
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        by_status: Dict[str, int] = {"pending_review": 0, "confirmed": 0, "false_positive": 0, "resolved": 0}

        for e in events:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
            if e.severity in by_severity:
                by_severity[e.severity] += 1
            if e.status in by_status:
                by_status[e.status] += 1

        devices_online = sum(1 for d in devices if d.status == "online")
        devices_total = len(devices)

        summary_metrics = {
            "total_events": total_events,
            "by_type": by_type,
            "by_severity": by_severity,
            "by_status": by_status,
            "devices_online": devices_online,
            "devices_total": devices_total,
            "active_tasks": sum(1 for t in tasks if t.status == "running"),
            "generated_at": datetime.utcnow().isoformat()
        }

        # 3. Generate File
        filename = f"{report_id}.{format_type}"
        file_path = REPORTS_DIR / filename

        if format_type == "csv":
            cls._generate_csv(
                file_path=file_path,
                events=events,
                devices=devices,
                summary=summary_metrics,
                start_date=start_date,
                end_date=end_date
            )
        else:
            cls._generate_pdf(
                file_path=file_path,
                report_id=report_id,
                events=events,
                devices=devices,
                summary=summary_metrics,
                start_date=start_date,
                end_date=end_date
            )

        file_size = os.path.getsize(file_path)

        # 4. Save Record
        record = ReportRecord(
            report_id=report_id,
            format=format_type,
            filename=filename,
            file_path=str(file_path),
            file_size_bytes=file_size,
            start_date=start_date,
            end_date=end_date,
            summary_metrics=summary_metrics,
            created_at=datetime.utcnow()
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info(f"Generated report #{record.id} ({format_type.upper()}): {filename} ({file_size} bytes)")
        return record

    @classmethod
    def _generate_csv(
        cls,
        file_path: Path,
        events: List[Event],
        devices: List[Device],
        summary: Dict[str, Any],
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ):
        with open(file_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow(["OMNISENSE AI — OPERATIONAL INCIDENT & AUDIT REPORT"])
            writer.writerow(["Generated At", datetime.utcnow().isoformat() + " UTC"])
            writer.writerow(["Filter Range Start", start_date.isoformat() if start_date else "Beginning"])
            writer.writerow(["Filter Range End", end_date.isoformat() if end_date else "Current"])
            writer.writerow([])

            # Section 1: Executive Summary
            writer.writerow(["=== EXECUTIVE SUMMARY METRICS ==="])
            writer.writerow(["Metric", "Value"])
            writer.writerow(["Total Events Recorded", summary["total_events"]])
            writer.writerow(["Pending Review Alerts", summary["by_status"].get("pending_review", 0)])
            writer.writerow(["Confirmed Incidents", summary["by_status"].get("confirmed", 0)])
            writer.writerow(["False Positive Alarms", summary["by_status"].get("false_positive", 0)])
            writer.writerow(["Resolved Incidents", summary["by_status"].get("resolved", 0)])
            writer.writerow(["Critical Severity Count", summary["by_severity"].get("critical", 0)])
            writer.writerow(["High Severity Count", summary["by_severity"].get("high", 0)])
            writer.writerow(["Medium Severity Count", summary["by_severity"].get("medium", 0)])
            writer.writerow(["Low Severity Count", summary["by_severity"].get("low", 0)])
            writer.writerow(["Devices Online", f"{summary['devices_online']} / {summary['devices_total']}"])
            writer.writerow([])

            # Section 2: Detailed Events
            writer.writerow(["=== DETAILED INCIDENT LEDGER ==="])
            writer.writerow(["Event ID", "Timestamp", "Type", "Severity", "Source", "Confidence", "Status", "Description", "Reviewer Notes"])
            for e in events:
                writer.writerow([
                    e.id,
                    e.created_at.isoformat() if e.created_at else "",
                    e.event_type,
                    e.severity,
                    e.source,
                    f"{e.confidence:.2f}",
                    e.status,
                    e.description,
                    e.reviewer_notes or ""
                ])
            writer.writerow([])

            # Section 3: Devices
            writer.writerow(["=== CONNECTED IOT DEVICE INVENTORY ==="])
            writer.writerow(["Device ID", "Name", "Type", "Location", "Status", "Approval Status", "Last Seen"])
            for d in devices:
                writer.writerow([
                    d.device_id,
                    d.name,
                    d.device_type,
                    d.location,
                    d.status,
                    getattr(d, "approval_status", "approved"),
                    d.last_seen.isoformat() if d.last_seen else "Never"
                ])

    @classmethod
    def _generate_pdf(
        cls,
        file_path: Path,
        report_id: str,
        events: List[Event],
        devices: List[Device],
        summary: Dict[str, Any],
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ):
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor('#0f172a'),
            spaceAfter=6
        )
        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#64748b'),
            spaceAfter=12
        )
        h2_style = ParagraphStyle(
            'Heading2Custom',
            parent=styles['Heading2'],
            fontSize=13,
            leading=16,
            textColor=colors.HexColor('#1e293b'),
            spaceBefore=14,
            spaceAfter=8
        )
        body_style = ParagraphStyle(
            'BodyCustom',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor('#334155')
        )
        small_style = ParagraphStyle(
            'SmallCustom',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#475569')
        )

        elements = []

        # 1. Header
        elements.append(Paragraph("OmniSense AI — Security & Environmental Operations Report", title_style))
        date_str = f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC | Report ID: {report_id}"
        range_str = f"Filter Period: {start_date.strftime('%Y-%m-%d') if start_date else 'All History'} to {end_date.strftime('%Y-%m-%d') if end_date else 'Present'}"
        elements.append(Paragraph(f"{date_str} &bull; {range_str}", subtitle_style))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#6366f1'), spaceAfter=14))

        # 2. Executive Summary Metrics Table
        elements.append(Paragraph("1. Executive Incident & Fleet Summary", h2_style))

        summary_data = [
            ["Metric", "Value", "Metric", "Value"],
            ["Total Detected Events", str(summary["total_events"]), "Pending Operator Review", str(summary["by_status"].get("pending_review", 0))],
            ["Confirmed Incidents", str(summary["by_status"].get("confirmed", 0)), "False Positive Alarms", str(summary["by_status"].get("false_positive", 0))],
            ["Critical Severity Alerts", str(summary["by_severity"].get("critical", 0)), "High Severity Alerts", str(summary["by_severity"].get("high", 0))],
            ["Online IoT Devices", f"{summary['devices_online']} / {summary['devices_total']}", "Active Background Tasks", str(summary["active_tasks"])]
        ]

        t_summary = Table(summary_data, colWidths=[140, 130, 140, 130])
        t_summary.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_summary)
        elements.append(Spacer(1, 14))

        # 3. Incident Breakdown by Severity & Type
        elements.append(Paragraph("2. Event Distribution by Classification", h2_style))
        type_rows = [["Event Type", "Occurrences"]]
        for t_name, count in summary["by_type"].items():
            type_rows.append([t_name, str(count)])
        if len(type_rows) == 1:
            type_rows.append(["None recorded", "0"])

        t_types = Table(type_rows, colWidths=[350, 190])
        t_types.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_types)
        elements.append(Spacer(1, 14))

        # 4. Recent Incident Log (up to 20)
        elements.append(Paragraph(f"3. Recent Incidents Log (Showing up to 20 of {len(events)})", h2_style))
        event_headers = ["ID", "Timestamp", "Type", "Sev", "Conf", "Status", "Notes"]
        event_rows = [event_headers]

        for e in events[:20]:
            event_rows.append([
                str(e.id),
                e.created_at.strftime('%m-%d %H:%M') if e.created_at else "",
                Paragraph(e.event_type[:24], small_style),
                e.severity.upper()[:4],
                f"{e.confidence:.2f}",
                e.status.replace('_', ' ')[:12],
                Paragraph((e.reviewer_notes or e.description)[:40], small_style)
            ])

        if len(event_rows) == 1:
            event_rows.append(["-", "-", "No incident events found", "-", "-", "-", "-"])

        t_events = Table(event_rows, colWidths=[30, 70, 120, 45, 40, 75, 160])
        t_events.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_events)
        elements.append(Spacer(1, 14))

        # 5. Device Fleet Status
        elements.append(Paragraph("4. Edge Device Fleet Inventory", h2_style))
        dev_rows = [["Device ID", "Name", "Type", "Status", "Approval", "Last Seen"]]
        for d in devices:
            dev_rows.append([
                d.device_id,
                Paragraph(d.name[:30], small_style),
                d.device_type,
                d.status.upper(),
                getattr(d, "approval_status", "approved").upper(),
                d.last_seen.strftime('%Y-%m-%d %H:%M') if d.last_seen else "Never"
            ])

        t_devs = Table(dev_rows, colWidths=[90, 170, 70, 60, 60, 90])
        t_devs.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t_devs)
        elements.append(Spacer(1, 16))

        # 6. Privacy & Safety Declaration
        elements.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor('#cbd5e1'), spaceAfter=10))
        privacy_text = (
            "<b>OmniSense AI Compliance Declaration:</b> This system operates strictly under zero facial recognition "
            "and zero biometric identification policies. All vision detections are ephemeral bounding box classifications "
            "(COCO Class 0: person). All incident alert determinations are submitted through a mandatory human-in-the-loop "
            "review process and are never autonomously marked confirmed."
        )
        elements.append(Paragraph(privacy_text, small_style))

        # Build PDF
        doc.build(elements)
