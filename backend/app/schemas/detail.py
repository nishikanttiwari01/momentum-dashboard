# backend/app/schemas/detail.py
"""
Re-export Drawer Detail contract models from the generated code.

This keeps imports stable for the rest of the codebase:
    from app.schemas.detail import DrawerDetail, NextAction, Meter, ...

While the actual class definitions are generated from OpenAPI in:
    app.schemas.generated.models
"""

# CHANGED: centralize all DrawerDetail-facing models here via re-exports.
#          We also normalize the "Channels vs ChannelsModel" mismatch so the
#          rest of the code can import `Channels` per the contract text.

from app.schemas.generated import models as gen

# Core detail models
DrawerDetail   = gen.DrawerDetail
Indicators     = gen.Indicators
Position       = gen.Position
Meter          = gen.Meter
NextAction     = gen.NextAction
AlertTemplate  = gen.AlertTemplate

# Contract says "Channels" (object with email/desktop/whatsapp).
# Codegen named a similar structure `ChannelsModel` in some versions.
# Provide a stable alias so the rest of our app can always import `Channels`.
Channels       = getattr(gen, "Channels", None) or getattr(gen, "ChannelsModel")

__all__ = [
    "DrawerDetail",
    "Indicators",
    "Position",
    "Meter",
    "NextAction",
    "AlertTemplate",
    "Channels",
]
