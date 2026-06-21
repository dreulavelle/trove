"""User settings, persisted as JSON in the OS config directory.

Lives next to the cache convention in :mod:`nps.catalog`: the location is the
platform's user config dir (``~/.config/trovenps`` on Linux), overridable with
``NPS_CONFIG_DIR``.
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger
from platformdirs import user_config_dir
from pydantic import BaseModel, Field, ValidationError

CONFIG_DIR = Path(os.getenv("NPS_CONFIG_DIR") or user_config_dir("trovenps"))
SETTINGS_PATH = CONFIG_DIR / "settings.json"


class Settings(BaseModel):
    """Persisted user preferences. Unknown/invalid fields fall back to defaults."""

    download_dir: str = "downloads"
    concurrency: int = Field(default=3, ge=1, le=16)
    verify: bool = True
    region: str = ""


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    """Read settings from ``path``; return defaults if missing or malformed."""
    try:
        return Settings.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return Settings()


def save_settings(settings: Settings, path: Path = SETTINGS_PATH) -> Path:
    """Write settings to ``path`` (creating parent dirs); return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    logger.debug("Saved settings to {}", path)
    return path
