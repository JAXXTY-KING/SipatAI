from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.db.assessment_store import AssessmentRecordNotFound, get_assessment, list_assessments
from app.schemas.flood_model import FloodModelRequest
from app.services.flood_model_service import (
    FloodModelDataError,
    FloodModelUnavailableError,
    analyze_area,
    get_model_status,
)

router = APIRouter(prefix="/model", tags=["mindspore"])


@router.get("/status")
async def model_status() -> dict[str, Any]:
    """Report whether the local MindSpore flood model is installed and trained."""
    return await run_in_threadpool(get_model_status)


@router.get("/assessments")
async def list_saved_assessments(limit: int = 50) -> dict[str, Any]:
    """List saved MindSpore satellite assessments, newest first."""
    return {"assessments": await run_in_threadpool(list_assessments, max(1, min(limit, 200)))}


@router.get("/assessments/{assessment_id}")
async def read_saved_assessment(assessment_id: int) -> dict[str, Any]:
    try:
        return await run_in_threadpool(get_assessment, assessment_id)
    except AssessmentRecordNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/analyze")
async def analyze_flood_area(request: FloodModelRequest) -> dict[str, Any]:
    """Run MindSpore flood segmentation on real Sentinel-1/2 data around a point."""
    try:
        return await run_in_threadpool(analyze_area, request.longitude, request.latitude, request.date)
    except FloodModelUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except FloodModelDataError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
