from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.db.session import DatabaseNotConfigured, DatabaseUnavailable
from app.services.assessment_service import AssessmentNotFound
from app.services.report_service import generate_latest_assessment_report

router = APIRouter(prefix="/reports", tags=["reports"])


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
