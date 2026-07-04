"""Startup config validation — fail loud on misconfigurations.

Philosophy
----------
Silent defaults are the enemy of a trading system. If the email alerter is
enabled but SMTP credentials are missing, we'd rather refuse to start than
scan the market all day and quietly drop every alert. Same for the critical
buy/sell rules — if they're disabled by accident, we should shout.

Policy summary
--------------
- HARD errors raise :class:`ConfigValidationError` (startup aborts):
    * email.enabled=true but SMTP host/username/password/from_addr missing
    * email.enabled=true but no recipients configured
    * strategy.profiles.buy has NO enabled profile (nothing can be bought)
    * strategy.profiles.sell.common disabled entirely (nothing can be sold)

- SOFT warnings are logged but don't abort:
    * ntfy.enabled=true but server or topics missing
    * email recipients look malformed (no '@')
    * news.enabled=true but no providers enabled
    * selection_policy.max_open_positions <= 0
    * scheduler.enabled=true but interval_minutes <= 0

The intent is "loud at boot, not loud at runtime." Every check below has a
human-readable hint in the error message pointing at the YAML key to fix.
"""
from __future__ import annotations

import logging
from typing import Any, List

log = logging.getLogger(__name__)


class ConfigValidationError(RuntimeError):
    """Raised at app startup when config is broken in a way that would
    silently degrade the system at runtime.
    """


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _looks_like_email(s: str) -> bool:
    return isinstance(s, str) and "@" in s and "." in s.split("@")[-1]


def validate_startup_config(cfg) -> List[str]:
    """Run all startup validations against a loaded Settings object.

    Returns a list of soft-warning messages (for the caller to log or
    surface). Raises :class:`ConfigValidationError` on any hard error,
    with all errors aggregated into a single message.
    """
    errors: List[str] = []
    warnings: List[str] = []

    _validate_alerts(cfg, errors, warnings)
    _validate_strategy(cfg, errors, warnings)
    _validate_scheduler(cfg, errors, warnings)
    _validate_news(cfg, errors, warnings)

    for w in warnings:
        log.warning("config warning: %s", w)

    if errors:
        joined = "\n  - ".join([""] + errors)
        raise ConfigValidationError(
            f"Invalid startup config ({len(errors)} hard error(s)):{joined}"
        )

    return warnings


def _validate_alerts(cfg, errors: List[str], warnings: List[str]) -> None:
    alerts = getattr(cfg, "alerts", None)
    if alerts is None:
        return

    delivery = getattr(alerts, "delivery", None)
    if delivery is None:
        return

    email = getattr(delivery, "email", None)
    if email is not None and getattr(email, "enabled", False):
        smtp = getattr(email, "smtp", None)
        if smtp is None:
            errors.append(
                "alerts.delivery.email.enabled=true but alerts.delivery.email.smtp "
                "section is missing"
            )
        else:
            missing: List[str] = []
            for key in ("host", "port", "username", "password", "from_addr"):
                val = getattr(smtp, key, None)
                if _is_blank(val):
                    missing.append(key)
            if missing:
                errors.append(
                    "alerts.delivery.email.enabled=true but SMTP "
                    f"{sorted(missing)} not set — export the matching "
                    "SMTP_* env vars (SMTP_PASSWORD, etc.) or disable "
                    "the email channel."
                )

        defaults = getattr(email, "defaults", None)
        recipients = list(getattr(defaults, "to", []) or []) if defaults else []
        recipients = [r for r in recipients if not _is_blank(r)]
        if not recipients:
            errors.append(
                "alerts.delivery.email.enabled=true but no recipients in "
                "alerts.delivery.email.defaults.to (set ALERT_EMAIL_TO_1 "
                "or edit alerts.yaml)."
            )
        else:
            bad = [r for r in recipients if not _looks_like_email(r)]
            if bad:
                warnings.append(
                    f"email recipients look malformed (no '@' or domain): {bad}"
                )

    ntfy = getattr(delivery, "ntfy", None)
    if ntfy is not None and getattr(ntfy, "enabled", False):
        if _is_blank(getattr(ntfy, "server", None)):
            warnings.append(
                "alerts.delivery.ntfy.enabled=true but ntfy.server is blank"
            )
        high = getattr(ntfy, "topic_high", None)
        low = getattr(ntfy, "topic_low", None)
        if _is_blank(high) and _is_blank(low):
            warnings.append(
                "alerts.delivery.ntfy.enabled=true but both topic_high and "
                "topic_low are blank — no ntfy alerts will be sent"
            )


