"""Structured logging setup for claudre."""

from __future__ import annotations

import logging
from pathlib import Path

_FMT = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%dT%H:%M:%S"

_LOG_DIR = Path.home() / ".claudre"
DEFAULT_LOG_PATH = _LOG_DIR / "claudre.log"


def setup_logging(log_path: str = "", debug: bool = False) -> None:
    """Configure root logger. Call once at startup.

    Always writes DEBUG logs to ~/.claudre/claudre.log regardless of flags.
    """
    stream_level = logging.DEBUG if debug else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    # Always write debug logs to the known location
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path or str(DEFAULT_LOG_PATH))
    file_handler.setLevel(logging.DEBUG)
    handlers.append(file_handler)

    logging.basicConfig(
        level=logging.DEBUG,
        format=_FMT,
        datefmt=_DATE_FMT,
        handlers=handlers,
        force=True,
    )
    # Stream handler respects the --debug flag
    handlers[0].setLevel(stream_level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
