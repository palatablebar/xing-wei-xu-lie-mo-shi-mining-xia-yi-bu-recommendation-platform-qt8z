"""路由聚合：统一 /api 前缀（Nginx 反代时剥掉 /api）。"""
from fastapi import APIRouter

from src.routes.audit import router as audit_router
from src.routes.auth import router as auth_router
from src.routes.events import router as events_router
from src.routes.exports import router as exports_router
from src.routes.health import router as health_router
from src.routes.mine_runs import router as mine_runs_router
from src.routes.overview import router as overview_router
from src.routes.patterns import router as patterns_router
from src.routes.recommendations import router as recommendations_router
from src.routes.sequences import router as sequences_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(overview_router)
api_router.include_router(events_router)
api_router.include_router(sequences_router)
api_router.include_router(mine_runs_router)
api_router.include_router(patterns_router)
api_router.include_router(recommendations_router)
api_router.include_router(exports_router)
api_router.include_router(audit_router)
