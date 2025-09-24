# backend/app/domain/next_action_catalog.py
from __future__ import annotations
from typing import Dict, Any

# Single source of truth for codes and default copy.
CATALOG: Dict[str, Dict[str, Any]] = {
    "EXIT_NOW": {
        "template": "Sell now (stop hit at ₹{stop})",
        "refs": ["stop_now"],
        "priority": 100,
    },
    "EXIT_EOD": {
        "template": "Exit at close if < EMA{n} (₹{ema_value})",
        "refs": ["ema_n", "ema_value", "tolerance_pct"],
        "priority": 90,
    },
    "HOLD_TIGHT": {
        "template": "Hold (trend strong)",
        "refs": ["ema_n", "ema_value", "adx14"],
        "priority": 60,
    },
    "HOLD_BREAKEVEN": {
        "template": "Hold (breakeven active)",
        "refs": ["entry_price_locked", "stop_now"],
        "priority": 60,
    },
    "HOLD_TRAIL": {
        "template": "Hold (trail stop at ₹{stop})",
        "refs": ["stop_now", "stop_method", "atr_pct", "k"],
        "priority": 55,
    },
    "HOLD": {
        "template": "Hold (above EMA{n})",
        "refs": ["ema_n", "ema_value"],
        "priority": 50,
    },
    "BUY_BREAKOUT": {
        "template": "Buy on breakout (≥ ₹{level})",
        "refs": ["breakout_level", "delta_pct", "relvol20"],
        "priority": 40,
    },
    "BUY_PULLBACK": {
        "template": "Buy on pullback (₹{entry_low}–₹{entry_high})",
        "refs": ["entry_low", "entry_high", "ema_n", "ema_value"],
        "priority": 40,
    },
    "BUY_STARTER": {
        "template": "Starter position (small size)",
        "refs": ["starter_size_pct", "ema_slow_value"],
        "priority": 40,
    },
    "ADD_ON_STRENGTH": {
        "template": "Add on strength (≥ ₹{add_level})",
        "refs": ["add_level", "relvol20", "adx_slope_5"],
        "priority": 35,
    },
    "WATCH": {
        "template": "Watch — weak momentum/volume/structure",
        "refs": ["failed_gates"],
        "priority": 20,
    },
    "IGNORE": {
        "template": "Ignore — does not meet basic filters",
        "refs": ["blocked_reason"],
        "priority": 10,
    },
    "NO_DATA": {
        "template": "Data insufficient",
        "refs": ["missing"],
        "priority": 5,
    },
    "ERROR": {
        "template": "Unavailable (error)",
        "refs": ["run_id"],
        "priority": 1,
    },
}
