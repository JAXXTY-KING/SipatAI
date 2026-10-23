import re
import tempfile
from pathlib import Path

import httpx

from app.core.config import get_copernicus_credentials
from app.integrations.obs_client import upload_file

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
PRODUCT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+(\.SAFE)?$")


class SentinelDownloadError(RuntimeError):
    """Raised when a Sentinel product cannot be downloaded or stored."""


class SentinelCredentialsError(SentinelDownloadError):
    """Raised when Copernicus credentials are not configured."""


def normalise_product_name(product_name: str) -> str:
    """Validate a STAC item id and return the catalogue product name (with .SAFE)."""
    if not PRODUCT_NAME_PATTERN.fullmatch(product_name):
        raise ValueError("Invalid Sentinel product name.")
    return product_name if product_name.endswith(".SAFE") else f"{product_name}.SAFE"


def build_object_key(collection: str, product_name: str) -> str:
    """Return the private OBS key for a raw Sentinel product archive."""
    return f"raw/{collection}/{product_name.removesuffix('.SAFE')}.zip"


async def _get_access_token(client: httpx.AsyncClient) -> str:
    credentials = get_copernicus_credentials()
    if credentials is None:
        raise SentinelCredentialsError("Copernicus credentials are not configured.")
    username, password = credentials
    response = await client.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": "cdse-public",
            "username": username,
            "password": password,
        },
    )
    if response.status_code >= 400:
        raise SentinelDownloadError("Copernicus authentication failed.")
    token = response.json().get("access_token")
    if not token:
        raise SentinelDownloadError("Copernicus authentication returned no token.")
    return token


async def _resolve_product_id(client: httpx.AsyncClient, product_name: str) -> str:
    response = await client.get(
        ODATA_URL, params={"$filter": f"Name eq '{product_name}'", "$top": "1"}
    )
    if response.status_code >= 400:
        raise SentinelDownloadError(f"Copernicus catalogue returned HTTP {response.status_code}.")
    items = response.json().get("value", [])
    if not items:
        raise SentinelDownloadError("Sentinel product was not found in the catalogue.")
    return items[0]["Id"]


async def download_product_to_obs(collection: str, product_name: str) -> str:
    """Stream an authenticated Sentinel product into the private OBS bucket; return its key."""
    name = normalise_product_name(product_name)
    object_key = build_object_key(collection, name)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as client:
            token = await _get_access_token(client)
            product_id = await _resolve_product_id(client, name)
            with tempfile.TemporaryDirectory() as workdir:
                archive = Path(workdir) / "product.zip"
                async with client.stream(
                    "GET",
                    DOWNLOAD_URL.format(product_id=product_id),
                    headers={"Authorization": f"Bearer {token}"},
                    follow_redirects=True,
                ) as response:
                    if response.status_code >= 400:
                        raise SentinelDownloadError(
                            f"Copernicus download returned HTTP {response.status_code}."
                        )
                    with archive.open("wb") as handle:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            handle.write(chunk)
                upload_file(archive, object_key)
    except httpx.HTTPError as error:
        raise SentinelDownloadError("Copernicus request failed.") from error
    return object_key
