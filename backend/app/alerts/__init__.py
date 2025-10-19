# Minimal package init; keeps public imports tidy.
import logging
from .types import Mode, Severity

log = logging.getLogger(__name__)

log.debug("app.alerts package initialized")
