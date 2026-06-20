"""Async, resumable PKG downloader with Range resume, retry, and SHA256 verify."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
from loguru import logger

from . import monitoring
from .models import Game
from .progress import ProgressSink, TqdmSink

_RETRYABLE = (httpx.TransportError, httpx.TimeoutException)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _already_complete(game: Game, dest: Path, verify: bool) -> bool:
    if not (dest.exists() and game.file_size and dest.stat().st_size == game.file_size):
        return False
    if not verify or not game.sha256:
        return True
    return _sha256(dest) == game.sha256.lower()


async def _stream_attempt(
    client: httpx.AsyncClient,
    url: str,
    tmp: Path,
    *,
    desc: str,
    fallback_total: int,
    sink: ProgressSink,
    key: str,
) -> None:
    resume_from = tmp.stat().st_size if tmp.exists() else 0
    headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}

    async with client.stream("GET", url, headers=headers, follow_redirects=True) as resp:
        if resp.status_code == 416:  # already complete on the server side
            return
        if resume_from and resp.status_code == 200:  # Range ignored; restart clean
            resume_from = 0
        resp.raise_for_status()

        if resp.status_code == 206:
            content_range = resp.headers.get("Content-Range", "")
            total = (
                int(content_range.rsplit("/", 1)[-1])
                if "/" in content_range
                else resume_from + int(resp.headers.get("Content-Length", 0))
            )
        else:
            total = int(resp.headers.get("Content-Length", 0)) or fallback_total

        sink.start(key, desc, total or None, initial=resume_from)
        with tmp.open("ab" if resume_from else "wb") as fh:
            async for chunk in resp.aiter_bytes(chunk_size=1024 * 256):
                fh.write(chunk)
                sink.advance(key, len(chunk))


async def download_game(
    game: Game,
    output_dir: Path,
    *,
    client: httpx.AsyncClient | None = None,
    verify: bool = True,
    sink: ProgressSink | None = None,
    max_retries: int = 5,
) -> Path:
    url = game.download_url
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / game.filename
    sink = sink if sink is not None else TqdmSink()
    key = game.filename

    if await asyncio.to_thread(_already_complete, game, dest, verify):
        logger.info("Skipping {} (already downloaded)", game.name)
        return dest

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0))
    tmp = dest.with_suffix(dest.suffix + ".part")
    fallback_total = game.file_size or 0

    resume_bytes = tmp.stat().st_size if tmp.exists() else 0
    monitoring.add_breadcrumb(
        category="download",
        message=("Resuming" if resume_bytes else "Starting") + f" {game.title_id}",
        data={"resume_from": resume_bytes, "url": url},
    )

    try:
        for attempt in range(1, max_retries + 1):
            try:
                await _stream_attempt(
                    client, url, tmp, desc=game.name[:40],
                    fallback_total=fallback_total, sink=sink, key=key,
                )
                break
            except _RETRYABLE as exc:
                if attempt == max_retries:
                    raise
                wait = min(2**attempt, 30)  # .part is kept, so the retry resumes
                monitoring.add_breadcrumb(
                    category="download",
                    level="warning",
                    message=f"{type(exc).__name__} on attempt {attempt}/{max_retries}, "
                    f"retrying in {wait}s",
                    data={"error": str(exc)},
                )
                logger.warning(
                    "{}: {}, retrying in {}s ({}/{})...",
                    game.title_id, type(exc).__name__, wait, attempt, max_retries,
                )
                await asyncio.sleep(wait)
    finally:
        sink.finish(key)
        if owns_client:
            await client.aclose()

    # Re-hash from disk: an in-memory digest can't survive a cross-run resume.
    if verify and game.sha256:
        actual = await asyncio.to_thread(_sha256, tmp)
        if actual != game.sha256.lower():
            tmp.unlink(missing_ok=True)
            raise ValueError(
                f"SHA256 mismatch for {game.name}: expected {game.sha256}, got {actual}"
            )

    tmp.replace(dest)
    return dest


async def download_games(
    games: list[Game],
    output_dir: Path,
    *,
    concurrency: int = 3,
    verify: bool = True,
    sink: ProgressSink | None = None,
) -> list[Path]:
    """Download many games concurrently, capped at ``concurrency`` in flight."""
    targets = [g for g in games if g.downloadable]
    sink = sink if sink is not None else TqdmSink()
    sem = asyncio.Semaphore(concurrency)
    results: list[Path] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0)) as client:

        async def worker(game: Game) -> None:
            async with sem:
                with monitoring.isolation_scope() as scope:
                    scope.set_tag("title_id", game.title_id)
                    scope.set_tag("region", game.region)
                    scope.set_context(
                        "game",
                        {
                            "title_id": game.title_id,
                            "name": game.name,
                            "region": game.region,
                            "url": game.pkg_direct_link,
                            "file_size": game.file_size,
                        },
                    )
                    try:
                        results.append(
                            await download_game(game, output_dir, client=client, verify=verify, sink=sink)
                        )
                    except Exception as exc:  # report every failure, but keep going
                        monitoring.capture_exception(exc)
                        logger.error("Failed {} ({}): {}", game.title_id, game.name, exc)

        await asyncio.gather(*(worker(g) for g in targets))

    return results
