from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.db.assessment_store import AssessmentRecordNotFound, get_assessment
from app.db.session import DatabaseNotConfigured, DatabaseUnavailable
from app.integrations.flood_screening_client import (
    FloodScreeningError,
    get_nationwide_flood_screening,
)
from app.services.assessment_service import AssessmentNotFound
from app.services.report_service import (
    create_flood_screening_report,
    create_satellite_assessment_report,
    generate_latest_assessment_report,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/flood-screening")
async def generate_flood_screening_report() -> StreamingResponse:
    """Generate a PDF brief from the latest public forecast-screening data."""
    try:
        screening = await get_nationwide_flood_screening()
        report_file = create_flood_screening_report(screening)
    except FloodScreeningError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=502, detail="Forecast screening data cannot be reported.") from error

    return StreamingResponse(
        report_file,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="sipatai-rainfall-screening-brief.pdf"'},
    )


@router.post("/satellite-assessment/{assessment_id}")
def generate_satellite_assessment_report(assessment_id: int) -> StreamingResponse:
    """Generate a PDF from a saved MindSpore satellite assessment (no GaussDB required)."""
    try:
        report_file = create_satellite_assessment_report(get_assessment(assessment_id))
    except AssessmentRecordNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return StreamingResponse(
        report_file,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="sipatai-satellite-assessment-{assessment_id}.pdf"'},
    )


@router.post("")
def generate_report() -> StreamingResponse:
    """Generate a PDF report from the latest completed database assessment."""
    try:
        report_file = generate_latest_assessment_report()
    except DatabaseNotConfigured as error:
        raise HTTPException(status_code=503, detail="Assessment database is not configured.") from error
    except DatabaseUnavailable as error:
        raise HTTPException(status_code=503, detail="Assessment database is unavailable.") from error
    except AssessmentNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return StreamingResponse(
        report_file,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="sipatai-assessment.pdf"'},
    )
