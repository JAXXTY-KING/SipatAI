from typing import Any

from fastapi import APIRouter, HTTPException

from app.integrations.modelarts_client import (
    ModelArtsConfigurationError,
    ModelArtsInferenceError,
    predict,
)
from app.schemas.inference import InferenceRequest

router = APIRouter(prefix="/analyze", tags=["analysis"])

@router.post("")
async def analyze(request: InferenceRequest) -> Any:
    """Call the configured ModelArts endpoint using its deployment payload contract."""
    try:
        return await predict(request.payload)
    except ModelArtsConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ModelArtsInferenceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
