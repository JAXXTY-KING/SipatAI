from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.services import auto_scan

from app.api.routes.damage_map import router as damage_map_router
from app.api.routes.flood_model import router as flood_model_router
from app.api.routes.analyze import router as analyze_router
from app.api.routes.health import router as health_router
from app.api.routes.parcels import router as parcels_router
from app.api.routes.reports import router as reports_router
from app.api.routes.scan import router as scan_router
from app.api.routes.scenes import router as scenes_router
from app.api.routes.summary import router as summary_router
from app.api.routes.weather import router as weather_router
from app.core.config import get_allowed_origins

@asynccontextmanager
async def lifespan(_app: FastAPI):
    auto_scan.start()
    yield
    auto_scan.stop()


app = FastAPI(
    title="SipatAI API",
    description="Agricultural flood assessment API backed by configured data and inference services.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Himawari-Observation-Time", "X-Himawari-Band"],
)

app.include_router(health_router)
app.include_router(summary_router, prefix="/api/v1")
app.include_router(analyze_router, prefix="/api/v1")
app.include_router(damage_map_router, prefix="/api/v1")
app.include_router(parcels_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(scenes_router, prefix="/api/v1")
app.include_router(weather_router, prefix="/api/v1")
app.include_router(flood_model_router, prefix="/api/v1")
app.include_router(scan_router, prefix="/api/v1")
