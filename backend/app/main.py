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

# ---------------- NEW: light helpers for startup backfill ----------------
import os
import asyncio
import anyio

def _boolish(val: str | None, default: bool = True) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")

async def _run_startup_backfill(logger: logging.Logger) -> None:
    """
    Fire-and-forget wrapper that invokes the existing CLI backfill
    without blocking app startup.
    """
    # small delay so the server is fully up
    await asyncio.sleep(5)
    try:
        logger.info("startup backfill: begin")
        # Import lazily so normal boot has no hard dependency if module moves
        from app.cli.backfill import main as backfill_main
        # run the CLI entrypoint in a worker thread (it prints progress & returns an int rc)
        rc = await anyio.to_thread.run_sync(backfill_main, [])
        logger.info("startup backfill: done rc=%s", rc)
    except Exception:
        logger.exception("startup backfill: FAILED")
# -------------------------------------------------------------------------


# NOTE: don't create/return an app instance here yet; do it in create_app().

def _wire_logging() -> logging.Logger:
    setup_logging()
    logger = logging.getLogger("app.main")
    logger.info("App boot: logging configured")
    return logger


def _wrap_unhandled(logger: logging.Logger):
    orig = on_unhandled_exception
    async def _wrapper(request: Request, exc: Exception):
        logger.exception("UNHANDLED %s %s -> %r", request.method, request.url.path, exc)
        return await orig(request, exc)
    return _wrapper


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger("app.main")
    logger.info("lifespan: begin")

    if hasattr(config.load, "cache_clear"):
        config.load.cache_clear()

    cfg = config.load()
    logger.info("lifespan: config loaded env=%s", getattr(cfg.app, "env", "unknown"))

    try:
        db.init_sqlite(cfg.storage.sqlite_path)
        logger.info("lifespan: db.init_sqlite ok path=%s", cfg.storage.sqlite_path)
    except Exception:
        logger.exception("lifespan: db.init_sqlite failed")
        raise

    logger.info("DB: sqlite_path=%s", cfg.storage.sqlite_path)
    try:
        from app.core.db import get_sessionmaker
        sm = get_sessionmaker()
        with sm() as s:
            try:
                cnt = s.execute(text("select count(1) from positions")).scalar()  # type: ignore
                logger.info("DB: positions row count = %s", cnt)
            except Exception as e:
                logger.warning("DB: positions table count failed: %r", e)
    except Exception as e:
        logger.warning("DB: unable to log positions count: %r", e)

    app.state.idem_salt = uuid4().hex
    app.state.ready = True

    # Start scheduler (non-fatal on failure)
    try:
        sched.start_if_enabled()
    except Exception:
        logger.exception("lifespan: scheduler start failed (continuing)")

    # ------------- NEW: optionally kick off startup backfill -------------
    # Source of truth: env var BACKFILL_ON_START (default true).
    # You can also export it via your YAML -> env pipeline.
    backfill_default = getattr(cfg.app, "backfill_on_start", True)
    env_backfill = os.getenv("BACKFILL_ON_START")
    if env_backfill is not None:
        backfill_enabled = _boolish(env_backfill, default=bool(backfill_default))
    else:
        backfill_enabled = bool(backfill_default)
    if backfill_enabled:
        try:
            asyncio.create_task(_run_startup_backfill(logger))
            logger.info("startup backfill: scheduled (BACKFILL_ON_START=on)")
        except Exception:
            logger.exception("startup backfill: schedule failed (continuing)")
    else:
        logger.info("startup backfill: disabled (BACKFILL_ON_START=off)")
    # ---------------------------------------------------------------------

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
    logger = _wire_logging()
    logging.getLogger("app.main").setLevel(logging.INFO)
    logging.getLogger("app.api.v1.instruments").setLevel(logging.INFO)
    logging.getLogger("app.services.detail").setLevel(logging.INFO)

    cfg = config.load()
    logger.info("boot env=%s", getattr(cfg.app, "env", "unknown"))

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
        return response

    app.add_exception_handler(RequestValidationError, on_validation_error)
    app.add_exception_handler(StarletteHTTPException, on_http_exception)
    app.add_exception_handler(Exception, _wrap_unhandled(logger))

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
