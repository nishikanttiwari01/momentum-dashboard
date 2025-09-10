# backend/app/api/v1/_examples.py
from pathlib import Path
import json

EXAMPLES_DIR = Path(__file__).resolve().parents[4] / "contracts" / "examples"

def load_example(name: str):
    with open(EXAMPLES_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)
