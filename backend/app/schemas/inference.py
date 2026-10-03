from typing import Any

from pydantic import BaseModel, ConfigDict, Field

class InferenceRequest(BaseModel):
    """Model-specific JSON payload forwarded unchanged to ModelArts."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(min_length=1)
