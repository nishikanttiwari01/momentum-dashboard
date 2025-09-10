#backend/app/api/v1/instruments.py
from fastapi import APIRouter, Path
from ._examples import load_example

router = APIRouter()

@router.get("/instruments/{symbol}/detail")
def get_detail(symbol: str = Path(...)):
    # For Phase 3: ignore symbol, return a representative example
    return load_example("detail.json")
