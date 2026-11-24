import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import logging
from backend.config import settings
from backend.database.init_db import init_database
from backend.api.router import api_router
from backend.iot.mqtt_client import mqtt_service
from backend.monitoring.runner import task_manager
from backend.monitoring.cleanup import cleanup_expired_evidence

logger = logging.getLogger("OmniSense")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for initialization and cleanup."""
    # 1. Security validation check
    if "change-in-production" in settings.SECRET_KEY.lower() or "secret-jwt-key" in settings.SECRET_KEY.lower():
        logger.warning("=" * 68)
        logger.warning("  [SECURITY WARNING] Using default development SECRET_KEY!")
        logger.warning("  For production, update SECRET_KEY in your .env configuration.")
        logger.warning("=" * 68)

    # 2. Data retention policy enforcement
    cleanup_expired_evidence()

    # 3. Initialize SQLite database and tables
    settings.setup_directories()
    init_database()

    # 4. Start MQTT background subscriber service
    mqtt_service.start()
    yield

    # 5. Clean shutdown handlers
    mqtt_service.stop()
    from backend.monitoring import universal_runner
    universal_runner.stop_all()
    try:
        task_manager.stop_all()
    except Exception:
        pass



app = FastAPI(
    title=settings.PROJECT_NAME,
    description="OmniSense AI - AI+IoT Real-time Monitoring Monolith",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for React frontend (Vite dev server default is 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount evidence directory for serving screenshot images
evidence_dir = Path(settings.EVIDENCE_DIR)
evidence_dir.mkdir(parents=True, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=str(evidence_dir)), name="evidence")

# Include master API router
app.include_router(api_router, prefix=settings.API_V1_STR)
# Also include /ws/dashboard and /video/stream at root for convenient client access
app.include_router(api_router)


@app.get("/api/health")
def health_check():
    """Health check endpoint to verify backend operational readiness."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "database": "sqlite_ready",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
