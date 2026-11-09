from io import BytesIO
from math import isfinite
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from app.services.assessment_service import get_latest_assessment_summary


def create_flood_screening_report(screening: dict[str, Any]) -> BytesIO:
    """Create a clearly labeled PDF from a forecast-screening response."""
    features = screening.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("A flood-screening report requires forecast grid cells.")

    counts = {"elevated": 0, "watch": 0, "lower": 0}
    valid_features = []
    for feature in features:
        properties = feature.get("properties", {})
        tier = properties.get("screening_level")
        rainfall = properties.get("rainfall_24h_mm")
        if tier not in counts or not isinstance(rainfall, (int, float)) or not isfinite(rainfall):
            raise ValueError("Flood-screening grid cells contain invalid summary data.")
        counts[tier] += 1
        valid_features.append(feature)

    peak = max(valid_features, key=lambda feature: feature["properties"]["rainfall_24h_mm"])
    peak_properties = peak["properties"]
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=A4)
    _, page_height = A4
    document.setTitle("SipatAI Rainfall and Elevation Screening Brief")

    margin = 48
    current_y = page_height - 56

    def write_line(text: str, *, bold: bool = False, font_size: int = 10, gap: int = 16) -> None:
        nonlocal current_y
        document.setFont("Helvetica-Bold" if bold else "Helvetica", font_size)
        lines = simpleSplit(text, "Helvetica-Bold" if bold else "Helvetica", font_size, A4[0] - 2 * margin)
        for line in lines:
            if current_y < 60:
                document.showPage()
                current_y = page_height - 56
                document.setFont("Helvetica", 9)
            document.drawString(margin, current_y, line)
            current_y -= gap

    write_line("Rainfall and Elevation Screening Brief", bold=True, font_size=16, gap=25)
    write_line("SIPATAI PROTOTYPE - NOT A FLOOD DAMAGE ASSESSMENT", bold=True, font_size=9)
    write_line(f"Data provider: {screening.get('provider', 'Not recorded')}")
    write_line(f"Retrieved (UTC): {screening.get('fetched_at', 'Not recorded')}")
    write_line(f"Forecast horizon: {screening.get('forecast_period_hours', 'Not recorded')} hours")
    write_line(f"Grid resolution: {screening.get('grid_resolution_degrees', 'Not recorded')} degrees")
    write_line(f"Grid cells screened: {len(valid_features)}")
    write_line(f"Elevated screening tier: {counts['elevated']} grid cells")
    write_line(f"Watch screening tier: {counts['watch']} grid cells")
    write_line(f"Lower screening tier: {counts['lower']} grid cells")
    write_line(
        "Peak 24-hour rainfall in the next 72 hours: "
        f"{peak_properties['rainfall_24h_mm']:.1f} mm at grid center "
        f"{peak_properties['latitude']}, {peak_properties['longitude']}"
    )
    write_line(f"72-hour rainfall at that grid center: {peak_properties['rainfall_72h_mm']:.1f} mm")
    elevation = peak_properties.get("elevation_m")
    write_line(f"Model elevation at that grid center: {elevation} m" if elevation is not None else "Model elevation at that grid center: unavailable")
    current_y -= 8
    write_line("Prototype screening method", bold=True, font_size=11)
    for tier in ("elevated", "watch", "lower"):
        write_line(f"{tier.capitalize()}: {screening['method'][tier]}", font_size=9, gap=13)
    current_y -= 8
    write_line("Interpretation and limitations", bold=True, font_size=11)
    for note in (
        "This coarse rainfall-and-elevation screening is not a typhoon detector, storm track, or official warning.",
        "The threshold categories are unvalidated. They are not flood probabilities, inundation depths, flood boundaries, hectares, or affected farms.",
        "Elevation and forecast rainfall alone do not account for drainage, river levels, soil saturation, land cover, tides, barriers, or local hydrology.",
        "This brief contains no parcel intersection, crop loss, severity classification, or monetary damage estimate.",
        "Use official PAGASA bulletins and local disaster-risk advisories for decisions. Validate future models against authoritative observations before operational use.",
    ):
        write_line(f"- {note}", font_size=9, gap=14)
    current_y -= 8
    write_line("Sources", bold=True, font_size=11)
    write_line("Forecast: Open-Meteo API (https://open-meteo.com/)", font_size=9)
    write_line("Official Philippine tropical cyclone warnings: PAGASA (https://www.pagasa.dost.gov.ph/)", font_size=9)
    document.save()
    output.seek(0)
    return output


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
