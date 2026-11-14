from pydantic import BaseModel, ConfigDict, Field


class FloodModelRequest(BaseModel):
    """Tile centre for a local MindSpore flood analysis in the Philippines."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=4.0, le=21.5)
    longitude: float = Field(ge=116.0, le=127.5)
    date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Event date (YYYY-MM-DD). Omit to analyse the most recent scenes.",
    )
