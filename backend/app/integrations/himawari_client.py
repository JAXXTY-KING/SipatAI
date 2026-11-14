import html
import io
import json
import re
import time
from datetime import datetime, timezone

import httpx
from PIL import Image

TILE_INDEX_URL = "https://www.jma.go.jp/bosai/himawari/data/satimg/targetTimes_fd.json"
TILE_URL_TEMPLATE = (
    "https://www.jma.go.jp/bosai/himawari/data/satimg/"
    "{basetime}/fd/{validtime}/B13/TBB/{z}/{x}/{y}.jpg"
)
TILE_MIN_ZOOM = 3
TILE_MAX_ZOOM = 5
TILE_FRAME_COUNT = 12
TILE_CACHE_TTL_SECONDS = 1800
TILE_INDEX_TTL_SECONDS = 60
MAX_CACHED_TILES = 1500
# Infrared brightness of clear sea and land is about 25-35; clouds are brighter.
CLOUD_BRIGHTNESS_FLOOR = 36
CLOUD_BRIGHTNESS_CEILING = 200
_TILE_INDEX_CACHE: tuple[float, list[dict[str, str]]] | None = None
_TILE_CACHE: dict[tuple[str, int, int, int], tuple[float, bytes]] = {}
SOURCE_PAGE_URL = "https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php?area=se1"
IMAGE_URL_TEMPLATE = "https://www.data.jma.go.jp/mscweb/data/himawari/img/se1/se1_{band}_{time_code}.jpg"
CACHE_TTL_SECONDS = 300
FRAME_COUNT = 12
BANDS = {
    "b13": "B13 (Infrared)",
    "b03": "B03 (Visible)",
    "cve": "Day Convective Storm RGB",
    "ngt": "Night Microphysics RGB",
    "dms": "Day Microphysics RGB",
    "arm": "Airmass RGB",
}
_FRAME_CACHE: tuple[float, list[dict[str, str]]] | None = None
_IMAGE_CACHE: dict[tuple[str, str], tuple[float, bytes, str]] = {}


class HimawariServiceError(Exception):
    """Raised when the JMA satellite image cannot be retrieved or parsed."""


async def get_himawari_frames(band: str) -> list[dict[str, str]]:
    global _FRAME_CACHE
    if band not in BANDS:
        raise ValueError("Unsupported Himawari image band.")

    now = time.monotonic()
    if _FRAME_CACHE and now - _FRAME_CACHE[0] < CACHE_TTL_SECONDS:
        return _FRAME_CACHE[1][:FRAME_COUNT]

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(SOURCE_PAGE_URL)
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise HimawariServiceError("JMA's Himawari image service is temporarily unavailable.") from error

    selector = re.search(
        r'<select\b[^>]*name=["\']slt_time["\'][^>]*>(.*?)</select>',
        response.text,
        re.IGNORECASE | re.DOTALL,
    )
    if not selector:
        raise HimawariServiceError("JMA's satellite page did not contain a time selector.")

    frames = [
        {
            "time_code": match.group(1),
            "observed_at": html.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip(),
        }
        for match in re.finditer(
            r'<option\b[^>]*value=["\']?(\d{4})["\']?[^>]*>(.*?)</option>',
            selector.group(1),
            re.IGNORECASE | re.DOTALL,
        )
    ]
    if not frames:
        raise HimawariServiceError("JMA's satellite page did not contain any image times.")

    _FRAME_CACHE = (time.monotonic(), frames)
    return frames[:FRAME_COUNT]


