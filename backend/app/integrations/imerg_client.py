import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

GIBS_TILE = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate_30min/default/"
    "{time}/GoogleMapsCompatible_Level6/4/7/13.png"
)
TILE_TEMPLATE = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate_30min/default/"
    "{time}/GoogleMapsCompatible_Level6/{{z}}/{{y}}/{{x}}.png"
)
_cache: tuple[float, dict[str, Any]] | None = None


async def latest_imerg_time() -> dict[str, Any] | None:
    """Probe NASA GIBS for the newest half-hourly IMERG scene (it is published about 4-6 hours late)."""
    global _cache
    if _cache and time.monotonic() - _cache[0] < 600:
        return _cache[1]
    now = datetime.now(timezone.utc) - timedelta(hours=2)
    candidate = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(24):
                stamp = candidate.strftime("%Y-%m-%dT%H:%M:%SZ")
                response = await client.head(GIBS_TILE.format(time=stamp))
                if response.status_code == 200:
                    result = {
                        "time": stamp,
                        "age_hours": round((datetime.now(timezone.utc) - candidate).total_seconds() / 3600, 1),
                        "tiles": TILE_TEMPLATE.format(time=stamp),
                        "source": "NASA GPM IMERG (via NASA GIBS), satellite precipitation rate",
                    }
                    _cache = (time.monotonic(), result)
                    return result
                candidate -= timedelta(minutes=30)
    except httpx.HTTPError:
        return _cache[1] if _cache else None
    return None
