from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from contextlib import asynccontextmanager

from .core import config
from .core.logging_setup import setup_logging
from .core.middleware import RequestLogMiddleware
from .core.problem import on_validation_error, on_http_exception, on_unhandled_exception
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.v1 import health, screener, instruments, alerts, history, settings
from .core import db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await db.init_sqlite("./data/local.db")
    app.state.ready = True
    logging.getLogger(__name__).info("app_ready")
    yield
    # shutdown (optional): close pools, flush logs, etc.

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

    # Request logging
    app.add_middleware(RequestLogMiddleware)

    # Exception handlers → Problem+JSON
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
