from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.redis_client import close_redis_client, init_redis_client
from app.routers import admin, billing, chat, health, mock_provider, portal
from app.routers import auth, payment, user_keys

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_redis_client()
    yield
    await close_redis_client()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
    application.include_router(health.router)
    application.include_router(chat.router)
    application.include_router(billing.router)
    application.include_router(admin.router)
    application.include_router(portal.router)
    application.include_router(auth.router)       # POST /auth/register, /auth/login, GET /auth/me
    application.include_router(payment.router)   # POST /billing/checkout, /billing/webhook
    application.include_router(user_keys.router) # GET/POST/DELETE /v1/me/keys

    if settings.enable_mock_provider:
        application.include_router(mock_provider.router)

    return application


app = create_app()
