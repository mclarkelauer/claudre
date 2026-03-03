"""Structured logging setup for claudre."""

from __future__ import annotations

import logging

_FMT = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(log_path: str = "", debug: bool = False) -> None:
    """Configure root logger. Call once at startup."""
    level = logging.DEBUG if debug else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_path:
        handlers.append(logging.FileHandler(log_path))

    logging.basicConfig(
        level=level,
        format=_FMT,
        datefmt=_DATE_FMT,
        handlers=handlers,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
