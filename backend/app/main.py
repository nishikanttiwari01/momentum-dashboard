# backend/app/main.py
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from uuid import uuid4  # <-- NEW

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import config as config
from app.middleware.request_log import RequestLogMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.api.v1 import (
    health,
    screener,
    instruments,
    alerts,
    history,
    settings,
    runs,
    scan,
    universe,
)
from app.api.errors import (
    on_validation_error,
    on_http_exception,
    on_unhandled_exception,
)
from app.core import db
from app.workers import scheduler as sched
import logging
from app.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger("app.main")
logger.info("App boot: logging configured")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure test-time env vars (e.g. APP_SQLITE_PATH) take effect
    if hasattr(config.load, "cache_clear"):
        config.load.cache_clear()

    cfg = config.load()

    # Initialize DB from configured path (tests point this at a tmp file)
    db.init_sqlite(cfg.storage.sqlite_path)

    # NEW: generate a per-app idempotency salt so keys are unique per test app instance
    app.state.idem_salt = uuid4().hex  # <-- NEW

    app.state.ready = True
    # Optionally start scheduler:
    sched.start_if_enabled()

    try:
        yield
    finally:
        sched.shutdown()
        db.dispose_engine()


#
  #  pass


def create_app() -> FastAPI:
    cfg = config.load()
    logging.getLogger(__name__).info("boot", extra={"env": cfg.app.env})

    app = FastAPI(title=cfg.app.name, lifespan=lifespan)
    app.state.ready = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(StarletteHTTPException, on_http_exception)
    app.add_exception_handler(Exception, on_unhandled_exception)

    prefix = cfg.app.api_prefix
    app.include_router(health.router,      prefix=prefix)
    app.include_router(screener.router,    prefix=prefix, tags=["Screener"])
    app.include_router(instruments.router, prefix=prefix, tags=["Instruments"])
    app.include_router(alerts.router,      prefix=prefix, tags=["Alerts"])
    app.include_router(history.router,     prefix=prefix, tags=["History"])
    app.include_router(settings.router,    prefix=prefix, tags=["Settings"])
    app.include_router(runs.router,        prefix=prefix, tags=["Runs"])
    app.include_router(scan.router,        prefix=prefix, tags=["Screener"])
    app.include_router(universe.router,    prefix=prefix, tags=["Universe"])
    return app


app = create_app()
