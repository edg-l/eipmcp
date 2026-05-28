"""MCP server exposing EIP/spec tools and resources."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import github_api, hardforks, repos, storage, sync
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
    """Return full EIP/ERC: frontmatter + markdown body. repo: 'eips' or 'ercs'."""
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
    """List EIPs with optional filters. Returns number/title/description/status/type/category."""
    with storage.connect() as conn:
        return storage.list_eips(conn, repo=repo, status=status, type_=type, category=category)


@mcp.tool()
def search_eips(query: str, limit: int = 50, snippet_words: int = 12) -> list[dict[str, Any]]:
    """SQLite FTS5 search over EIP title/description/body. Ranked by bm25, returns snippets."""
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
    """Unified git diff for an EIP between two revs.

    since: 'previous_sync' (default), 'last_sync', or a commit SHA.
    until: commit SHA, or None for current HEAD.
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
    """EIP numbers this EIP requires (from frontmatter)."""
    with storage.connect() as conn:
        row = storage.get_eip(conn, number, repo=repo)
    return list(row["requires"]) if row else []


@mcp.tool()
def eip_required_by(number: int, repo: str = "eips") -> list[dict[str, Any]]:
    """EIPs whose `requires` list includes this EIP."""
    with storage.connect() as conn:
        return storage.required_by(conn, number, repo=repo)


# ---------- Cross-reference tools ----------

@mcp.tool()
def eip_referenced_in(number: int, repo: str | None = None) -> list[dict[str, Any]]:
    """Spec/test/EIP files that mention `EIP-<number>` in body or path.

    Optionally filter by source repo (e.g. 'consensus-specs', 'execution-spec-tests').
    """
    with storage.connect() as conn:
        return storage.refs_for_eip(conn, number, repo=repo)


@mcp.tool()
def refs_in_source(repo: str, path: str) -> list[int]:
    """EIP numbers referenced inside a given indexed file."""
    with storage.connect() as conn:
        return storage.refs_in_source(conn, repo, path)


@mcp.tool()
def tests_for_eip(number: int) -> list[dict[str, Any]]:
    """Files under execution-specs/tests/ that reference this EIP (path-based or in body)."""
    with storage.connect() as conn:
        all_refs = storage.refs_for_eip(conn, number, repo="execution-specs")
    return [r for r in all_refs if r["source_path"].startswith("tests/")]


# ---------- Hardfork tools ----------

@mcp.tool()
def get_hardfork(name: str) -> dict[str, Any]:
    """Resolve a fork codename (pectra, fusaka, cancun, ...) to its Meta EIP(s) and included EIPs."""
    return hardforks.lookup(name)


@mcp.tool()
def list_hardforks() -> list[dict[str, Any]]:
    """All indexed Meta EIPs (candidates for hardfork lookups)."""
    return hardforks.list_all()


# ---------- Open-PR tools ----------

@mcp.tool()
def pending_prs_for_eip(number: int, repo: str = "eips", limit: int = 30) -> list[dict[str, Any]]:
    """Open GitHub PRs in `repo` that mention EIP-<number>. Uses local `gh` CLI."""
    return github_api.open_prs_for_eip(number, repo_key=repo, limit=limit)


@mcp.tool()
def pending_prs_for_spec(repo: str, path: str, limit: int = 30) -> list[dict[str, Any]]:
    """Open GitHub PRs in `repo` matching the basename of `path` (approximate)."""
    return github_api.open_prs_for_path(repo, path, limit=limit)


# ---------- Spec tools ----------

@mcp.tool()
def list_specs(repo: str, glob: str | None = None) -> list[dict[str, Any]]:
    """List indexed spec files. `glob` uses SQL LIKE semantics (`*` → `%`)."""
    with storage.connect() as conn:
        return storage.list_specs(conn, repo, glob=glob)


@mcp.tool()
def get_spec(repo: str, path: str) -> dict[str, Any]:
    """Return the full contents of an indexed spec file."""
    with storage.connect() as conn:
        row = storage.get_spec(conn, repo, path)
    if not row:
        return {"error": f"spec '{path}' not found in '{repo}'."}
    return row


@mcp.tool()
def diff_spec(
    repo: str,
    path: str,
    since: str | None = None,
    until: str | None = None,
    context: int = 3,
) -> dict[str, Any]:
    """Unified git diff for a spec path between two revs."""
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
    """Pull a repo and reindex.

    repo ∈ {'eips','ercs','consensus-specs','execution-specs'}.
    """
    return sync.sync_repo(repo)


@mcp.tool()
def sync_all() -> list[dict[str, Any]]:
    """Pull and reindex every tracked repo."""
    return sync.sync_all()


@mcp.tool()
def list_repos() -> list[dict[str, Any]]:
    """Show tracked repos and their last-known sync commit."""
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
    """Full EIP document. URI: `eip://1559`."""
    return _format_eip_resource(int(number), repo="eips")


@mcp.resource("erc://{number}")
def erc_resource(number: str) -> str:
    """Full ERC document. URI: `erc://20`."""
    return _format_eip_resource(int(number), repo="ercs")


# ---------- Entry point ----------

def run() -> None:
    sync.auto_sync_if_stale()  # noop unless EIPMCP_SYNC_TTL is set
    mcp.run(transport="stdio")
