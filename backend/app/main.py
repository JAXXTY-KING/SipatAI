from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.damage_map import router as damage_map_router
from app.api.routes.analyze import router as analyze_router
from app.api.routes.health import router as health_router
from app.api.routes.reports import router as reports_router
from app.api.routes.scenes import router as scenes_router
from app.api.routes.summary import router as summary_router
from app.core.config import get_allowed_origins

app = FastAPI(
    title="SipatAI API",
    description="Agricultural flood assessment API backed by configured data and inference services.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(health_router)
app.include_router(summary_router, prefix="/api/v1")
app.include_router(analyze_router, prefix="/api/v1")
app.include_router(damage_map_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(scenes_router, prefix="/api/v1")
