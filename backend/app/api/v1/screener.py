#backend/app/api/v1/screener.py
from fastapi import APIRouter
from ._examples import load_example

router = APIRouter()

@router.get("/screener")
def list_screener():
    return load_example("screener-list.json")
