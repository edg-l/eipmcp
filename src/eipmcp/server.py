"""MCP server exposing EIP/spec tools and resources."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import github_api, hardforks, recent, repos, storage, sync
from .config import REPOS

mcp = FastMCP("eipmcp")


def _resolve_since(repo_key: str, since: str | None) -> str | None:
    if since is None or since == "previous_sync":
        with storage.connect() as conn:
            prev = storage.previous_sync(conn, repo_key)
        return prev["commit_sha"] if prev else None
    if since == "last_sync":
        with storage.connect() as conn:
            last = storage.last_sync(conn, repo_key)
        return last["commit_sha"] if last else None
    return since


# ---------- EIP tools ----------

@mcp.tool()
def get_eip(number: int, repo: str = "eips") -> dict[str, Any]:
    """Fetch one EIP/ERC with full body, frontmatter, and parsed `requires` list.

    Use when you need the actual spec text. For summary-only listings call
    `list_eips`. repo: 'eips' (default) or 'ercs'.
    """
    with storage.connect() as conn:
        row = storage.get_eip(conn, number, repo=repo)
    if not row:
        return {"error": f"EIP-{number} not found in repo '{repo}'. Run `sync` first?"}
    return row


@mcp.tool()
def list_eips(
    repo: str | None = None,
    status: str | None = None,
    type: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """List EIP summaries (number, title, description, status, type, category).

    Cheap discovery call — filter by repo / status / type / category to scope.
    Use before `get_eip` when you don't already know the number.
    """
    with storage.connect() as conn:
        return storage.list_eips(conn, repo=repo, status=status, type_=type, category=category)


@mcp.tool()
def search_eips(query: str, limit: int = 50, snippet_words: int = 12) -> list[dict[str, Any]]:
    """Ranked full-text search across EIP title, description, and body.

    Returns relevance-ranked matches with highlighted snippets. Use when you
    don't know the EIP number — e.g. 'EIPs about blob mempool', 'withdrawals
    queue'. Multi-word queries match all tokens.
    """
    with storage.connect() as conn:
        return storage.search_eips(conn, query, limit=limit, snippet_words=snippet_words)


@mcp.tool()
def diff_eip(
    number: int,
    since: str | None = None,
    until: str | None = None,
    repo: str = "eips",
    context: int = 3,
) -> dict[str, Any]:
    """Unified git diff for one EIP between two revisions.

    Use to see how an EIP shifted since the last sync, or between any two refs.

    since: 'previous_sync' (default — the sync before the latest),
           'last_sync' (latest sync vs current HEAD),
           or any git rev (SHA, tag, branch).
    until: any git rev; defaults to current HEAD.
    """
    spec = repos.get_repo(repo)
    repo_path = repos.ensure_clone(spec)
    with storage.connect() as conn:
        row = storage.get_eip(conn, number, repo=repo)
    if not row:
        return {"error": f"EIP-{number} not found. Sync first."}
    file_rel = row["file_path"]
    old = _resolve_since(repo, since)
    if old is None:
        return {"error": "No prior sync recorded; nothing to diff against."}
    new = until or repos.head(repo_path)
    patch = repos.diff(repo_path, old, new, file_rel=file_rel, context=context)
    return {
        "number": number, "file": file_rel,
        "from": old, "to": new,
        "diff": patch, "empty": not patch.strip(),
    }


@mcp.tool()
def eip_requires(number: int, repo: str = "eips") -> list[int]:
    """EIPs this EIP explicitly depends on (from its `requires:` frontmatter).

    Use when planning what to read before tackling a new EIP.
    """
    with storage.connect() as conn:
        row = storage.get_eip(conn, number, repo=repo)
    return list(row["requires"]) if row else []


@mcp.tool()
def eip_required_by(number: int, repo: str = "eips") -> list[dict[str, Any]]:
    """Reverse of `eip_requires`: every EIP that lists this one in `requires:`.

    Use for impact analysis ('what depends on EIP-N?').
    """
    with storage.connect() as conn:
        return storage.required_by(conn, number, repo=repo)


# ---------- Cross-reference tools ----------

@mcp.tool()
def eip_referenced_in(number: int, repo: str | None = None) -> list[dict[str, Any]]:
    """Files (specs, tests, other EIPs) that mention `EIP-<number>` in body or path.

    Catches prose references the formal `requires:` graph misses — useful for
    tracing where an EIP is actually implemented, specified, or tested.
    Filter by source repo (e.g. 'consensus-specs', 'execution-specs', 'eips').
    """
    with storage.connect() as conn:
        return storage.refs_for_eip(conn, number, repo=repo)


@mcp.tool()
def refs_in_source(repo: str, path: str) -> list[int]:
    """The EIPs mentioned inside one file (reverse of `eip_referenced_in`).

    Pass the same (repo, path) you'd give `get_spec`. Use to summarise what an
    unfamiliar spec or test file relates to.
    """
    with storage.connect() as conn:
        return storage.refs_in_source(conn, repo, path)


@mcp.tool()
def tests_for_eip(number: int) -> list[dict[str, Any]]:
    """Test files under execution-specs/tests/ that exercise or reference an EIP.

    Matches both `tests/<fork>/eip<n>_*/` directories and in-body mentions —
    catches cross-fork interactions (e.g. EIP-7702 referenced by Amsterdam's
    block-access-list tests). Use to find conformance tests when implementing.
    """
    with storage.connect() as conn:
        all_refs = storage.refs_for_eip(conn, number, repo="execution-specs")
    return [r for r in all_refs if r["source_path"].startswith("tests/")]


# ---------- Hardfork tools ----------

@mcp.tool()
def get_hardfork(name: str) -> dict[str, Any]:
    """Resolve a fork codename to its Meta EIP(s) and the EIPs it bundles.

    Accepts aliases: pectra↔prague↔electra, fusaka↔fulu↔osaka,
    glamsterdam↔amsterdam, cancun↔deneb, shanghai↔capella, merge↔paris↔bellatrix.
    Use to answer 'what's in fork X?' in one call.
    """
    return hardforks.lookup(name)


@mcp.tool()
def list_hardforks() -> list[dict[str, Any]]:
    """All indexed Meta EIPs — the universe of forks `get_hardfork` can resolve."""
    return hardforks.list_all()


# ---------- Open-PR tools ----------

@mcp.tool()
def pending_prs_for_eip(number: int, repo: str = "eips", limit: int = 30) -> list[dict[str, Any]]:
    """Open pull requests against `repo` that mention EIP-<number>.

    Live GitHub query (not from the local index). Use to spot in-flight changes
    before relying on the indexed version of an EIP.
    """
    return github_api.open_prs_for_eip(number, repo_key=repo, limit=limit)


@mcp.tool()
def pending_prs_for_spec(repo: str, path: str, limit: int = 30) -> list[dict[str, Any]]:
    """Open pull requests against `repo` matching the basename of `path`.

    Approximate file-touched filter (GitHub search has no exact one). Live query.
    """
    return github_api.open_prs_for_path(repo, path, limit=limit)


# ---------- Spec tools ----------

@mcp.tool()
def list_specs(repo: str, glob: str | None = None) -> list[dict[str, Any]]:
    """List spec file paths in `repo`. `glob` accepts `*` as a wildcard.

    Examples: `*prague*`, `specs/electra/*`, `*beacon-chain.md`.
    Use for discovery before `get_spec`.
    """
    with storage.connect() as conn:
        return storage.list_specs(conn, repo, glob=glob)


@mcp.tool()
def get_spec(repo: str, path: str) -> dict[str, Any]:
    """Fetch one spec file's full contents. Pair with `list_specs` to discover paths."""
    with storage.connect() as conn:
        row = storage.get_spec(conn, repo, path)
    if not row:
        return {"error": f"spec '{path}' not found in '{repo}'."}
    return row


