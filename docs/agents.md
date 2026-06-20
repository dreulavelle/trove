# Scripting & agents

`nps` is a plain CLI, so anything that can run a command and parse JSON can drive
it — shell scripts, CI jobs, or an AI agent with shell access. No extra server or
SDK is required.

## JSON output

Add `--json` to any search to get a JSON array on stdout instead of the human
listing. Logs are suppressed in this mode, so stdout carries the payload alone
and is safe to pipe.

```bash
nps "tearaway" --json
nps -p PS3 -t DLCS "persona" --json
```

```json
[
  {
    "title_id": "PCSA00142",
    "name": "Tearaway Soundtrack (with bonus tracks)",
    "region": "US",
    "platform": "PSV",
    "content_type": "GAMES",
    "content_subtype": null,
    "downloadable": true,
    "url": "http://zeus.dl.playstation.net/cdn/UP9000/PCSA00142_00/...pkg",
    "file_size": 207406320,
    "sha256": "530995daf2f7358807eb3d4c4f1115cb927e2b81cf99def2e1749cb4840276fd",
    "content_id": "UP9000-PCSA00142_00-GTEARAWAYSOUND01",
    "last_modification_date": "2017-10-19 06:44:20"
  }
]
```

`--json` lists; it never downloads. Combine it with `-p`/`-t`/`-r` to scope the
results, then act on the `url` and `sha256` fields yourself.

### Fields

| Field | Notes |
| --- | --- |
| `title_id`, `name`, `region` | Catalog identity. |
| `platform`, `content_type` | The dataset the row came from. |
| `content_subtype` | Free-text sub-type, when the dataset provides one. |
| `downloadable` | `true` when a usable PKG link exists. |
| `url` | Direct PKG link, or `null` when not downloadable. |
| `file_size` | Bytes, or `null` if the catalog omits it. |
| `sha256` | Expected hash for verification, or `null`. |
| `content_id` | Sony content ID. |
| `last_modification_date` | As published by NoPayStation. |

## Patterns

Pick the largest downloadable match with `jq`:

```bash
nps "tearaway" --json \
  | jq 'map(select(.downloadable)) | max_by(.file_size) | .url'
```

Download everything that matched without re-querying:

```bash
nps "patapon" -p PSP --all -o ./downloads
```

## For AI agents

A documented `--json` CLI is usually all an agent needs: it can search, read the
structured result, and either download in-process (`nps <id> -o <dir>`) or hand
the `url`/`sha256` to its own fetcher. There is no dedicated MCP server today —
if a sandboxed, shell-less agent ever needs one, `nps --json` is the contract it
would wrap.
