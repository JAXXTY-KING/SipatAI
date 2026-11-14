import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(BACKEND_ENV_FILE, override=False)
load_dotenv(BACKEND_ENV_FILE.with_name(".env.local"), override=False)


def get_allowed_origins() -> list[str]:
    """Read browser origins allowed to call the API from the environment."""
    configured_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if configured_origins.strip():
        return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
    if os.getenv("APP_ENV", "development").lower() != "production":
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    return []
    
def get_gaussdb_dsn() -> str | None:
    """Read the private GaussDB connection string without exposing it in logs."""
    configured_dsn = os.getenv("GAUSSDB_DSN", "").strip()
    return configured_dsn or None


def get_openweathermap_api_key() -> str | None:
    """Read the optional private weather-service key from backend environment."""
    configured_key = os.getenv("OPENWEATHERMAP_API_KEY", "").strip()
    return configured_key or None

def get_copernicus_credentials() -> tuple[str, str] | None:
    """Read private Copernicus Data Space account credentials."""
    username = os.getenv("COPERNICUS_USERNAME", "").strip()
    password = os.getenv("COPERNICUS_PASSWORD", "").strip()
    if not username or not password:
        return None
    return username, password


def get_flood_model_checkpoint() -> Path:
    """Return the trained MindSpore checkpoint used for local flood inference."""
    configured_path = os.getenv("SIPATAI_MODEL_CHECKPOINT", "").strip()
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return REPOSITORY_ROOT / "ml" / "artifacts" / "checkpoints" / "sipatai-best.ckpt"


def get_modelarts_inference_config() -> tuple[str, str] | None:
    """Return the configured HTTPS inference URL and private authorization token."""
    endpoint_url = os.getenv("MODELARTS_INFERENCE_URL", "").strip()
    endpoint_token = os.getenv("MODELARTS_INFERENCE_TOKEN", "").strip()
    if not endpoint_url and not endpoint_token:
        return None
    if not endpoint_url or not endpoint_token:
        raise ValueError("Both ModelArts inference environment variables must be configured.")
    return endpoint_url, endpoint_token


def get_obs_config() -> dict[str, str | bool] | None:
    """Read private OBS settings, supporting access keys or an ECS agency."""
    endpoint = os.getenv("OBS_ENDPOINT", "").strip()
    bucket = os.getenv("OBS_BUCKET", "").strip()
    access_key_id = os.getenv("OBS_ACCESS_KEY_ID", "").strip()
    secret_access_key = os.getenv("OBS_SECRET_ACCESS_KEY", "").strip()
    security_token = os.getenv("OBS_SECURITY_TOKEN", "").strip()
    use_ecs_role = os.getenv("OBS_USE_ECS_ROLE", "false").lower() == "true"

    if not any((endpoint, bucket, access_key_id, secret_access_key, security_token, use_ecs_role)):
        return None
    if not endpoint or not bucket:
        raise ValueError("OBS_ENDPOINT and OBS_BUCKET must both be configured.")
    if use_ecs_role and (access_key_id or secret_access_key or security_token):
        raise ValueError("Use either an ECS role or access-key credentials for OBS, not both.")
    if not use_ecs_role and (not access_key_id or not secret_access_key):
        raise ValueError("OBS access-key authentication requires both access key ID and secret access key.")

    return {
        "endpoint": endpoint,
        "bucket": bucket,
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "security_token": security_token,
        "use_ecs_role": use_ecs_role,
    }
