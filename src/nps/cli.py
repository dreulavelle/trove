"""Command-line interface for the nps catalog downloader."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from loguru import logger

from . import __version__
from .aria2 import add_to_aria2_rpc, run_aria2c, write_aria2_input
from .catalog import load_games, reset_cache
from .config import load_settings
from .download import download_games
from .models import ContentType, Filter, Game, Platform

_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


def parse_size(text: str) -> int:
    """Parse a size like ``2GB``, ``500MB``, or a raw byte count into bytes."""
    s = text.strip().upper()
    for unit in ("TB", "GB", "MB", "KB", "B"):
        if s.endswith(unit):
            return int(float(s[: -len(unit)].strip()) * _SIZE_UNITS[unit])
    return int(s)  # bare number = bytes


def _game_json(g: Game) -> dict[str, object]:
    """A flat, agent-friendly view of a game (stable keys, no internal model noise)."""
    return {
        "title_id": g.title_id,
        "name": g.name,
        "region": g.region,
        "platform": g.platform.value if g.platform else None,
        "content_type": g.content_type.value if g.content_type else None,
        "content_subtype": g.content_subtype,
        "downloadable": g.downloadable,
        "url": g.download_url if g.downloadable else None,
        "file_size": g.file_size,
        "sha256": g.sha256,
        "required_fw": g.required_fw,
        "content_id": g.content_id,
        "last_modification_date": g.last_modification_date,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nps", description="Trove — browse and download from NoPayStation."
    )
    p.add_argument("query", nargs="?", help="Filter by Title ID or name (case-insensitive).")
    p.add_argument("-p", "--platform", type=Platform, choices=list(Platform), default=Platform.PSV,
                   help="Console platform (default: PSV).")
    p.add_argument("-t", "--type", type=ContentType, choices=list(ContentType), default=ContentType.GAMES,
                   dest="content_type", help="Content type (default: GAMES).")
    p.add_argument("-r", "--region", action="append", help="Region to include (repeatable), e.g. US EU JP.")
    p.add_argument("--name", help="Filter by name substring only (case-insensitive).")
    p.add_argument("--title-id", dest="title_id", help="Filter by Title ID substring only.")
    p.add_argument("--max-fw", type=float, metavar="VERSION",
                   help="Only items requiring firmware <= VERSION (e.g. 3.60).")
    p.add_argument("--min-size", type=parse_size, metavar="SIZE",
                   help="Only items at least SIZE (e.g. 100MB, 2GB).")
    p.add_argument("--max-size", type=parse_size, metavar="SIZE",
                   help="Only items at most SIZE (e.g. 500MB, 4GB).")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="Output directory (default: settings download_dir, or ./downloads).")
    p.add_argument("--flat", action="store_true",
                   help="Don't split downloads into per-console subfolders.")
    p.add_argument("--local", action="store_true",
                   help="Force the built-in downloader even if an aria2 instance is configured.")
    p.add_argument("-l", "--list", action="store_true", help="List matches without downloading.")
    p.add_argument("--json", action="store_true",
                   help="Print matches as JSON (no download); for scripts and agents.")
    p.add_argument("-a", "--all", action="store_true", help="Download every downloadable match.")
    p.add_argument("-c", "--concurrency", type=int, default=None,
                   help="Max concurrent downloads (default: settings concurrency, or 3).")
    p.add_argument("--no-verify", action="store_true", help="Skip SHA256 verification.")
    p.add_argument("--refresh", action="store_true", help="Force-refresh the catalog from NoPayStation.")
    p.add_argument("--reset-cache", action="store_true", help="Delete all cached catalogs and exit.")
    p.add_argument("--offline", action="store_true", help="Use only the cached catalog (no network).")
    p.add_argument("--aria2", type=Path, metavar="FILE", help="Export matches as an aria2 input file.")
    p.add_argument("--aria2-run", action="store_true",
                   help="Download matches now via a local aria2c (single command; needs aria2c on PATH).")
    p.add_argument("--aria2-rpc", nargs="?", const="", default=None, metavar="URL",
                   help="Push to a running aria2 daemon (URL, or ARIA2_RPC_URL / saved settings).")
    p.add_argument("--aria2-secret", default=None,
                   help="aria2 RPC secret token (or ARIA2_RPC_SECRET env / saved settings).")
    p.add_argument("--aria2-dir", default=None, help="Download dir on the aria2 host (RPC mode).")
    p.add_argument("--version", action="version", version=f"nps {__version__}")
    return p


def main(argv: list[str] | None = None) -> None:
    from .observability import setup

    args = _build_parser().parse_args(argv)
    # In --json mode, logs (loguru -> tqdm.write -> stdout) would corrupt the
    # payload, so silence the console sink and let stdout carry JSON alone.
    setup(console=not args.json)

    if args.reset_cache:
        logger.info("Removed {} cached file(s).", reset_cache())
        return

    games = asyncio.run(
        load_games(args.platform, args.content_type, refresh=args.refresh, offline=args.offline)
    )
    if not games:
        if args.json:
            print("[]")
            return
        logger.warning("No catalog data for {} {}.", args.platform.value, args.content_type.value)
        return

    fkw: dict[str, object] = dict(
        query=args.query,
        title_id=args.title_id,
        name=args.name,
        regions=set(args.region) if args.region else None,
        max_fw=args.max_fw,
        min_size=args.min_size,
        max_size=args.max_size,
    )
    flt = Filter(**fkw)
    matches = flt.apply(games)

    if args.json or args.list or not (args.query or args.all):
        shown = Filter(**fkw, downloadable_only=False).apply(games)
        if args.json:
            print(json.dumps([_game_json(g) for g in shown], indent=2))
            return
        print(f"{len(shown)} match(es), {len(matches)} downloadable:\n")
        for g in shown:
            mark = " " if g.downloadable else "x"
            print(f"  [{mark}] {g.title_id}  {g.region:4}  {g.name}")
        if not (args.query or args.all):
            print("\nPass a Title ID / name, or use --all to download everything.")
        return

    if not matches:
        logger.warning("No downloadable matches.")
        return

    # Resolve effective options: explicit flag > env > saved settings > built-in default.
    settings = load_settings()
    output = (args.output or Path(settings.download_dir)).expanduser()
    concurrency = args.concurrency if args.concurrency is not None else settings.concurrency
    verify = settings.verify and not args.no_verify
    organize = settings.organize_by_platform and not args.flat
    aria2_url = (args.aria2_rpc or None) or os.getenv("ARIA2_RPC_URL") or settings.aria2_rpc_url
    aria2_secret = args.aria2_secret or os.getenv("ARIA2_RPC_SECRET") or settings.aria2_rpc_secret or None
    aria2_remote_dir = args.aria2_dir or settings.aria2_dir or None

    if args.aria2:
        count = write_aria2_input(matches, output, args.aria2, organize=organize)
        logger.info("Wrote {} entries to {}", count, args.aria2)
        logger.info("Run: aria2c -c -j{} -i {}", concurrency, args.aria2)
        return

    if args.aria2_run:
        try:
            run_aria2c(matches, output, concurrency=concurrency, organize=organize)
        except FileNotFoundError as exc:
            logger.error(str(exc))
        return

    # Use a configured/requested aria2 instance unless --local forces the built-in downloader.
    if args.aria2_rpc is not None or (aria2_url and not args.local):
        if not aria2_url:
            logger.error("aria2 requested but no URL set (--aria2-rpc URL, ARIA2_RPC_URL, or settings).")
            return
        gids = asyncio.run(
            add_to_aria2_rpc(
                matches, aria2_url, secret=aria2_secret, remote_dir=aria2_remote_dir, organize=organize
            )
        )
        logger.info("Queued {}/{} download(s) to aria2 ({}).", len(gids), len(matches), aria2_url)
        return

    logger.info("Downloading {} item(s) to {} (concurrency={})", len(matches), output, concurrency)
    asyncio.run(
        download_games(matches, output, concurrency=concurrency, verify=verify, organize=organize)
    )


if __name__ == "__main__":
    main()
