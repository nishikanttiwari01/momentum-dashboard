from fastapi import APIRouter, Request, Response, status

router = APIRouter(tags=["Health"])

_db_ready = False  # Phase 3: pretend DB not ready yet

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/health/live")
def live():
    return {"status": "live"}

#@router.get("/health/ready")
#def ready():
#    if not _db_ready:
#        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
#    return {"status": "ready"}

@router.get("/health/ready")
def ready(req: Request):
    if not getattr(req.app.state, "ready", False):
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return {"status": "ready"}