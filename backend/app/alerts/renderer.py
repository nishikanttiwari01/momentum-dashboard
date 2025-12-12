from __future__ import annotations

from decimal import Decimal
import logging
import math
from numbers import Real
from typing import Any, Dict

log = logging.getLogger(__name__)


def _format_for_template(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _format_for_template(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_format_for_template(val) for val in value]
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    return value


def _prepare_template_context(context: Dict[str, Any]) -> Dict[str, Any]:
    if not context:
        return {"symbol": "UNKNOWN", "description": ""}
    prepared = {key: _format_for_template(val) for key, val in context.items()}
    if not prepared.get("symbol"):
        prepared["symbol"] = "UNKNOWN"
    prepared.setdefault("description", "")
    return prepared


def render_template(
    template: Dict[str, str] | None,
    fallback: Dict[str, str],
    context: Dict[str, Any],
) -> tuple[str, str]:
    tpl = template or {}
    title_tpl = tpl.get("title") or fallback.get("title") or "{{ code }} - {{ symbol }}"
    body_tpl = tpl.get("body") or fallback.get("body") or "{{ description }}"

    prepared_context = _prepare_template_context(context)

    try:
        from jinja2 import Environment, BaseLoader, StrictUndefined

        jenv = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        title = jenv.from_string(title_tpl).render(**prepared_context)
        body = jenv.from_string(body_tpl).render(**prepared_context)
        log.debug(
            "Rendered alert template using jinja context_keys=%s title_template=%s body_template=%s",
            list(prepared_context.keys()),
            title_tpl,
            body_tpl,
        )
        return title.strip(), body.strip()
    except Exception:
        log.exception("Template rendering failed; falling back to simple renderer", exc_info=True)

        def cheap(s: str) -> str:
            out = s
            for key, value in prepared_context.items():
                out = out.replace(f"{{{{ {key} }}}}", str(value)).replace(f"{{{{{key}}}}}", str(value))
            return out

        log.debug(
            "Rendered alert template via fallback context_keys=%s",
            list(prepared_context.keys()),
        )
        return cheap(title_tpl).strip(), cheap(body_tpl).strip()
