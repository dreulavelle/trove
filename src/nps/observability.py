"""Logging setup and UTF-8 stream config.

Optional config is read from environment variables (``LOG_LEVEL``, and the
``GLITCHTIP_DSN`` / ``SENTRY_*`` set used by :mod:`nps.monitoring`).
"""

from __future__ import annotations

import os
import sys

from loguru import logger
from tqdm import tqdm

from . import monitoring

_LOG_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan> - <level>{message}</level>"
)


def setup_logging() -> None:
    """Route loguru through tqdm.write so log lines don't corrupt progress bars."""
    logger.remove()
    logger.add(
        lambda msg: tqdm.write(msg, end=""),
        format=_LOG_FORMAT,
        level=os.getenv("LOG_LEVEL", "INFO"),
        colorize=True,
        backtrace=False,  # one clean line per error, no inlined values (leak-safe)
        diagnose=False,
    )


def _force_utf8_streams() -> None:
    # Windows consoles default to cp1252 and crash on non-Latin game names.
    for stream in (sys.stdout, sys.stderr):
        if (reconfigure := getattr(stream, "reconfigure", None)) is not None:
            reconfigure(encoding="utf-8", errors="replace")


def setup(console: bool = True) -> None:
    """Configure UTF-8 streams, logging, and (optional) error monitoring.

    ``console=False`` (for the TUI) silences the stdout sink so logs can't corrupt
    the screen.
    """
    _force_utf8_streams()
    if console:
        setup_logging()
    else:
        logger.remove()
    monitoring.init()
