"""Remote NoPayStation catalog: fetch TSVs (cached), parse into ``Game`` records.

Datasets are cached for ``CACHE_TTL``; once stale they're revalidated with an
ETag conditional request, so an unchanged dataset costs a ``304``, not a refetch.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import time
from datetime import timedelta
from pathlib import Path

import httpx
from loguru import logger
from platformdirs import user_cache_dir
from pydantic import ValidationError

from .models import COLUMNS, ContentType, Game, Platform

BASE_URL = "https://nopaystation.com/tsv"
CACHE_TTL = timedelta(days=30).total_seconds()
# Default to the OS cache dir (shared across runs, outside the repo); override
# with NPS_CACHE_DIR for a fixed location.
CACHE_DIR = Path(os.getenv("NPS_CACHE_DIR") or user_cache_dir("nps"))

# NoPayStation doesn't publish every platform×type combination.
DATASETS: dict[Platform, tuple[ContentType, ...]] = {
    Platform.PSV: (
        ContentType.GAMES,
        ContentType.DLCS,
        ContentType.THEMES,
        ContentType.UPDATES,
        ContentType.DEMOS,
    ),
    Platform.PSP: (ContentType.GAMES, ContentType.DLCS),
    Platform.PS3: (
        ContentType.GAMES,
        ContentType.DLCS,
        ContentType.THEMES,
        ContentType.AVATARS,
    ),
    Platform.PSX: (ContentType.GAMES,),
    Platform.PSM: (ContentType.GAMES,),
}


def dataset_name(platform: Platform, content_type: ContentType) -> str:
    return f"{platform.value}_{content_type.value}"


def _paths(name: str) -> tuple[Path, Path]:
    return CACHE_DIR / f"{name}.tsv", CACHE_DIR / f"{name}.meta.json"


def reset_cache() -> int:
    """Delete every cached dataset; return the number of files removed."""
    if not CACHE_DIR.exists():
        return 0
    removed = 0
    for path in CACHE_DIR.glob("*"):
        path.unlink()
        removed += 1
    return removed


def _load_meta(meta_path: Path) -> dict:
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _is_fresh(meta: dict) -> bool:
    fetched_at = meta.get("fetched_at")
    return isinstance(fetched_at, (int, float)) and (time.time() - fetched_at) < CACHE_TTL


async def fetch_dataset(
    platform: Platform,
    content_type: ContentType,
    *,
    client: httpx.AsyncClient | None = None,
    refresh: bool = False,
    offline: bool = False,
) -> Path | None:
    """Path to the cached TSV, fetching/revalidating as needed.

    ``None`` if it can't be obtained (invalid combo, or offline/network failure
    with no cached fallback).
    """
    name = dataset_name(platform, content_type)
    tsv_path, meta_path = _paths(name)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if offline:
        return tsv_path if tsv_path.exists() else None

    meta = _load_meta(meta_path)
    if tsv_path.exists() and not refresh and _is_fresh(meta):
        return tsv_path

    headers: dict[str, str] = {}
    if tsv_path.exists() and not refresh and meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]

    url = f"{BASE_URL}/{name}.tsv"
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0))
    try:
        resp = await client.get(url, headers=headers, follow_redirects=True)
        if resp.status_code == 304:
            meta["fetched_at"] = time.time()
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            return tsv_path
        resp.raise_for_status()
        body = resp.content
        if not body.startswith(b"Title ID\t"):  # an error page, not a dataset
            logger.warning("{} is not a valid dataset; skipping.", name)
            return None
        tsv_path.write_bytes(body)
        meta_path.write_text(
            json.dumps(
                {
                    "etag": resp.headers.get("ETag"),
                    "last_modified": resp.headers.get("Last-Modified"),
                    "fetched_at": time.time(),
                }
            ),
            encoding="utf-8",
        )
        logger.info("Fetched {} ({:,} bytes).", name, len(body))
        return tsv_path
    except httpx.HTTPError as exc:
        if tsv_path.exists():
            logger.warning("Fetch failed for {} ({}); using cached copy.", name, exc)
            return tsv_path
        logger.error("Fetch failed for {} and no cache available: {}", name, exc)
        return None
    finally:
        if owns_client:
            await client.aclose()


def parse_tsv(path: Path, platform: Platform, content_type: ContentType) -> list[Game]:
    games: list[Game] = []
    skipped = 0
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            data: dict[str, object] = {}
            for header, field in COLUMNS.items():
                if value := row.get(header):
                    data.setdefault(field, value)  # first non-empty wins
            if not data.get("title_id"):
                continue
            data["platform"] = platform
            data["content_type"] = content_type
            try:
                games.append(Game.model_validate(data))
            except ValidationError:
                skipped += 1
    if skipped:
        logger.warning("Skipped {} malformed row(s) in {}.", skipped, dataset_name(platform, content_type))
    return games


async def load_games(
    platform: Platform,
    content_type: ContentType,
    *,
    client: httpx.AsyncClient | None = None,
    refresh: bool = False,
    offline: bool = False,
) -> list[Game]:
    """Fetch (cached) and parse a single dataset."""
    path = await fetch_dataset(
        platform, content_type, client=client, refresh=refresh, offline=offline
    )
    if path is None:
        return []
    return await asyncio.to_thread(parse_tsv, path, platform, content_type)
