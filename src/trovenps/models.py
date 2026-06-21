"""Dataset enums, the union ``Game`` record, and ``Filter``."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ValidationInfo, field_validator

_MISSING = {"", "MISSING"}
_IDENTITY = {"title_id", "region", "name"}

# TSV header -> field, spanning every dataset type. Both FW headers map to
# ``required_fw``; only one is present per dataset, and parsing keeps it.
COLUMNS: dict[str, str] = {
    "Title ID": "title_id",
    "Region": "region",
    "Type": "content_subtype",
    "Name": "name",
    "PKG direct link": "pkg_direct_link",
    "zRIF": "zrif",
    "RAP": "rap",
    "Download .RAP file": "rap_url",
    "Content ID": "content_id",
    "Update Version": "update_version",
    "Required FW VERSION": "required_fw",
    "Last Modification Date": "last_modification_date",
    "Original Name": "original_name",
    "File Size": "file_size",
    "SHA256": "sha256",
    "Required FW": "required_fw",
    "App Version": "app_version",
}


# StrEnum's str() is the bare value ("PSV", not "Platform.PSV"), which argparse
# uses to render choices and error messages — so --help advertises the token the
# parser actually accepts.
class Platform(StrEnum):
    PSV = "PSV"
    PSP = "PSP"
    PS3 = "PS3"
    PSX = "PSX"
    PSM = "PSM"

    @property
    def folder(self) -> str:
        """Friendly lowercase subfolder for per-console downloads (PSV -> psvita)."""
        return _PLATFORM_FOLDERS[self]


_PLATFORM_FOLDERS = {
    Platform.PSV: "psvita",
    Platform.PSP: "psp",
    Platform.PS3: "ps3",
    Platform.PSX: "psx",
    Platform.PSM: "psm",
}


class ContentType(StrEnum):
    GAMES = "GAMES"
    DLCS = "DLCS"
    THEMES = "THEMES"
    UPDATES = "UPDATES"
    DEMOS = "DEMOS"
    AVATARS = "AVATARS"


class Game(BaseModel):
    title_id: str
    region: str = ""
    name: str = ""
    pkg_direct_link: str | None = None
    zrif: str | None = None
    rap: str | None = None
    rap_url: str | None = None
    content_id: str | None = None
    update_version: str | None = None
    last_modification_date: str | None = None
    original_name: str | None = None
    file_size: int | None = None
    sha256: str | None = None
    required_fw: str | None = None
    app_version: str | None = None
    content_subtype: str | None = None
    platform: Platform | None = None  # set by the loader, not the TSV row
    content_type: ContentType | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _normalize_blanks(cls, v: object, info: ValidationInfo) -> object:
        if info.field_name in _IDENTITY:
            return "" if v is None else v
        if isinstance(v, str) and v.strip() in _MISSING:
            return None
        return v

    @field_validator("file_size", mode="before")
    @classmethod
    def _parse_size(cls, v: object) -> int | None:
        text = str(v).strip() if v is not None else ""
        return int(text) if text.isdigit() else None  # tolerate junk like "4.7"

    @property
    def downloadable(self) -> bool:
        return bool(self.pkg_direct_link and self.pkg_direct_link.startswith("http"))

    @property
    def download_url(self) -> str:
        if self.pkg_direct_link is None or not self.downloadable:
            raise ValueError(f"{self.title_id} ({self.name}) has no PKG link")
        return self.pkg_direct_link

    @property
    def filename(self) -> str:
        return f"{self.content_id or f'{self.title_id}_{self.region}'}.pkg"

    @property
    def identity(self) -> str:
        """Canonical key for dedup and selection (NoPayStation lists some dupes)."""
        return f"{self.title_id}|{self.region}|{self.content_id or self.name}"


def dest_dir(base: Path, game: Game, organize: bool) -> Path:
    """Where ``game`` is saved locally: ``base/<console>`` when organizing, else ``base``."""
    return base / game.platform.folder if (organize and game.platform) else base


def parse_fw(value: str | None) -> float | None:
    """A firmware string (``"3.60"``, ``"0"``) as a float, or ``None`` if unparseable."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class Filter(BaseModel):
    """Game selection criteria; unset fields are ignored."""

    query: str | None = None
    title_id: str | None = None
    name: str | None = None
    regions: set[str] | None = None
    max_fw: float | None = None
    min_size: int | None = None
    max_size: int | None = None
    downloadable_only: bool = True

    @field_validator("regions", mode="before")
    @classmethod
    def _upper_regions(cls, v: object) -> object:
        if isinstance(v, (set, list, tuple)):
            return {str(r).upper() for r in v}
        return v

    def matches(self, game: Game) -> bool:
        if self.downloadable_only and not game.downloadable:
            return False
        if self.regions and game.region.upper() not in self.regions:
            return False
        if self.title_id and self.title_id.lower() not in game.title_id.lower():
            return False
        if self.name and self.name.lower() not in game.name.lower():
            return False
        if self.min_size is not None and (game.file_size is None or game.file_size < self.min_size):
            return False
        if self.max_size is not None and (game.file_size is None or game.file_size > self.max_size):
            return False
        if self.max_fw is not None:
            fw = parse_fw(game.required_fw)  # unknown firmware is excluded, not assumed safe
            if fw is None or fw > self.max_fw:
                return False
        if self.query:
            q = self.query.lower()
            if q not in game.title_id.lower() and q not in game.name.lower():
                return False
        return True

    def apply(self, games: list[Game]) -> list[Game]:
        return [g for g in games if self.matches(g)]
