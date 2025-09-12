# backend/app/main.py
from __future__ import annotations
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import config as config
from app.core.db import init_sqlite
from app.middleware.request_log import RequestLogMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.api.v1 import health, screener, instruments, alerts, history, settings
from app.api.errors import (
    on_validation_error,
    on_http_exception,
    on_unhandled_exception,
)
from app.core import db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # init_sqlite is synchronous; do NOT await
    db.init_sqlite("./data/local.db")
    app.state.ready = True
    try:
        yield
    finally:
        # release SQLite handle for Windows so tests can unlink files
        db.dispose_engine()

def setup_logging() -> None:
    # (keep your logging wiring if you had it elsewhere)
    pass

def create_app() -> FastAPI:
    # Load config, then setup logging so boot logs go to console+file
    cfg = config.load()
    setup_logging()
    logging.getLogger(__name__).info("boot", extra={"env": cfg.app.env})

    app = FastAPI(title=cfg.app.name, lifespan=lifespan)
    app.state.ready = False

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middlewares
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # Exception handlers → Problem+JSON (with proper media type set in app/api/errors.py)
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(StarletteHTTPException, on_http_exception)
    app.add_exception_handler(Exception, on_unhandled_exception)

    # Routers
    prefix = cfg.app.api_prefix
    app.include_router(health.router,      prefix=prefix)
    app.include_router(screener.router,    prefix=prefix, tags=["Screener"])
    app.include_router(instruments.router, prefix=prefix, tags=["Instruments"])
    app.include_router(alerts.router,      prefix=prefix, tags=["Alerts"])
    app.include_router(history.router,     prefix=prefix, tags=["History"])
    app.include_router(settings.router,    prefix=prefix, tags=["Settings"])

    return app

app = create_app()
