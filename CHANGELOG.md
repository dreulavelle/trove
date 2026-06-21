# Changelog

All notable changes to Trove are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-21

First stable release.

### Added
- Per-console download folders — `downloads/psvita`, `psp`, `ps3`, `psx`, `psm` —
  for the built-in downloader and every aria2 path. Opt out with `--flat` or the
  Settings toggle.
- A `settings.json` shared by the CLI and TUI, including an aria2 instance
  (RPC URL / secret / remote dir). A saved aria2 instance is used by default;
  `--local` forces the built-in downloader.
- Settings tab: aria2 fields, the per-console toggle, and a live
  "Current Download Location".

### Changed
- Downloads now default to per-console subfolders.
- Maturity classifier raised to Production/Stable.

## [0.5.0] — 2026-06-21

### Added
- Settings tab with persisted preferences (download folder, concurrency, verify,
  default region).
- Live per-download speed and size on the Downloads tab.
- Visual refresh: accent borders and table headers, highlighted cursor row, and a
  bold status bar.

## [0.4.0] — 2026-06-21

First PyPI release.

### Added
- `nps` CLI and `trove` Textual TUI over the cached NoPayStation catalog
  (PSV / PSP / PS3 / PSX / PSM).
- Resumable, retrying, SHA-256-verified downloads.
- aria2 hand-off: input-file export, single-command local `aria2c`, and RPC push.
- `--json` output for scripts and AI agents.
- Filters: `--max-fw` (firmware), `--min-size` / `--max-size`, `--name` /
  `--title-id`.

[1.0.0]: https://github.com/dreulavelle/trove/releases/tag/v1.0.0
[0.5.0]: https://github.com/dreulavelle/trove/releases/tag/v0.5.0
[0.4.0]: https://github.com/dreulavelle/trove/releases/tag/v0.4.0
