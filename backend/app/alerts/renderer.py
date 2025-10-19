from __future__ import annotations
from typing import Dict, Any, Optional

def render_template(template: Dict[str, str] | None, fallback: Dict[str, str], context: Dict[str, Any]) -> tuple[str, str]:
    tpl = template or {}
    title_tpl = tpl.get("title") or fallback.get("title") or "{{ code }} • {{ symbol }}"
    body_tpl  = tpl.get("body")  or fallback.get("body")  or "{{ description }}"

    try:
        from jinja2 import Environment, BaseLoader, StrictUndefined
        jenv = Environment(loader=BaseLoader(), undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True)
        title = jenv.from_string(title_tpl).render(**context)
        body  = jenv.from_string(body_tpl).render(**context)
        return title.strip(), body.strip()
    except Exception:
        # ultra-simple fallback; replace {{key}} occurrences we have
        def cheap(s: str) -> str:
            out = s
            for k, v in context.items():
                out = out.replace("{{ " + k + " }}", str(v)).replace("{{"+k+"}}", str(v))
            return out
        return cheap(title_tpl).strip(), cheap(body_tpl).strip()
