from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SceneDownloadRequest(BaseModel):
    """A catalogue product to copy into the private OBS bucket."""

    model_config = ConfigDict(extra="forbid")

    collection: Literal["sentinel-1-grd", "sentinel-2-l2a"]
    product_name: str = Field(min_length=10, max_length=200, pattern=r"^[A-Za-z0-9_\-]+(\.SAFE)?$")


class SceneSearchRequest(BaseModel):
    """Spatial and temporal search criteria for Sentinel scene discovery."""

    model_config = ConfigDict(extra="forbid")

    collection: Literal["sentinel-1-grd", "sentinel-2-l2a"]
    bbox: tuple[float, float, float, float]
    start_datetime: datetime
    end_datetime: datetime
    max_cloud_cover: float | None = Field(default=None, ge=0, le=100)
    limit: int = Field(default=50, ge=1, le=100)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        west, south, east, north = bbox
        if not -180 <= west < east <= 180 or not -90 <= south < north <= 90:
            raise ValueError("bbox must be west, south, east, north in EPSG:4326 bounds.")
        return bbox

    @field_validator("start_datetime", "end_datetime")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Search datetimes must include a timezone, preferably UTC.")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_search_window(self) -> "SceneSearchRequest":
        if self.start_datetime >= self.end_datetime:
            raise ValueError("start_datetime must be earlier than end_datetime.")
        if self.collection == "sentinel-1-grd" and self.max_cloud_cover is not None:
            raise ValueError("Cloud-cover filtering applies only to Sentinel-2 L2A scenes.")
        return self
