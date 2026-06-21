# Trove

A fast CLI and TUI for browsing and downloading the
[NoPayStation](https://nopaystation.com) catalog — PSV, PSP, PS3, PSX and PSM.
Downloads resume, retry, and verify SHA-256, or hand off to a running aria2.

![Trove demo](docs/demo.gif)

## Quickstart

```bash
pip install trovenps   # or, from a clone: uv sync
nps "tearaway"         # search the catalog
trove                  # browse in the TUI
```

`nps` is the command line; `trove` is the full-screen TUI. Add `--json` to any
search for output a script or AI agent can parse.

## Docs

Full usage, the JSON contract, aria2 hand-off, and caching all live at
**<https://dreulavelle.github.io/trove/>**.

## Develop

```bash
uv run pytest
uv run ruff check .
```

Trove only retrieves what NoPayStation publishes; how you use it is on you.
