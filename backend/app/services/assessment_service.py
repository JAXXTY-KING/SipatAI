from typing import Any

from app.db.queries.assessment_summary import get_latest_assessment_summary as query_latest_summary


class AssessmentNotFound(RuntimeError):
    """Raised when no completed assessment is available in the database."""


def get_latest_assessment_summary() -> dict[str, Any]:
    """Return the latest completed assessment or report that none exists."""
    summary = query_latest_summary()
    if summary is None:
        raise AssessmentNotFound("No completed assessment is available.")
    return summary
