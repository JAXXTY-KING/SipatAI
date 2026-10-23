from pydantic import BaseModel, ConfigDict, Field


class WeatherRequest(BaseModel):
    """WGS 84 map coordinate for a current-weather lookup."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
