# eipmcp

MCP server that mirrors Ethereum EIP/ERC repos and consensus/execution specs
locally, indexes them in SQLite, and exposes `get`, `list`, `search`, `diff`,
and `requires` tools.

## Tracked repos

| key                    | source                                      | indexed as |
| ---------------------- | ------------------------------------------- | ---------- |
| `eips`                 | github.com/ethereum/EIPs                    | EIPs (numbered, frontmatter) |
| `ercs`                 | github.com/ethereum/ERCs                    | EIPs (numbered, frontmatter) |
| `consensus-specs`      | github.com/ethereum/consensus-specs         | Specs (path-based) |
| `execution-specs`      | github.com/ethereum/execution-specs         | Specs (path-based) |
| `execution-spec-tests` | github.com/ethereum/execution-spec-tests    | Specs (path-based, .py + docs) |

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

- `get_eip(number, repo='eips')` — full body + frontmatter (incl. `description`)
- `list_eips(repo?, status?, type?, category?)`
- `search_eips(query, limit=50, snippet_words=12)` — SQLite FTS5, bm25-ranked, returns snippets
- `diff_eip(number, since='previous_sync', until?, repo='eips', context=3)`
- `eip_requires(number)` / `eip_required_by(number)`

Cross-references (EIP↔spec / EIP↔test):

- `eip_referenced_in(number, repo?)` — files mentioning `EIP-<n>` in body or path
- `refs_in_source(repo, path)` — EIP numbers cited inside one file
- `tests_for_eip(number)` — execution-spec-tests files referencing this EIP

Hardforks:

- `get_hardfork(name)` — resolves codenames (`pectra`, `fusaka`, `cancun`, ...) to Meta EIP(s) and the EIPs they include
- `list_hardforks()` — every indexed Meta EIP

Open PRs (uses local `gh` CLI):

- `pending_prs_for_eip(number, repo='eips', limit=30)`
- `pending_prs_for_spec(repo, path, limit=30)`

Path-based specs (consensus-specs / execution-specs / execution-spec-tests):

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
