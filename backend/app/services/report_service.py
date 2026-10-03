from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.assessment_service import get_latest_assessment_summary


def create_assessment_report(assessment: dict[str, Any]) -> BytesIO:
    """Create a PDF summary using values loaded from the assessment database."""
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=A4)
    _, page_height = A4

    document.setTitle("SipatAI Flood Damage Assessment")
    document.setFont("Helvetica-Bold", 16)
    document.drawString(48, page_height - 60, "Flood Damage Assessment")
    document.setFont("Helvetica", 10)
    document.drawString(48, page_height - 82, f"SipatAI | Assessment {assessment['assessment_id']}")

    fields = [
        ("Event", assessment["event_name"]),
        ("Municipality", assessment["municipality"]),
        ("Affected area", f"{assessment['total_affected_hectares']:,.1f} hectares"),
        (
            "Estimated damage",
            f"PHP {assessment['estimated_damage_php']:,.2f}"
            if assessment.get("estimated_damage_php") is not None
            else "Not calculated",
        ),
        ("Affected barangays", str(assessment["affected_barangays"])),
        ("Model version", assessment.get("model_version") or "Not recorded"),
    ]
    current_y = page_height - 132
    for label, value in fields:
        document.setFont("Helvetica-Bold", 10)
        document.drawString(48, current_y, label)
        document.setFont("Helvetica", 10)
        document.drawString(190, current_y, value[:100])
        current_y -= 24

    document.setFont("Helvetica", 9)
    document.drawString(48, 48, "Damage valuation is not included unless configured for this assessment.")
    document.showPage()
    document.save()
    output.seek(0)
    return output


def generate_latest_assessment_report() -> BytesIO:
    """Generate a PDF for the latest completed database assessment."""
    return create_assessment_report(get_latest_assessment_summary())
