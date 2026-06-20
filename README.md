# Trove

A fast CLI and TUI for browsing and downloading the
[NoPayStation](https://nopaystation.com) catalog — PSV, PSP, PS3, PSX and PSM.
Downloads resume, retry, and verify SHA-256, or hand off to a running aria2.

## Install

```bash
uv sync                       # core
uv sync --extra monitoring    # + optional GlitchTip/Sentry error reporting
```

## CLI

```bash
nps "tearaway"                              # search PSV games
nps -p PS3 -t DLCS "persona"                 # any platform / type
nps "PCSC80018" -o ./downloads               # download
nps "patapon" -p PSP --all                   # download every match
nps -a --aria2-rpc URL --aria2-secret TOKEN  # hand off to aria2
```

## TUI

```bash
trove
```

Search, multi-select (selections survive searches), and download with live
progress or aria2 hand-off.

## Notes

- Catalogs come from NoPayStation and are cached for 30 days
  (`--refresh`, `--reset-cache`, `--offline`). The cache lives in the OS cache
  dir; set `NPS_CACHE_DIR` to change it. Downloads default to `./downloads`.
- aria2 (`--aria2-rpc` / `ARIA2_RPC_URL`) and error reporting (`GLITCHTIP_DSN`)
  are optional.

## Develop

```bash
uv run pytest
uv run ruff check .
```

Trove only retrieves what NoPayStation publishes; how you use it is on you.
