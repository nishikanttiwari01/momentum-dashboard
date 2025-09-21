# backend/app/schemas/detail.py
"""
Re-export Drawer Detail contract models from the generated code.

This keeps imports stable for the rest of the codebase:
    from app.schemas.detail import DrawerDetail, NextAction, Meter, ...

While the actual class definitions are generated from OpenAPI in:
    app.schemas.generated.models
"""

from __future__ import annotations
from typing import Any, Optional

from app.schemas.generated import models as gen


def _resolve(gen_mod: Any, *candidates: str, required: bool = False) -> Optional[type]:
    """
    Return the first attribute found in gen_mod matching any of the candidate names.
    If required and none found, raise a clear ImportError listing available attributes.
    """
    for name in candidates:
        obj = getattr(gen_mod, name, None)
        if obj is not None:
            return obj
    if required:
        available = ", ".join(sorted(n for n in dir(gen_mod) if not n.startswith("_")))
        raise ImportError(
            f"Could not resolve any of {candidates} in app.schemas.generated.models. "
            f"Available: {available}"
        )
    return None


# -------- Core detail models (required) --------
DrawerDetail = _resolve(gen, "DrawerDetail", required=True)

# Some generators name these differently across versions; resolve flexibly.
Indicators = _resolve(
    gen,
    # common candidates
    "Indicators", "DrawerIndicators", "IndicatorsModel", "IndicatorsBlock",
    # looser fallbacks
    "IndicatorSet", "IndicatorsSchema"
)
Position = _resolve(gen, "Position", "DrawerPosition", "PositionModel")
Meter = _resolve(gen, "Meter", "DrawerMeter", "MeterModel")
NextAction = _resolve(gen, "NextAction", "DrawerNextAction", "NextActionModel")
AlertTemplate = _resolve(gen, "AlertTemplate", "DrawerAlertTemplate", "AlertTemplateModel")

# Contract says "Channels" (object with email/desktop/whatsapp).
# Codegen sometimes emits ChannelsModel or similar. Keep the alias.
Channels = _resolve(gen, "Channels", "ChannelsModel", "DrawerChannels")

__all__ = [
    "DrawerDetail",
    "Indicators",
    "Position",
    "Meter",
    "NextAction",
    "AlertTemplate",
    "Channels",
]
