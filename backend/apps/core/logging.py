"""Structured JSON logging.

Production log aggregators are far happier parsing one JSON object per line than
a bespoke text format, and stable keys (``level``, ``logger``, ``msg``) make
alerting queries trivial.  Development keeps the human-readable formatter from
``base.LOGGING``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

# Attributes present on every LogRecord; anything else was passed via `extra`
# and is therefore interesting enough to emit.
_RESERVED = {
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
    "message",
    "module",
    "msecs",
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


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # Surface request/user correlation ids added through `extra=`.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = _serialise(value)

        return json.dumps(payload, ensure_ascii=False, default=str)


def _serialise(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_serialise(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialise(item) for key, item in value.items()}
    return str(value)


def get_logger(name: str = "lawschool") -> logging.Logger:
    """Return the project logger so `extra=` correlation ids are always emitted."""
    return logging.getLogger(name)
