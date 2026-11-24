from fastapi import APIRouter

from backend.api.auth import router as auth_router
from backend.api.agent import router as agent_router
from backend.api.tasks import router as tasks_router
from backend.api.devices import router as devices_router
from backend.api.events import router as events_router
from backend.api.video import router as video_router
from backend.api.websocket import router as ws_router
from backend.api.overview import router as overview_router
from backend.api.reports import router as reports_router
from backend.api.profiles import router as profiles_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(agent_router)
api_router.include_router(tasks_router)
api_router.include_router(devices_router)
api_router.include_router(events_router)
api_router.include_router(video_router)
api_router.include_router(ws_router)
api_router.include_router(overview_router)
api_router.include_router(reports_router)
api_router.include_router(profiles_router)

