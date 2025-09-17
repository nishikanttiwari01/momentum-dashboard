# app/api/v1/positions.py
# -----------------------------------------------------------------------------
# Positions API (GET/PUT) with robust error handling + structured logging.
# - Works with existing PositionsRepo (supports .get / .read_one / .fetch, and
#   .upsert / .save / .put fallback) without changing repo code.
# - Avoids 500s for common cases: returns 404 (not found), 400 (bad payload),
#   or 503 (DB not initialized) where appropriate.
# - Emits INFO/ERROR logs so we can trace what's going on in production.
# -----------------------------------------------------------------------------

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.responses import JSONResponse

# IMPORTANT: import your generated models the same way the rest of your code does.
# If you re-exported models via app.schemas.__init__, prefer that (stable import path).
try:
    from app.schemas import PositionIn, PositionOut  # re-exported path (preferred)
except Exception:
    # Fallback to generated path if re-export isn't wired in (won't break your app)
    from app.schemas.generated.models import PositionIn, PositionOut  # type: ignore

# Your existing repo (do NOT change its implementation)
from app.repos.sql.positions_repo import PositionsRepo  # noqa: E402

router = APIRouter(prefix="/positions", tags=["positions"])
log = logging.getLogger("app.api.positions")


# ----------------------------- repo helpers ----------------------------------

def _repo_get(repo: Any, symbol: str) -> Optional[Dict[str, Any]]:
    """
    Try a few common method names so we don't have to change working repo code.
    Returns a dict-like row or None.
    """
    for meth in ("get", "read_one", "fetch"):
        fn = getattr(repo, meth, None)
        if callable(fn):
            log.info("positions.get: using repo.%s for symbol=%s", meth, symbol)
            try:
                # Support both signatures: (symbol) and (symbol=...)
                try:
                    row = fn(symbol)
                except TypeError:
                    row = fn(symbol=symbol)
                return row
            except Exception:
                log.exception("positions.get: repo.%s crashed for symbol=%s", meth, symbol)
                raise
    # no suitable method
    log.error("positions.get: no supported getter on repo for symbol=%s", symbol)
    return None


def _repo_upsert(repo: Any, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upsert wrapper — tries .upsert / .save / .put. Returns the stored row.
    """
    for meth in ("upsert", "save", "put"):
        fn = getattr(repo, meth, None)
        if callable(fn):
            log.info("positions.upsert: using repo.%s for symbol=%s payload_keys=%s",
                     meth, symbol, list(data.keys()))
            try:
                # Support both signatures: (symbol, data) and (symbol=symbol, **data)
                try:
                    stored = fn(symbol, data)
                except TypeError:
                    stored = fn(symbol=symbol, **data)
                return stored
            except Exception:
                log.exception("positions.upsert: repo.%s crashed for symbol=%s", meth, symbol)
                raise
    log.error("positions.upsert: no supported upsert method on repo for symbol=%s", symbol)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Positions repository does not support upsert/save/put.",
    )


# ------------------------------- endpoints -----------------------------------

@router.get(
    "/{symbol}",
    response_model=PositionOut,
    summary="Get saved position for a symbol",
)
def get_position(symbol: str):
    """
    Read the saved position row for `symbol`.
    """
    log.info("GET /positions/%s", symbol)

    try:
        repo = PositionsRepo()
        row = _repo_get(repo, symbol)
    except RuntimeError as e:
        # Match the known message from your stack traces
        if "DB not initialized" in str(e):
            log.warning("GET /positions/%s → DB not initialized", symbol)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DB not initialized. Try again soon.",
            )
        # Unknown runtime error
        log.exception("GET /positions/%s → runtime error", symbol)
        raise HTTPException(status_code=500, detail="Internal server error")

    if not row:
        log.info("GET /positions/%s → 404 (not found)", symbol)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")

    try:
        # Ensure we only return the contract fields
        model = PositionOut.model_validate(row)
        payload = model.model_dump(mode="json")
        log.info("GET /positions/%s → 200", symbol)
        return JSONResponse(payload, status_code=200)
    except Exception:
        log.exception("GET /positions/%s → serialization/validation failed", symbol)
        raise HTTPException(status_code=500, detail="Serialization error")


@router.put(
    "/{symbol}",
    response_model=PositionOut,
    summary="Create or update a position for a symbol",
)
def put_position(symbol: str, payload: PositionIn = Body(...)):
    """
    Upsert position row for `symbol`. Returns the stored row.
    Designed to avoid 500s on normal error cases and to log each step.
    """
    log.info("PUT /positions/%s payload=%s", symbol, payload.model_dump(mode="json"))

    # Validate payload explicitly to avoid partial/None surprises downstream.
    try:
        data = payload.model_dump(mode="json", exclude_unset=True)
    except Exception:
        log.exception("PUT /positions/%s → payload validation failed", symbol)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    try:
        repo = PositionsRepo()
        stored = _repo_upsert(repo, symbol, data)
    except RuntimeError as e:
        if "DB not initialized" in str(e):
            log.warning("PUT /positions/%s → 503 (DB not initialized)", symbol)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DB not initialized. Try again soon.",
            )
        log.exception("PUT /positions/%s → runtime error", symbol)
        raise HTTPException(status_code=500, detail="Internal server error")
    except HTTPException:
        # Already logged; just bubble up
        raise
    except Exception:
        log.exception("PUT /positions/%s → repo upsert failed", symbol)
        raise HTTPException(status_code=500, detail="Failed to persist position")

    if not stored:
        log.error("PUT /positions/%s → repo returned empty result", symbol)
        raise HTTPException(status_code=500, detail="Positions repo returned no data")

    try:
        model = PositionOut.model_validate(stored)
        out = model.model_dump(mode="json")
        log.info("PUT /positions/%s → 200", symbol)
        return JSONResponse(out, status_code=200)
    except Exception:
        log.exception("PUT /positions/%s → serialization/validation failed (stored=%s)", symbol, stored)
        raise HTTPException(status_code=500, detail="Serialization error")