async def get_himawari_image(
    band: str,
    time_code: str | None = None,
) -> tuple[bytes, str]:
    if band not in BANDS:
        raise ValueError("Unsupported Himawari image band.")

    frames = await get_himawari_frames(band)
    frame = next(
        (item for item in frames if item["time_code"] == time_code),
        None,
    ) if time_code else frames[0]
    if frame is None:
        raise ValueError("The requested satellite frame is not available from JMA.")

    cache_key = (band, frame["time_code"])
    now = time.monotonic()
    cached = _IMAGE_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1], cached[2]

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(
                IMAGE_URL_TEMPLATE.format(band=band, time_code=frame["time_code"])
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise HimawariServiceError("JMA's Himawari image service is temporarily unavailable.") from error

    image = response.content
    if not image.startswith(b"\xff\xd8"):
        raise HimawariServiceError("JMA returned an invalid satellite image.")

    _IMAGE_CACHE[cache_key] = (time.monotonic(), image, frame["observed_at"])
    return image, frame["observed_at"]


async def get_latest_himawari_image(band: str) -> tuple[bytes, str]:
    return await get_himawari_image(band)


def _format_observation_time(time_code: str) -> str:
    observed = datetime.strptime(time_code, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return f"{observed:%H:%M} UTC {observed.day} {observed:%b %Y}"


async def get_himawari_tile_frames() -> list[dict[str, str]]:
    """Return the most recent JMA full-disk observation times, oldest first."""
    global _TILE_INDEX_CACHE
    now = time.monotonic()
    if _TILE_INDEX_CACHE and now - _TILE_INDEX_CACHE[0] < TILE_INDEX_TTL_SECONDS:
        return _TILE_INDEX_CACHE[1]

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(TILE_INDEX_URL)
            response.raise_for_status()
        entries = json.loads(response.text)
        times = sorted({
            str(entry["validtime"])
            for entry in entries
            if re.fullmatch(r"\d{14}", str(entry.get("basetime", "")))
            and entry.get("basetime") == entry.get("validtime")
        })
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
        if _TILE_INDEX_CACHE:
            return _TILE_INDEX_CACHE[1]
        raise HimawariServiceError("JMA's Himawari tile index is temporarily unavailable.") from error
    if not times:
        raise HimawariServiceError("JMA's Himawari tile index contained no observation times.")

    frames = [
        {"time_code": time_code, "observed_at": _format_observation_time(time_code)}
        for time_code in times[-TILE_FRAME_COUNT:]
    ]
    _TILE_INDEX_CACHE = (time.monotonic(), frames)
    return frames


def _cloud_overlay_png(jpeg: bytes) -> bytes:
    """Turn a grayscale infrared tile into white clouds on a transparent background."""
    try:
        with Image.open(io.BytesIO(jpeg)) as source:
            brightness = source.convert("L")
    except OSError as error:
        raise HimawariServiceError("JMA returned an invalid satellite tile.") from error

    span = CLOUD_BRIGHTNESS_CEILING - CLOUD_BRIGHTNESS_FLOOR
    alpha_table = []
    tone_table = []
    for value in range(256):
        strength = min(1.0, max(0.0, (value - CLOUD_BRIGHTNESS_FLOOR) / span))
        alpha_table.append(min(255, round(255 * 0.92 * strength ** 0.7 / 8) * 8))
        tone_table.append(min(255, round((214 + 41 * strength) / 8) * 8))
    tone = brightness.point(tone_table)
    overlay = Image.merge("RGBA", (tone, tone, tone, brightness.point(alpha_table)))
    output = io.BytesIO()
    overlay.save(output, format="PNG", optimize=True)
    return output.getvalue()


async def get_himawari_cloud_tile(time_code: str, z: int, x: int, y: int) -> bytes:
    """Return one transparent cloud tile for a recent, listed JMA observation time."""
    if not TILE_MIN_ZOOM <= z <= TILE_MAX_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError("The requested satellite tile is outside the available range.")
    frames = await get_himawari_tile_frames()
    if time_code not in {frame["time_code"] for frame in frames}:
        raise ValueError("The requested satellite frame is not available from JMA.")

    cache_key = (time_code, z, x, y)
    cached = _TILE_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < TILE_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(TILE_URL_TEMPLATE.format(
                basetime=time_code, validtime=time_code, z=z, x=x, y=y,
            ))
            if response.status_code == 404:
                raise ValueError("The requested satellite tile is not available from JMA.")
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise HimawariServiceError("JMA's Himawari tile service is temporarily unavailable.") from error

    tile = _cloud_overlay_png(response.content)
    if len(_TILE_CACHE) >= MAX_CACHED_TILES:
        _TILE_CACHE.pop(next(iter(_TILE_CACHE)))
    _TILE_CACHE[cache_key] = (time.monotonic(), tile)
    return tile
