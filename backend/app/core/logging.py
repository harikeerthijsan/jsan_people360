"""Centralised logging configuration.

Two formatters are provided:

* ``console`` -- human readable, used for local development.
* ``json``    -- one JSON object per line, suitable for log shippers in
  staging/production.

Every record is automatically enriched with the current request id so that a
single request can be traced across the request log, service logs and the
exception log.
"""

from __future__ import annotations

import json
import logging
import logging.config
import sys
from typing import Any

from app.core.config import settings
from app.core.context import get_actor_id, get_request_id

_RESERVED_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class RequestContextFilter(logging.Filter):
    """Attach request-scoped identifiers to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        actor_id = get_actor_id()
        record.actor_id = str(actor_id) if actor_id else "-"
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON documents."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "actor_id": getattr(record, "actor_id", "-"),
            "service": settings.APP_NAME,
            "environment": settings.APP_ENV,
        }

        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Compact, readable formatter for local development."""

    _FORMAT = "%(asctime)s | %(levelname)-8s | %(request_id)s | %(name)s | %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self._FORMAT, datefmt="%Y-%m-%d %H:%M:%S")


def configure_logging() -> None:
    """Install the logging configuration for the whole process."""

    formatter = "json" if settings.LOG_FORMAT == "json" else "console"

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_context": {"()": RequestContextFilter},
            },
            "formatters": {
                "json": {"()": JsonFormatter},
                "console": {"()": ConsoleFormatter},
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": formatter,
                    "filters": ["request_context"],
                },
            },
            "root": {
                "handlers": ["default"],
                "level": settings.LOG_LEVEL,
            },
            "loggers": {
                # Uvicorn writes its own access log; ours is richer, so silence it.
                "uvicorn.access": {"handlers": ["default"], "level": "WARNING", "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": settings.LOG_LEVEL, "propagate": False},
                "sqlalchemy.engine": {
                    "handlers": ["default"],
                    "level": "INFO" if settings.DB_ECHO else "WARNING",
                    "propagate": False,
                },
                "alembic": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "app": {"handlers": ["default"], "level": settings.LOG_LEVEL, "propagate": False},
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced application logger."""
    return logging.getLogger(name if name.startswith("app") else f"app.{name}")
