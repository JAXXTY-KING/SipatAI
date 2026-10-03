from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["system"])
def read_health() -> dict[str, str]:
    """Report whether the API process is responding."""
    return {"status": "ok"}
