"""Application logging configuration.

Renders log timestamps in the configured timezone (settings.timezone) instead
of the container's UTC clock, so app log lines line up with the CST timestamps
APScheduler already prints and with the operator's local reasoning.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import settings

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S %Z"


class _TimezoneFormatter(logging.Formatter):
    """Formatter whose asctime is rendered in the configured timezone."""

    def __init__(self, fmt: str, datefmt: str, tz: str) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._tz = ZoneInfo(tz)

    def formatTime(  # noqa: N802 (overrides logging.Formatter.formatTime)
        self, record: logging.LogRecord, datefmt: str | None = None
    ) -> str:
        dt = datetime.fromtimestamp(record.created, tz=self._tz)
        return dt.strftime(datefmt or self.datefmt or DATE_FORMAT)


# Third-party loggers that ship their own StreamHandler at import time, which
# produces a second, differently-formatted copy of every line. We drop those
# handlers and let the records propagate to our single root handler instead.
_SELF_HANDLED_LOGGERS = ("LiteLLM", "litellm")


def _route_through_root(*logger_names: str) -> None:
    for name in logger_names:
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with timezone-aware, human-readable output.

    Uses force=True so our handler/formatter wins even if a dependency (uvicorn,
    litellm) already touched the root logger, and so repeat calls stay idempotent
    instead of stacking handlers.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_TimezoneFormatter(LOG_FORMAT, DATE_FORMAT, settings.timezone))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    _route_through_root(*_SELF_HANDLED_LOGGERS)


def align_uvicorn_loggers() -> None:
    """Route uvicorn's loggers through the root handler too.

    uvicorn installs its own handlers (with propagate=False) when it boots,
    which happens *after* setup_logging() runs at import time — so its access
    and error lines otherwise keep uvicorn's own format. Call this from the
    app startup hook, once uvicorn has finished configuring logging.
    """
    _route_through_root("uvicorn", "uvicorn.access", "uvicorn.error")
