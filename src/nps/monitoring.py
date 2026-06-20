"""Optional error monitoring (GlitchTip / Sentry), lazily loaded.

The rest of the app calls these helpers unconditionally; they are no-ops unless
``init()`` activates monitoring — which needs ``GLITCHTIP_DSN`` set and the
``monitoring`` extra installed (``uv sync --extra monitoring``).
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from typing import Any

from loguru import logger

_sentry: Any = None


def init() -> bool:
    """Activate monitoring if a DSN is set and sentry-sdk is importable."""
    global _sentry
    dsn = os.getenv("GLITCHTIP_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.loguru import LoguruIntegration
    except ImportError:
        logger.warning("GLITCHTIP_DSN is set but sentry-sdk is missing; run: uv sync --extra monitoring")
        return False

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.01")),
        auto_session_tracking=False,  # GlitchTip does not support sessions
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("SENTRY_RELEASE"),
        attach_stacktrace=True,
        debug=os.getenv("SENTRY_DEBUG", "").lower() in {"1", "true", "yes"},
        integrations=[LoguruIntegration(event_level=None)],
    )
    _sentry = sentry_sdk
    return True


def capture_exception(exc: BaseException) -> None:
    if _sentry is not None:
        _sentry.capture_exception(exc)


def add_breadcrumb(**kwargs: Any) -> None:
    if _sentry is not None:
        _sentry.add_breadcrumb(**kwargs)


class _NullScope:
    def set_tag(self, *_: Any) -> None: ...
    def set_context(self, *_: Any) -> None: ...


@contextlib.contextmanager
def isolation_scope() -> Iterator[Any]:
    if _sentry is not None:
        with _sentry.isolation_scope() as scope:
            yield scope
    else:
        yield _NullScope()
