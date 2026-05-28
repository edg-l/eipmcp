# eipmcp

MCP server that mirrors Ethereum EIP/ERC repos and consensus/execution specs
locally, indexes them in SQLite, and exposes `get`, `list`, `search`, `diff`,
and `requires` tools — built to aid ethrex (EL) and CL dev.

## Tracked repos

| key                | source                                  | indexed as |
| ------------------ | --------------------------------------- | ---------- |
| `eips`             | github.com/ethereum/EIPs                | EIPs (numbered, frontmatter) |
| `ercs`             | github.com/ethereum/ERCs                | EIPs (numbered, frontmatter) |
| `consensus-specs`  | github.com/ethereum/consensus-specs     | Specs (path-based) |
| `execution-specs`  | github.com/ethereum/execution-specs     | Specs (path-based) |

Data lives at `$XDG_DATA_HOME/eipmcp` (override with `EIPMCP_DATA_DIR`).
Repos are cloned with `--filter=blob:none` for a smaller working tree.

## Install

```bash
cd eipmcp
uv venv
uv pip install -e .
```

Or with plain pip: `pip install -e .`

## First sync

```bash
eipmcp sync eips             # one repo
eipmcp sync                  # all repos
```

The first clone of all four repos pulls ~150 MB. Subsequent `sync` calls do a
`git fetch` + reindex of changed files.

## Run as MCP server

```bash
eipmcp serve                 # stdio transport
```

Register with Claude Code:

```bash
claude mcp add eipmcp -- eipmcp serve
```

Or paste into `~/.claude.json` / project config:

```json
{
  "mcpServers": {
    "eipmcp": { "command": "eipmcp", "args": ["serve"] }
  }
}
```

## Tools exposed

EIP-format (numbered, YAML frontmatter):

- `get_eip(number, repo='eips')` — full body + frontmatter
- `list_eips(repo?, status?, type?, category?)`
- `search_eips(query, limit=50)`
- `diff_eip(number, since='previous_sync', until?, repo='eips', context=3)`
- `eip_requires(number)` / `eip_required_by(number)`

Path-based specs (consensus-specs / execution-specs):

- `list_specs(repo, glob?)`
- `get_spec(repo, path)`
- `diff_spec(repo, path, since='previous_sync', until?)`

Repo management:

- `sync_repo(repo)` / `sync_all()` / `list_repos()`

### `since` values for `diff_*`

- `'previous_sync'` (default): diff against the sync immediately before the latest
- `'last_sync'`: diff between latest sync commit and current HEAD (usually empty unless you just pulled)
- any commit SHA / tag / branch ref

## Dev

```bash
uv pip install -e '.[dev]'
pytest
```
