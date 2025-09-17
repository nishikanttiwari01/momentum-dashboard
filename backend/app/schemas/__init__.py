# app/schemas/__init__.py
"""
Schema package bootstrap.

Priority order:
1) Contract-first generated models (preferred at app/schemas/generated/models.py)
   - Fallback to app/schemas/models.py (if you generated there).
2) Hand-authored adjunct schemas (e.g., screener.py, runs.py) that complement the OpenAPI set.

After this init, consumers can simply:
    from app.schemas import DrawerDetail, PositionOut, PositionUpsert, ...
…regardless of where the generator wrote the file.
"""

from __future__ import annotations

from types import ModuleType

# --- 1) Import the generated models module (prefer ./generated/models.py; fallback to ./models.py) ---
_gm: ModuleType | None = None
try:
    # Preferred location (recommended in this repo)
    from .generated import models as _gm  # type: ignore
except Exception:
    # Fallback: some environments generate into app/schemas/models.py
    try:
        from . import models as _gm  # type: ignore
    except Exception as e:
        raise ImportError(
            "Generated schemas module not found. Expected 'app/schemas/generated/models.py' "
            "or 'app/schemas/models.py'. Re-run datamodel-codegen pointing to one of these."
        ) from e

# Re-export ALL public names from the generated module so the package is contract-first.
globals().update({name: getattr(_gm, name) for name in dir(_gm) if not name.startswith("_")})
__all__ = [name for name in dir(_gm) if not name.startswith("_")]

# --- 2) Optional hand-written complements (kept for now; safe if absent) ---
# If you keep manual adjunct schemas, they get layered on top.
try:
    from .screener import *  # noqa: F401,F403
    from .runs import *      # noqa: F401,F403
    # from .alerts import *  # noqa: F401,F403  # uncomment if you keep a manual alerts module
    # Extend __all__ with any adjunct names that are actually present
    for _name in ("ScreenerRow", "ScreenerList", "RunSummary", "RunDetail", "Counts"):
        if _name in globals() and _name not in __all__:
            __all__.append(_name)
except Exception:
    # Adjunct modules are optional; never block imports if missing.
    pass

# Avoid leaking helper symbols
del ModuleType, _gm
