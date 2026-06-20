# Usage

## CLI (`nps`)

```bash
nps "tearaway"                               # search PSV games by name or Title ID
nps -p PS3 -t DLCS "persona"                 # pick platform and content type
nps "tearaway" --list                        # list matches, don't download
nps "PCSC80018" -o ./downloads               # download a single match
nps "patapon" -p PSP --all                   # download every downloadable match
nps "tearaway" --json                        # machine-readable output (see Agents)
```

### Options

| Flag | Meaning |
| --- | --- |
| `query` | Title ID or name, case-insensitive. |
| `-p, --platform` | `PSV` (default), `PSP`, `PS3`, `PSX`, `PSM`. |
| `-t, --type` | `GAMES` (default), `DLCS`, `THEMES`, `UPDATES`, `DEMOS`, `AVATARS`. |
| `-r, --region` | Region to include, repeatable (e.g. `-r US -r EU`). |
| `-o, --output` | Output directory (default `./downloads`). |
| `-l, --list` | List matches without downloading. |
| `-a, --all` | Download every downloadable match. |
| `--json` | Print matches as JSON; no download. |
| `-c, --concurrency` | Max concurrent downloads (default 3). |
| `--no-verify` | Skip SHA-256 verification. |
| `--refresh` | Force-refresh the catalog from NoPayStation. |
| `--reset-cache` | Delete all cached catalogs and exit. |
| `--offline` | Use only the cached catalog (no network). |

NoPayStation doesn't publish every platform × type combination; unavailable
combinations return nothing.

## TUI (`trove`)

```bash
trove
```

Search, multi-select (selections survive searches), and download with live
progress or aria2 hand-off. Press `/` to focus search; the result table keeps
the action keys (download, select) live while you browse.

## aria2 hand-off

Instead of downloading in-process, hand matches to [aria2](https://aria2.github.io/):

```bash
nps "patapon" -p PSP --all --aria2 patapon.txt   # write an aria2 input file
aria2c -c -j3 -i patapon.txt

nps "patapon" -p PSP --all \
  --aria2-rpc http://localhost:6800/jsonrpc \
  --aria2-secret TOKEN                            # push to a running daemon
```

`--aria2-rpc` and `--aria2-secret` fall back to `ARIA2_RPC_URL` /
`ARIA2_RPC_SECRET`. Use `--aria2-dir` to set the download directory on the
aria2 host.

## Caching & configuration

- Catalogs come from NoPayStation and are cached for 30 days, then revalidated
  with an ETag (an unchanged dataset costs a `304`, not a refetch).
- The cache lives in the OS cache directory; set `NPS_CACHE_DIR` to relocate it.
- Optional error reporting goes to GlitchTip/Sentry via `GLITCHTIP_DSN` (install
  the `monitoring` extra).
