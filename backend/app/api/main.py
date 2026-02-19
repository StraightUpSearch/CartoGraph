from fastapi import APIRouter

from app.api.routes import alerts, billing, domains, exports, items, login, private, users, utils, webhooks, workspaces
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(domains.router)
api_router.include_router(workspaces.router)
api_router.include_router(webhooks.router)
api_router.include_router(alerts.router)
api_router.include_router(exports.router)
api_router.include_router(billing.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
