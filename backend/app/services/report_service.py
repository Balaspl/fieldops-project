"""
report_service.py

Service layer for asynchronous report generation and PDF compilation.
Provides report generation utilities and re-exports Celery queue configurations.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any, Dict, List, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.celery_app import (
    REPORT_QUEUE,
    REPORT_ROUTING_KEY,
    REPORT_GENERATION_QUEUE,
    REPORT_GENERATION_ROUTING_KEY,
    get_report_generation_queue_config,
    create_report_generation_queue,
    CreateReportGenerationQueue,
    Create_report_generation_queue,
    CreateReportQueue,
    create_report_queue,
    Create_report_queue,
)

logger = logging.getLogger(__name__)


def render_summary_report_pdf(
    *,
    title: str,
    records: Optional[List[Dict[str, Any]]] = None,
    tenant_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Render a clean, authoritative PDF summary report using ReportLab.
    Reusable for job summary, audit export, or performance reporting.
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 54
    y = height - margin

    # Header title
    pdf.setFillColor(colors.HexColor("#0F172A"))
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margin, y, str(title))
    y -= 24

    # Tenant and metadata
    pdf.setFillColor(colors.HexColor("#64748B"))
    pdf.setFont("Helvetica", 9)
    tenant_label = f"Tenant: {tenant_id}" if tenant_id else "System Scope"
    pdf.drawString(margin, y, tenant_label)
    y -= 16

    # Horizontal divider line
    pdf.setStrokeColor(colors.HexColor("#CBD5E1"))
    pdf.setLineWidth(1)
    pdf.line(margin, y, width - margin, y)
    y -= 24

    # Body records
    if records:
        pdf.setFillColor(colors.HexColor("#1E293B"))
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin, y, "Report Records:")
        y -= 18

        pdf.setFont("Helvetica", 9)
        for i, rec in enumerate(records[:30]):
            rec_str = json.dumps(rec, default=str) if isinstance(rec, dict) else str(rec)
            if y < margin + 40:
                pdf.showPage()
                y = height - margin
                pdf.setFont("Helvetica", 9)
            pdf.drawString(margin + 12, y, f"• {rec_str[:90]}")
            y -= 15
    else:
        pdf.setFillColor(colors.HexColor("#475569"))
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.drawString(margin, y, "No record entries submitted for this report period.")
        y -= 20

    # Footer
    pdf.setFillColor(colors.HexColor("#94A3B8"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, 28, "FieldOps Platform - Automated Report Generation")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


__all__ = [
    "REPORT_QUEUE",
    "REPORT_ROUTING_KEY",
    "REPORT_GENERATION_QUEUE",
    "REPORT_GENERATION_ROUTING_KEY",
    "get_report_generation_queue_config",
    "create_report_generation_queue",
    "CreateReportGenerationQueue",
    "Create_report_generation_queue",
    "CreateReportQueue",
    "create_report_queue",
    "Create_report_queue",
    "render_summary_report_pdf",
]

