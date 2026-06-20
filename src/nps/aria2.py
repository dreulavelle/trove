"""aria2 hand-off: write an input file, or push to a running daemon over RPC."""

from __future__ import annotations

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