def _validate_strategy(cfg, errors: List[str], warnings: List[str]) -> None:
    strategy = getattr(cfg, "strategy", None)
    if strategy is None:
        return

    profiles = getattr(strategy, "profiles", None)
    if profiles is None:
        errors.append(
            "strategy.profiles missing — no buy/sell rules defined"
        )
        return

    buy = getattr(profiles, "buy", None)
    if buy is None:
        errors.append("strategy.profiles.buy missing — nothing can be bought")
    else:
        enabled_profiles: List[str] = []
        # `buy` may be modeled as a Dict[str, StrategyBuyProfileConfig]
        # (current config.py) or as a Pydantic object with named sub-profile
        # attributes. Handle both shapes.
        iter_items: List[tuple] = []
        if isinstance(buy, dict):
            iter_items = list(buy.items())
        elif hasattr(buy, "model_dump") and isinstance(buy.model_dump(), dict):
            # Pydantic object: iterate declared fields + any extras.
            try:
                field_names = list(getattr(buy, "model_fields", {}).keys())
            except Exception:
                field_names = []
            extras = getattr(buy, "model_extra", None) or {}
            for name in field_names:
                iter_items.append((name, getattr(buy, name, None)))
            for name, val in extras.items():
                iter_items.append((name, val))
        else:
            # Last-ditch: scan public attributes (original behavior).
            for attr in dir(buy):
                if attr.startswith("_"):
                    continue
                iter_items.append((attr, getattr(buy, attr, None)))

        for name, sub in iter_items:
            if sub is None:
                continue
            # sub may itself be a dict or a Pydantic object.
            if isinstance(sub, dict):
                if bool(sub.get("enabled", False)):
                    enabled_profiles.append(name)
            elif hasattr(sub, "enabled") and getattr(sub, "enabled", False):
                enabled_profiles.append(name)

        if not enabled_profiles:
            errors.append(
                "no enabled strategy.profiles.buy.* — set at least one buy "
                "profile's `enabled: true` (e.g. swing_eod or intraday_breakout)"
            )

    sell = getattr(profiles, "sell", None)
    if sell is None:
        errors.append(
            "strategy.profiles.sell missing — nothing can be exited"
        )
    else:
        common = getattr(sell, "common", None)
        if common is None:
            errors.append(
                "strategy.profiles.sell.common missing — no stop/target rules"
            )
        else:
            stop = getattr(common, "stop", None)
            if stop is None:
                errors.append(
                    "strategy.profiles.sell.common.stop missing — no trailing "
                    "stop rules; positions cannot be exited on weakness"
                )
            targets = getattr(common, "targets", None)
            if targets is None:
                warnings.append(
                    "strategy.profiles.sell.common.targets missing — T1/T2 "
                    "profit-taking will not fire"
                )

    selection = getattr(strategy, "selection_policy", None)
    if selection is not None:
        max_open = getattr(selection, "max_open_positions", None)
        if isinstance(max_open, (int, float)) and max_open <= 0:
            warnings.append(
                f"strategy.selection_policy.max_open_positions={max_open} "
                "means no new positions will ever be opened"
            )
        top_n = getattr(selection, "top_n_per_run", None)
        if isinstance(top_n, (int, float)) and top_n <= 0:
            warnings.append(
                f"strategy.selection_policy.top_n_per_run={top_n} means no "
                "BUY_SELECTED events will fire per scan"
            )


def _validate_scheduler(cfg, errors: List[str], warnings: List[str]) -> None:
    sched = getattr(cfg, "scheduler", None)
    if sched is None:
        return
    if getattr(sched, "enabled", False):
        interval = getattr(sched, "interval_minutes", None)
        if isinstance(interval, (int, float)) and interval <= 0:
            errors.append(
                f"scheduler.enabled=true but interval_minutes={interval}; "
                "must be a positive number of minutes"
            )


def _validate_news(cfg, errors: List[str], warnings: List[str]) -> None:
    news = getattr(cfg, "news", None)
    if news is None:
        return
    if not getattr(news, "enabled", False):
        return
    # News uses a flexible dict shape; we only do soft checks.
    providers = None
    try:
        providers = getattr(news, "providers", None) or getattr(news, "sources", None)
    except Exception:
        providers = None
    if providers is None:
        warnings.append(
            "news.enabled=true but no providers/sources configured"
        )
        return
    if isinstance(providers, dict):
        any_enabled = any(
            isinstance(v, dict) and v.get("enabled", True)
            for v in providers.values()
        )
    elif isinstance(providers, list):
        any_enabled = any(
            isinstance(v, dict) and v.get("enabled", True)
            for v in providers
        )
    else:
        any_enabled = True  # unknown shape; don't nag
    if not any_enabled:
        warnings.append(
            "news.enabled=true but no individual provider has enabled=true"
        )