@mcp.tool()
def search_specs(
    query: str,
    repo: str | None = None,
    limit: int = 50,
    snippet_words: int = 12,
) -> list[dict[str, Any]]:
    """Ranked full-text search across spec file bodies.

    Use for concept-level questions in consensus-specs / execution-specs that
    aren't tied to an EIP number — e.g. 'where is RANDAO mixed?', 'how is the
    blob commitment computed?'. Filter by repo to narrow CL vs EL.
    """
    with storage.connect() as conn:
        return storage.search_specs_fts(
            conn, query, repo=repo, limit=limit, snippet_words=snippet_words
        )


@mcp.tool()
def diff_spec(
    repo: str,
    path: str,
    since: str | None = None,
    until: str | None = None,
    context: int = 3,
) -> dict[str, Any]:
    """Unified git diff for one spec path between two revisions.

    Same `since` / `until` semantics as `diff_eip`. Use to track what changed in
    a spec file between syncs or releases.
    """
    spec = repos.get_repo(repo)
    repo_path = repos.ensure_clone(spec)
    old = _resolve_since(repo, since)
    if old is None:
        return {"error": "No prior sync recorded; nothing to diff against."}
    new = until or repos.head(repo_path)
    patch = repos.diff(repo_path, old, new, file_rel=path, context=context)
    return {
        "path": path, "from": old, "to": new,
        "diff": patch, "empty": not patch.strip(),
    }


