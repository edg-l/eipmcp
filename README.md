# eipmcp

MCP server that mirrors Ethereum EIP/ERC repos and consensus/execution specs
locally, indexes them in SQLite, and exposes `get`, `list`, `search`, `diff`,
and `requires` tools.

## Tracked repos

| key                | source                                  | indexed as |
| ------------------ | --------------------------------------- | ---------- |
| `eips`             | github.com/ethereum/EIPs                | EIPs (numbered, frontmatter) |
| `ercs`             | github.com/ethereum/ERCs                | EIPs (numbered, frontmatter) |
| `consensus-specs`  | github.com/ethereum/consensus-specs     | Specs (path-based) |
| `execution-specs`  | github.com/ethereum/execution-specs     | Specs + tests (path-based; `src/ethereum`, `docs`, `tests`) |

`tests_for_eip(number)` reads from `execution-specs/tests/` — that's where the
new EL test framework lives. `ethereum/execution-spec-tests` is on its way to
retirement and is not tracked.

Data lives at `$XDG_DATA_HOME/eipmcp` (override with `EIPMCP_DATA_DIR`).
Repos are cloned with `--filter=blob:none` for a smaller working tree.

## Install

End-user install (puts `eipmcp` on your PATH via `~/.local/bin`):

```bash
git clone https://github.com/edg-l/eipmcp && cd eipmcp
uv tool install .
```

Upgrade later with `uv tool upgrade eipmcp` (or `uv tool install -e .` from a
checkout for live edits). Uninstall with `uv tool uninstall eipmcp`.

Dev install (editable, for hacking on the code):

```bash
uv venv && uv pip install -e '.[dev]'
```

## First sync

```bash
eipmcp sync eips             # one repo
eipmcp sync                  # all four repos
```

Clones ~150 MB on first run and streams git progress to stderr. Subsequent
`sync` calls do `git fetch` + reindex only the changed files.

## Run as MCP server

```bash
eipmcp serve                 # stdio transport
```

Register with Claude Code (user scope = available in every project):

```bash
claude mcp add --scope user eipmcp -- eipmcp serve
```

With auto-sync on stale data (daily):

```bash
claude mcp add --scope user -e EIPMCP_SYNC_TTL=24h eipmcp -- eipmcp serve
```

Or paste into `~/.claude.json` / project config:

```json
{
  "mcpServers": {
    "eipmcp": {
      "command": "eipmcp",
      "args": ["serve"],
      "env": { "EIPMCP_SYNC_TTL": "24h" }
    }
  }
}
```

## Tools exposed

EIP-format (numbered, YAML frontmatter):

- `get_eip(number, repo='eips')` — full body + frontmatter (incl. `description`)
- `list_eips(repo?, status?, type?, category?)`
- `search_eips(query, limit=50, snippet_words=12)` — SQLite FTS5, bm25-ranked, returns snippets
- `diff_eip(number, since='previous_sync', until?, repo='eips', context=3)`
- `eip_requires(number)` / `eip_required_by(number)`

Cross-references (EIP↔spec / EIP↔test):

- `eip_referenced_in(number, repo?)` — files mentioning `EIP-<n>` in body or path
- `refs_in_source(repo, path)` — EIP numbers cited inside one file
- `tests_for_eip(number)` — files under `execution-specs/tests/` referencing this EIP

Hardforks:

- `get_hardfork(name)` — resolves codenames (`pectra`, `fusaka`, `cancun`, ...) to Meta EIP(s) and the EIPs they include
- `list_hardforks()` — every indexed Meta EIP

Open PRs (uses local `gh` CLI):

- `pending_prs_for_eip(number, repo='eips', limit=30)`
- `pending_prs_for_spec(repo, path, limit=30)`

Path-based specs (consensus-specs / execution-specs):

- `list_specs(repo, glob?)`
- `get_spec(repo, path)`
- `diff_spec(repo, path, since='previous_sync', until?)`

Repo management:

- `sync_repo(repo)` / `sync_all()` / `list_repos()`

## Resources

- `eip://{number}` — formatted EIP doc (URI scheme for MCP clients/IDEs)
- `erc://{number}` — formatted ERC doc

## `since` values for `diff_*`

- `'previous_sync'` (default): diff against the sync immediately before the latest
- `'last_sync'`: diff between latest sync commit and current HEAD
- any commit SHA / tag / branch ref

## Auto-sync TTL

By default no automatic pulls. Set `EIPMCP_SYNC_TTL` to enable auto-sync on
server start when any repo is stale:

```bash
EIPMCP_SYNC_TTL=24h eipmcp serve     # accepts 30s, 5m, 24h, 1d, or seconds
```

## Dev

```bash
uv pip install -e '.[dev]'
pytest
```
