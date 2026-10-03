from pathlib import Path

from obs import ObsClient

from app.core.config import get_obs_config


class OBSConfigurationError(RuntimeError):
    """Raised when OBS settings are missing or inconsistent."""


class OBSRequestError(RuntimeError):
    """Raised when an OBS operation fails."""


def _create_client(config: dict[str, str | bool]) -> ObsClient:
    if config["use_ecs_role"]:
        return ObsClient(
            server=str(config["endpoint"]),
            security_provider_policy="ECS",
            ssl_verify=True,
        )

    client_options = {
        "server": str(config["endpoint"]),
        "access_key_id": str(config["access_key_id"]),
        "secret_access_key": str(config["secret_access_key"]),
        "ssl_verify": True,
    }
    if config["security_token"]:
        client_options["security_token"] = str(config["security_token"])
    return ObsClient(**client_options)


def check_bucket_access() -> None:
    """Verify configured OBS credentials can read bucket metadata."""
    try:
        config = get_obs_config()
    except ValueError as error:
        raise OBSConfigurationError("OBS configuration is incomplete.") from error
    if config is None:
        raise OBSConfigurationError("OBS is not configured.")

    client = _create_client(config)
    try:
        response = client.getBucketMetadata(str(config["bucket"]))
        if response.status >= 300:
            raise OBSRequestError(f"OBS bucket check returned HTTP {response.status}.")
    except OBSRequestError:
        raise
    except Exception as error:
        raise OBSRequestError("OBS bucket check failed.") from error
    finally:
        client.close()


def upload_file(local_path: Path, object_key: str) -> None:
    """Upload a processed artifact to the configured private OBS bucket."""
    if not local_path.is_file():
        raise FileNotFoundError("OBS upload source file does not exist.")
    if not object_key or object_key.startswith("/") or ".." in Path(object_key).parts:
        raise ValueError("OBS object key must be a relative object path.")

    config = get_obs_config()
    if config is None:
        raise OBSConfigurationError("OBS is not configured.")

    client = _create_client(config)
    try:
        response = client.putFile(str(config["bucket"]), object_key, str(local_path))
        if response.status >= 300:
            raise OBSRequestError(f"OBS upload returned HTTP {response.status}.")
    except OBSRequestError:
        raise
    except Exception as error:
        raise OBSRequestError("OBS artifact upload failed.") from error
    finally:
        client.close()
