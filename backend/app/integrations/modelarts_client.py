from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import get_modelarts_inference_config

class ModelArtsConfigurationError(RuntimeError):
    """Raised when ModelArts endpoint configuration is missing or unsafe."""

class ModelArtsInferenceError(RuntimeError):
    """Raised when the deployed ModelArts inference endpoint cannot be called."""

async def predict(payload: dict[str, Any]) -> Any:
    """Forward the model-specific JSON payload to the configured ModelArts endpoint."""
    try:
        endpoint_config = get_modelarts_inference_config()
    except ValueError as error:
        raise ModelArtsConfigurationError("ModelArts inference configuration is incomplete.") from error

    if endpoint_config is None:
        raise ModelArtsConfigurationError("ModelArts inference is not configured.")

    endpoint_url, endpoint_token = endpoint_config
    if urlsplit(endpoint_url).scheme != "https":
        raise ModelArtsConfigurationError("ModelArts inference endpoint must use HTTPS.")

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            response = await client.post(
                endpoint_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Auth-Token": endpoint_token,
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as error:
        raise ModelArtsInferenceError(
            f"ModelArts inference returned HTTP {error.response.status_code}."
        ) from error
    except httpx.HTTPError as error:
        raise ModelArtsInferenceError("ModelArts inference request failed.") from error
    except ValueError as error:
        raise ModelArtsInferenceError("ModelArts inference returned invalid JSON.") from error
