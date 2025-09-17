# backend/app/main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text  # CHANGED: for simple startup DB checks

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
    positions,
)
from app.api.errors import (
    on_validation_error,
    on_http_exception,
    on_unhandled_exception,  # we'll wrap this so we log first
)
from app.core import db
from app.workers import scheduler as sched

from app.core.logging_config import setup_logging

# NOTE: don't create/return an app instance here yet; do it in create_app().


def _wire_logging() -> logging.Logger:
    """
    Initialize logging exactly once. Always add a rotating file handler
    pointing at <repo-root>/logs/app.log. Returns a module logger.
    """
    setup_logging()  # writes "Logging initialized -> .../logs/app.log"
    logger = logging.getLogger("app.main")
    logger.info("App boot: logging configured")
    return logger


def _wrap_unhandled(logger: logging.Logger):
    """
    Return a logging wrapper for your on_unhandled_exception so that
    we preserve your existing JSON shape but also log the traceback.
    """
    orig = on_unhandled_exception

    async def _wrapper(request: Request, exc: Exception):
        logger.exception("UNHANDLED %s %s -> %r", request.method, request.url.path, exc)
        return await orig(request, exc)

    return _wrapper


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger("app.main")
    logger.info("lifespan: begin")

    # Ensure test-time env vars (e.g. APP_SQLITE_PATH) take effect
    if hasattr(config.load, "cache_clear"):
        config.load.cache_clear()

    cfg = config.load()
    logger.info("lifespan: config loaded env=%s", getattr(cfg.app, "env", "unknown"))

    # Initialize DB from configured path (tests point this at a tmp file)
    try:
        db.init_sqlite(cfg.storage.sqlite_path)
        logger.info("lifespan: db.init_sqlite ok path=%s", cfg.storage.sqlite_path)
    except Exception:
        logger.exception("lifespan: db.init_sqlite failed")
        raise

    # CHANGED: log DB path + positions table row count (best effort)
    logger.info("DB: sqlite_path=%s", cfg.storage.sqlite_path)
    try:
        # use the same sessionmaker as the app
        from app.core.db import get_sessionmaker  # existing helper in your project
        sm = get_sessionmaker()
        with sm() as s:
            try:
                cnt = s.execute(text("select count(1) from positions")).scalar()  # type: ignore
                logger.info("DB: positions row count = %s", cnt)
            except Exception as e:
                logger.warning("DB: positions table count failed: %r", e)
    except Exception as e:
        logger.warning("DB: unable to log positions count: %r", e)

    # per-app idempotency salt for tests
    app.state.idem_salt = uuid4().hex

    app.state.ready = True

    # Start scheduler in a guarded way so startup never hangs silently
    try:
        sched.start_if_enabled()
        logger.info("lifespan: scheduler started (if enabled)")
    except Exception:
        logger.exception("lifespan: scheduler start failed (continuing)")

    logger.info("lifespan: yield to serve")
    try:
        yield
    finally:
        logger.info("lifespan: shutdown begin")
        try:
            sched.shutdown()
            logger.info("lifespan: scheduler shutdown ok")
        except Exception:
            logger.exception("lifespan: scheduler shutdown error (continuing)")
        try:
            db.dispose_engine()
            logger.info("lifespan: db disposed")
        except Exception:
            logger.exception("lifespan: db dispose error")
        logger.info("lifespan: end")


def create_app() -> FastAPI:
    # CHANGED: initialize logging here so it's active for the real app instance
    logger = _wire_logging()
    logging.getLogger("app.main").setLevel(logging.INFO)
    logging.getLogger("app.api.v1.instruments").setLevel(logging.INFO)
    logging.getLogger("app.services.detail").setLevel(logging.INFO)

    cfg = config.load()
    logger.info("boot env=%s", getattr(cfg.app, "env", "unknown"))

    app = FastAPI(title=cfg.app.name, lifespan=lifespan)
    app.state.ready = False

    # CORS + request middlewares
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # CHANGED: request access log (method/path/status) on the live app
    @app.middleware("http")
    async def _req_access_logger(request: Request, call_next):
        path = request.url.path
        method = request.method
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("REQ EXC %s %s", method, path)
            raise
        logger.info("REQ %s %s -> %s", method, path, response.status_code)
        return response   # <— IMPORTANT: ensure this is 'response'

    # Exception handlers — keep your shapes, but ensure we log
    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(StarletteHTTPException, on_http_exception)
    app.add_exception_handler(Exception, _wrap_unhandled(logger))  # CHANGED

    # Routers
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
    app.include_router(positions.router,   prefix=prefix, tags=["Positions"])

    return app


app = create_app()
