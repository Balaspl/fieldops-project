"""Shared backend-authoritative calculations for persisted job invoices."""

import math
from datetime import date, datetime
from io import BytesIO


def invoice_totals(subtotal_value) -> dict[str, float | str]:
    """Apply the existing FieldOps invoice contract to a persisted subtotal."""
    if subtotal_value is None:
        raise ValueError("Invoice subtotal is unavailable")
    try:
        subtotal = round(float(subtotal_value), 2)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Invoice subtotal is invalid") from exc
    if not math.isfinite(subtotal):
        raise ValueError("Invoice subtotal is invalid")

    gst_rate = 5.0
    gst_amount = round(subtotal * gst_rate / 100.0, 2)
    total_amount = round(subtotal + gst_amount, 2)
    if not math.isfinite(gst_amount) or not math.isfinite(total_amount):
        raise ValueError("Invoice total is invalid")

    return {
        "subtotal": subtotal,
        "gst_rate": gst_rate,
        "gst_amount": gst_amount,
        "total_amount": total_amount,
        "currency": "INR",
    }


def invoice_summary(job, closure) -> dict:
    """Return identifiers and totals used by invoice views and emails."""
    amounts = invoice_totals(closure.subtotal)
    return {
        "invoice_number": str(closure.id),
        "currency": amounts["currency"],
        **amounts,
        "job_id": job.id,
        "completed_at": closure.completed_at,
    }


def render_invoice_pdf(job, closure, signature=None) -> bytes:
    """Render a green-accented billing report from persisted invoice records."""
    import base64
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader, simpleSplit
    from reportlab.pdfgen import canvas

    totals = invoice_totals(closure.subtotal)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    green = colors.HexColor("#16834A")
    dark_green = colors.HexColor("#116638")
    pale_green = colors.HexColor("#EAF5EE")
    text_color = colors.HexColor("#26332B")
    muted = colors.HexColor("#64746A")
    margin = 42
    pdf.setTitle(f"Invoice - Job #{job.id}")
    pdf.setFillColor(green)
    pdf.roundRect(margin, height - 112, width - 2 * margin, 76, 10, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(margin + 20, height - 66, "FieldOps - Billing Report")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margin + 20, height - 88, f"Report #{closure.id}  |  Job #{job.id}")

    completed_at = closure.completed_at
    if isinstance(completed_at, datetime):
        completed_date = completed_at.date().isoformat()
    elif isinstance(completed_at, date):
        completed_date = completed_at.isoformat()
    else:
        completed_date = str(completed_at or "N/A").split("T", 1)[0].split(" ", 1)[0]

    y = height - 140

    def section(title):
        nonlocal y
        pdf.setFillColor(pale_green)
        pdf.roundRect(margin, y - 8, width - 2 * margin, 23, 5, fill=1, stroke=0)
        pdf.setFillColor(dark_green)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin + 10, y, title)
        y -= 26

    def detail(label, value):
        nonlocal y
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(margin + 4, y, f"{label}:")
        pdf.setFillColor(text_color)
        pdf.setFont("Helvetica", 9)
        lines = simpleSplit(str(value or "N/A"), "Helvetica", 9, width - 2 * margin - 100)
        for line in lines or ["N/A"]:
            pdf.drawString(margin + 100, y, line)
            y -= 13

    section("JOB DETAILS")
    for label, value in (
        ("Customer", getattr(job, "customer_name", None) or "N/A"),
        ("Service", getattr(job, "service_type", None) or "N/A"),
        ("Location", getattr(job, "location", None) or getattr(job, "site_address", None) or "N/A"),
        ("Completed", completed_date),
    ):
        detail(label, value)

    y -= 8
    section("WORK SUMMARY")
    pdf.setFillColor(text_color)
    pdf.setFont("Helvetica", 9)
    summary = (getattr(closure, "work_summary", None) or "No work summary provided.").replace("\n", " ")
    for line in simpleSplit(summary, "Helvetica", 9, width - 2 * margin - 12):
        pdf.drawString(margin + 5, y, line)
        y -= 13
        if y < 105:
            pdf.showPage()
            y = height - 55
            pdf.setFillColor(text_color)
            pdf.setFont("Helvetica", 9)

    y -= 10
    section("COST DETAILS")
    costs = (
        ("Service Charge", float(getattr(closure, "labour_cost", 0) or 0)),
        ("Material Cost", float(getattr(closure, "material_cost", 0) or 0)),
        ("Subtotal", totals["subtotal"]),
        ("GST (5%)", totals["gst_amount"]),
        ("Total", totals["total_amount"]),
    )
    table_left = margin
    table_right = width - margin
    row_height = 21
    for index, (label, value) in enumerate(costs):
        is_total = label == "Total"
        if is_total:
            pdf.setFillColor(pale_green)
            pdf.roundRect(table_left, y - 6, table_right - table_left, row_height, 4, fill=1, stroke=0)
        pdf.setFillColor(dark_green if is_total else text_color)
        pdf.setFont("Helvetica-Bold" if is_total or label in {"Subtotal", "GST (5%)"} else "Helvetica", 9)
        pdf.drawString(table_left + 8, y, label)
        pdf.drawRightString(table_right - 8, y, f"{totals['currency']} {value:,.2f}")
        y -= row_height

    signature_data = getattr(signature, "signature_data", None)
    if signature_data:
        y -= 10
        section("CUSTOMER SIGNATURE")
        box_height = 68
        pdf.setStrokeColor(colors.HexColor("#C8D5CC"))
        pdf.roundRect(margin, y - box_height + 8, 190, box_height, 4, fill=0, stroke=1)
        try:
            encoded = signature_data.split(",", 1)[1]
            image = ImageReader(BytesIO(base64.b64decode(encoded, validate=True)))
            image_width, image_height = image.getSize()
            scale = min(170 / float(image_width or 1), 52 / float(image_height or 1), 1.0)
            draw_width, draw_height = image_width * scale, image_height * scale
            pdf.drawImage(image, margin + 10, y - box_height + 16,
                          width=draw_width, height=draw_height,
                          preserveAspectRatio=True, mask="auto")
        except Exception:
            # A malformed optional signature must not prevent invoice delivery.
            pass
        y -= box_height + 10

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica-Oblique", 7)
    pdf.drawString(margin, 28, "Generated from the FieldOps technician billing report")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
