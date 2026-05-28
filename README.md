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

Auto-sync runs daily by default (see [Auto-sync TTL](#auto-sync-ttl) below).
To override:

```bash
claude mcp add --scope user -e EIPMCP_SYNC_TTL=7d eipmcp -- eipmcp serve
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
- `search_specs(query, repo?, limit=50)` — FTS5 over spec bodies; bm25-ranked + snippets
- `diff_spec(repo, path, since='previous_sync', until?)`

Recency:

- `recent_changes(days=7, repo?)` — files changed since the sync before that cutoff, with EIP status transitions

Repo management:

- `sync_repo(repo)` / `sync_all()` / `list_repos()` — `sync_all` is per-repo
  resilient (one failure doesn't block the rest; failing repo gets `{error, type}`)

## Resources

- `eip://{number}` — formatted EIP doc (URI scheme for MCP clients/IDEs)
- `erc://{number}` — formatted ERC doc
- `spec://{repo}/{path}` — one spec file's body (percent-encode `/` in the
  path if your client splits on it)

## Dependencies

`pending_prs_for_eip` and `pending_prs_for_spec` shell out to the `gh` CLI to
query GitHub's search API. Install [`gh`](https://cli.github.com/) and
authenticate (`gh auth login`) to use those tools. Everything else works
without `gh`.

## Useful calls

Concrete things this MCP unlocks. Each block shows the underlying tool call —
in Claude you'd just describe the goal in natural language.

### "What's in Pectra?"

```
get_hardfork("pectra")
```

Alias-resolves to `prague/electra`, finds Meta EIP-7600, returns all 13
included EIPs with status/type/category. One call, full fork snapshot.

### "Show me every test that touches EIP-7702"

```
tests_for_eip(7702)
```

Returns every file under `execution-specs/tests/` that mentions 7702 by path
or body. Picks up the obvious `prague/eip7702_set_code_tx/*` and the
non-obvious `amsterdam/eip7928_block_level_access_lists/test_block_access_lists_eip7702.py`
— the kind of EL-impl interaction you'd otherwise miss.

### "Which consensus-layer specs reference EIP-4844?"

```
eip_referenced_in(4844, repo="consensus-specs")
```

Returns the 9 files under `specs/deneb/` that mention it (beacon-chain,
fork-choice, polynomial-commitments, p2p-interface, light-client/*). Useful
for tracing where a CL change originates.

### "What's the spec text for execution-layer triggerable withdrawals?"

```
get_spec("execution-specs", "src/ethereum/prague/requests.py")
```

Direct read of any indexed spec file. Pair with `list_specs(repo, glob="*prague*")`
to discover what's there.

### "Find EIPs about blob transactions"

```
search_eips("blob transactions", limit=5)
```

FTS5 bm25 ranking + snippets across title, description, and body. Beats
keyword-grep through 1500+ markdown files; tokens are AND-joined and safe
against special FTS operators.

### "Where is RANDAO mixed in?" (specs, not EIPs)

```
search_specs("RANDAO mix", repo="consensus-specs")
```

Same FTS5 machinery, but over consensus-specs / execution-specs file bodies.
Use for concept-level questions that aren't tied to an EIP number.

### "What shifted in EIPs this week?"

```
recent_changes(days=7, repo="eips")
```

Anchored to the last sync before the cutoff — i.e. "what's new since you last
cared", not just what's in the git log. EIP entries include `status_was` /
`status_now` when an EIP's status flipped (Draft → Final, etc.).

### "What's pending against EIP-7702 right now?"

```
pending_prs_for_eip(7702)
```

Live GitHub search via the local `gh` CLI for open PRs that reference the EIP.
Useful for spotting "draft about to change under your feet" before you start
implementing.

### "Did EIP-7702 change since I last synced?"

```
diff_eip(7702, since="previous_sync")
```

Unified git diff between the prior sync's commit and current HEAD. Returns
`{empty: true}` when nothing changed. Pair with `diff_spec` for CL/EL spec
files.

### "What EIPs depend on EIP-1559?"

```
eip_required_by(1559)
```

Reverse graph from the `requires:` frontmatter — impact analysis without
grepping every other EIP.

### "Read the full EIP inline as a resource"

URI: `eip://7702` (or `erc://20`). Surfaces in IDEs and the Claude Code
resource picker, so the model can pull it on demand without a tool call.

## `since` values for `diff_*`

- `'previous_sync'` (default): diff against the sync immediately before the latest
- `'last_sync'`: diff between latest sync commit and current HEAD
- any commit SHA / tag / branch ref

## Auto-sync TTL

`eipmcp serve` auto-pulls stale repos on startup. **Default: `24h`.** Override
with the `EIPMCP_SYNC_TTL` env var; set to `0` to disable.

```bash
EIPMCP_SYNC_TTL=0   eipmcp serve     # disable auto-sync
EIPMCP_SYNC_TTL=7d  eipmcp serve     # weekly
EIPMCP_SYNC_TTL=30m eipmcp serve     # accepts s/m/h/d or bare seconds
```

Repos that have never been synced are **not** auto-fetched — that keeps the
first server start instant. Run `eipmcp sync` once after install to initialize;
after that, every `serve` invocation refreshes anything older than the TTL.

## Dev

```bash
uv pip install -e '.[dev]'
pytest
```
