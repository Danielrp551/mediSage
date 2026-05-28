"""
Structured JSON logging with correlation IDs.

Cloud Logging parses `severity` and the JSON payload natively, so a
record looks like a regular structured log in the GCP console.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Set by `RequestContextMiddleware`; default empty when running outside a request.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class JsonFormatter(logging.Formatter):
    """One JSON object per log line, ready for Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = request_id_ctx.get()
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Attach any custom `extra={...}` fields passed to the logger.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_ATTRS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


_STANDARD_LOG_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "taskName",
}


def configure_logging(level: str = "INFO") -> None:
    """Replace the root handler with the JSON formatter. Idempotent."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Quiet down noisy libraries; surface them via `LOG_LEVEL=DEBUG` if needed.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
