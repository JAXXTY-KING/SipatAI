from fastapi import APIRouter, HTTPException

from app.db.session import DatabaseNotConfigured, DatabaseUnavailable
from app.services.assessment_service import AssessmentNotFound, get_latest_assessment_summary

router = APIRouter(prefix="/barangay", tags=["assessment"])


@router.get("/summary")
def read_barangay_summary() -> dict[str, object]:
    """Return summary metrics for the latest completed database assessment."""
    try:
        return get_latest_assessment_summary()
    except DatabaseNotConfigured as error:
        raise HTTPException(status_code=503, detail="Assessment database is not configured.") from error
    except DatabaseUnavailable as error:
        raise HTTPException(status_code=503, detail="Assessment database is unavailable.") from error
    except AssessmentNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
