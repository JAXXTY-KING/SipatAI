from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from fastapi import Query
from fastapi.responses import FileResponse, Response

from app.db.assessment_store import AssessmentRecordNotFound, get_assessment, list_assessments
from app.services.susceptibility_service import (
    SusceptibilityUnavailableError,
    assess_point,
    chunk_png,
    chunks_in_bbox,
    get_susceptibility_status,
    render_outlook_chunk,
)
from app.integrations.province_forecast_client import get_forecast_samples
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


@router.get("/susceptibility/status")
async def susceptibility_status() -> dict[str, Any]:
    """Report whether the MindSpore flood-susceptibility (prediction) model is trained and its measured skill."""
    return await run_in_threadpool(get_susceptibility_status)


@router.post("/susceptibility")
async def flood_prone_areas(request: FloodModelRequest) -> dict[str, Any]:
    """Flood-proneness around a point combined with the real rainfall forecast for its province."""
    try:
        return await assess_point(request.longitude, request.latitude)
    except SusceptibilityUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/susceptibility/chunks")
async def susceptibility_chunks(
    west: float = Query(ge=110, le=130),
    south: float = Query(ge=0, le=25),
    east: float = Query(ge=110, le=130),
    north: float = Query(ge=0, le=25),
) -> dict[str, Any]:
    """Precomputed nationwide flood-prone overlays (1 degree squares) inside a map viewport."""
    try:
        return {"chunks": await run_in_threadpool(chunks_in_bbox, west, south, east, north)}
    except SusceptibilityUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/susceptibility/chunk/{chunk_id}.png")
async def susceptibility_chunk_image(chunk_id: str) -> FileResponse:
    try:
        return FileResponse(chunk_png(chunk_id), media_type="image/png", headers={"Cache-Control": "public, max-age=600"})
    except SusceptibilityUnavailableError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/outlook/chunk/{chunk_id}.png")
async def outlook_chunk_image(chunk_id: str) -> Response:
    """Flood-prone pixels recoloured by the real forecast rain over them (advisory/watch/warning)."""
    try:
        samples, fetched_at = await get_forecast_samples()
        image = await run_in_threadpool(render_outlook_chunk, chunk_id, samples, fetched_at)
    except SusceptibilityUnavailableError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail="Forecast unavailable for the flood outlook.") from error
    return Response(image, media_type="image/png", headers={"Cache-Control": "public, max-age=300"})


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
