from __future__ import annotations
from importlib import import_module
from typing import Dict, Any
from .base import BaseRule

def _code_to_module_name(code: str) -> str:
    return code.lower().replace("_", " ")

def _code_to_pyfile(code: str) -> str:
    return code.lower().replace("__", "_").replace("-", "_").replace(" ", "_")

def load_rule_handler(code: str) -> BaseRule:
    mod_name = _code_to_pyfile(code)
    mod_path = f"app.alerts.rules.{mod_name}"
    mod = import_module(mod_path)
    # rule module should expose `Rule` (class) or `evaluate(ctx,symbol) -> EvalResult|None`
    if hasattr(mod, "Rule"):
        return getattr(mod, "Rule")()
    elif hasattr(mod, "evaluate"):
        class _FnRule(BaseRule):
            CODE = code
            def evaluate(self, ctx, symbol):
                return mod.evaluate(ctx, symbol)
        return _FnRule()
    raise ImportError(f"Rule module {mod_path} missing Rule/evaluate")
