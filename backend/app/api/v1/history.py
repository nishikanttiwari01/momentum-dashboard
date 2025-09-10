#backend/app/api/v1/history.py
from fastapi import APIRouter
from ._examples import load_example
router = APIRouter()
@router.get("/history")
def list_history():
    return load_example("history.json")

