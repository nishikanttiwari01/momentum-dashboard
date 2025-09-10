#backend/app/api/v1/settings.py
from fastapi import APIRouter
from ._examples import load_example
router = APIRouter()
@router.get("/settings")
def get_settings_api():
    return load_example("settings.json")

@router.put("/settings")
def put_settings_api():
    return load_example("settings.json")