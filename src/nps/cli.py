"""Command-line interface for the nps catalog downloader."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from loguru import logger

from . import __version__
from .aria2 import add_to_aria2_rpc, write_aria2_input
from .catalog import load_games, reset_cache
from .download import download_games
from .models import ContentType, Filter, Platform


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
    p.add_argument("-o", "--output", type=Path, default=Path("downloads"), help="Output directory.")
    p.add_argument("-l", "--list", action="store_true", help="List matches without downloading.")
    p.add_argument("-a", "--all", action="store_true", help="Download every downloadable match.")
    p.add_argument("-c", "--concurrency", type=int, default=3, help="Max concurrent downloads.")
    p.add_argument("--no-verify", action="store_true", help="Skip SHA256 verification.")
    p.add_argument("--refresh", action="store_true", help="Force-refresh the catalog from NoPayStation.")
    p.add_argument("--reset-cache", action="store_true", help="Delete all cached catalogs and exit.")
    p.add_argument("--offline", action="store_true", help="Use only the cached catalog (no network).")
    p.add_argument("--aria2", type=Path, metavar="FILE", help="Export matches as an aria2 input file.")
    p.add_argument("--aria2-rpc", nargs="?", const=os.getenv("ARIA2_RPC_URL"), metavar="URL",
                   help="Push matches to a running aria2 daemon (URL or ARIA2_RPC_URL env).")
    p.add_argument("--aria2-secret", default=os.getenv("ARIA2_RPC_SECRET"),
                   help="aria2 RPC secret token (or ARIA2_RPC_SECRET env).")
    p.add_argument("--aria2-dir", help="Download dir on the aria2 host (RPC mode).")
    p.add_argument("--version", action="version", version=f"nps {__version__}")
    return p


def main(argv: list[str] | None = None) -> None:
    from .observability import setup

    setup()
    args = _build_parser().parse_args(argv)

    if args.reset_cache:
        logger.info("Removed {} cached file(s).", reset_cache())
        return

    games = asyncio.run(
        load_games(args.platform, args.content_type, refresh=args.refresh, offline=args.offline)
    )
    if not games:
        logger.warning("No catalog data for {} {}.", args.platform.value, args.content_type.value)
        return

    flt = Filter(query=args.query, regions=set(args.region) if args.region else None)
    matches = flt.apply(games)

    if args.list or not (args.query or args.all):
        shown = Filter(query=args.query, regions=flt.regions, downloadable_only=False).apply(games)
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

    if args.aria2:
        count = write_aria2_input(matches, args.output, args.aria2)
        logger.info("Wrote {} entries to {}", count, args.aria2)
        logger.info("Run: aria2c -c -j{} -i {}", args.concurrency, args.aria2)
        return

    if args.aria2_rpc:
        gids = asyncio.run(
            add_to_aria2_rpc(
                matches, args.aria2_rpc, secret=args.aria2_secret, remote_dir=args.aria2_dir
            )
        )
        logger.info("Queued {}/{} download(s) to aria2.", len(gids), len(matches))
        return

    logger.info(
        "Downloading {} item(s) to {} (concurrency={})", len(matches), args.output, args.concurrency
    )
    asyncio.run(
        download_games(matches, args.output, concurrency=args.concurrency, verify=not args.no_verify)
    )


if __name__ == "__main__":
    main()
