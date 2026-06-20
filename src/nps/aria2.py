"""aria2 hand-off: write an input file, run a local aria2c, or push over RPC."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx
from loguru import logger

from . import monitoring
from .models import Game


def write_aria2_input(games: list[Game], output_dir: Path, dest: Path) -> int:
    """Write an aria2 ``--input-file`` (``aria2c -c -i <dest>``); return entry count."""
    targets = [g for g in games if g.downloadable]
    lines: list[str] = []
    for g in targets:
        lines.append(g.download_url)
        lines.append(f"  out={g.filename}")
        lines.append(f"  dir={output_dir}")
        if g.sha256:
            lines.append(f"  checksum=sha-256={g.sha256.lower()}")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(targets)


def run_aria2c(games: list[Game], output_dir: Path, *, concurrency: int = 3) -> int:
    """Download matches now with a local ``aria2c`` (single command).

    Writes a temporary input file and hands it to ``aria2c -c``; aria2c streams
    its own progress and verifies the embedded SHA-256 checksums. Returns aria2c's
    exit code. Raises ``FileNotFoundError`` if ``aria2c`` isn't on PATH.
    """
    aria2c = shutil.which("aria2c")
    if aria2c is None:
        raise FileNotFoundError(
            "aria2c not found on PATH; install aria2, or use --aria2 FILE to export an input file."
        )
    with tempfile.NamedTemporaryFile("w", suffix=".aria2.txt", delete=False, encoding="utf-8") as fh:
        tmp = Path(fh.name)
    try:
        count = write_aria2_input(games, output_dir, tmp)
        logger.info("Handing {} download(s) to aria2c (-j{}).", count, concurrency)
        return subprocess.run([aria2c, "-c", f"-j{concurrency}", "-i", str(tmp)]).returncode
    finally:
        tmp.unlink(missing_ok=True)


async def add_to_aria2_rpc(
    games: list[Game],
    rpc_url: str,
    *,
    secret: str | None = None,
    remote_dir: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """Queue downloads on a running aria2 daemon; return the assigned GIDs.

    ``remote_dir`` is a path on the aria2 host; omit it for the daemon's default.
    """
    targets = [g for g in games if g.downloadable]
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    gids: list[str] = []
    try:
        for g in targets:
            options: dict[str, str] = {"out": g.filename, "continue": "true"}
            if remote_dir is not None:
                options["dir"] = remote_dir
            if g.sha256:
                options["checksum"] = f"sha-256={g.sha256.lower()}"

            params: list = []  # aria2.addUri params: [secret?, [uris], options]
            if secret:
                params.append(f"token:{secret}")
            params.append([g.download_url])
            params.append(options)
            payload = {"jsonrpc": "2.0", "id": g.title_id, "method": "aria2.addUri", "params": params}
            try:
                resp = await client.post(rpc_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    logger.error("aria2 rejected {}: {}", g.title_id, data["error"])
                    continue
                gids.append(data["result"])
                logger.info("Queued {} ({}) -> aria2 gid {}", g.title_id, g.name, data["result"])
            except Exception as exc:
                monitoring.capture_exception(exc)
                logger.error("Failed to queue {} ({}): {}", g.title_id, g.name, exc)
    finally:
        if owns_client:
            await client.aclose()
    return gids
