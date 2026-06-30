"""Structured logging helpers for collector services.

This file is intentionally not exposed as a Python package named ``logging`` to
avoid shadowing the standard library. Import it by path from application entry
points if a shared logger helper is needed.
"""

from __future__ import annotations

import logging
from typing import Any


def configure_logger(name: str = "quodeadvisors", level: int = logging.INFO) -> logging.Logger:
    """Create a stream logger with a stable production-friendly format."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    return logger


def structured_log(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit a compact structured log line without adding a JSON dependency."""
    suffix = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
    message = f"event={event} {suffix}".rstrip()
    logger.log(level, message)