# ---------- Sync tools ----------

@mcp.tool()
def sync_repo(repo: str) -> dict[str, Any]:
    """Pull a repo's latest commits and reindex it.

    Call when you need fresh data immediately rather than waiting for the next
    auto-sync. repo ∈ {'eips','ercs','consensus-specs','execution-specs'}.
    """
    return sync.sync_repo(repo)


@mcp.tool()
def sync_all() -> list[dict[str, Any]]:
    """Pull and reindex every tracked repo.

    Slow on first run (clones ~150 MB); fast afterwards (fetch + delta reindex).
    """
    return sync.sync_all()


@mcp.tool()
def recent_changes(days: int = 7, repo: str | None = None) -> list[dict[str, Any]]:
    """Files changed in each tracked repo over the past `days` days.

    Anchored to the last sync recorded before the cutoff (so it shows what's
    *new since you last cared*, not just what's in the git log). EIP entries
    include current title/status plus `status_was` when status flipped.
    Use for 'what shifted this week?' briefings.
    """
    return recent.recent_changes(days=days, repo=repo)


@mcp.tool()
def list_repos() -> list[dict[str, Any]]:
    """List tracked repos with their last sync commit + timestamp.

    Use to check how fresh the indexed data is.
    """
    out: list[dict[str, Any]] = []
    with storage.connect() as conn:
        for key, spec in REPOS.items():
            last = storage.last_sync(conn, key)
            out.append(
                {
                    "key": key,
                    "url": spec.url,
                    "eip_dirs": list(spec.eip_dirs),
                    "spec_dirs": list(spec.spec_dirs),
                    "last_sync": last,
                }
            )
    return out


# ---------- MCP resources ----------

def _format_eip_resource(number: int, repo: str) -> str:
    with storage.connect() as conn:
        row = storage.get_eip(conn, number, repo=repo)
    if not row:
        return f"# Not found\n\nEIP-{number} is not indexed in repo '{repo}'."
    header = [
        f"# EIP-{number}: {row.get('title') or ''}",
        "",
        f"- **Status:** {row.get('status')}",
        f"- **Type:** {row.get('type')}",
    ]
    if row.get("category"):
        header.append(f"- **Category:** {row['category']}")
    if row.get("created"):
        header.append(f"- **Created:** {row['created']}")
    if row.get("requires"):
        header.append(f"- **Requires:** {row['requires']}")
    if row.get("description"):
        header.append(f"- **Description:** {row['description']}")
    return "\n".join(header) + "\n\n" + row["body"]


@mcp.resource("eip://{number}")
def eip_resource(number: str) -> str:
    """Full EIP document: formatted header (status, type, requires, description) + body.
    URI form: `eip://1559`."""
    return _format_eip_resource(int(number), repo="eips")


@mcp.resource("erc://{number}")
def erc_resource(number: str) -> str:
    """Full ERC document with formatted header + body. URI form: `erc://20`."""
    return _format_eip_resource(int(number), repo="ercs")


@mcp.resource("spec://{repo}/{path}")
def spec_resource(repo: str, path: str) -> str:
    """One spec file's full contents.

    URI form: `spec://consensus-specs/specs/electra/beacon-chain.md`. If your
    MCP client splits on `/`, percent-encode the path component instead:
    `spec://consensus-specs/specs%2Felectra%2Fbeacon-chain.md`.
    """
    from urllib.parse import unquote
    decoded = unquote(path)
    with storage.connect() as conn:
        row = storage.get_spec(conn, repo, decoded)
    if not row:
        return f"# Not found\n\nSpec '{decoded}' not indexed in repo '{repo}'."
    return f"# {repo}: {decoded}\n\n{row['body']}"


# ---------- Entry point ----------

def run() -> None:
    sync.auto_sync_if_stale()  # noop unless EIPMCP_SYNC_TTL is set
    mcp.run(transport="stdio")
