import html
import re
import time

import httpx

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
