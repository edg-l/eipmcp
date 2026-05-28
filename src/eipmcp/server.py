"""MCP server exposing EIP/spec tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import repos, storage, sync
from .config import REPOS

mcp = FastMCP("eipmcp")


def _resolve_since(repo_key: str, since: str | None) -> str | None:
    """Translate 'last_sync', 'previous_sync', a commit SHA, or None → commit SHA."""
    if since is None or since == "previous_sync":
        with storage.connect() as conn:
            prev = storage.previous_sync(conn, repo_key)
        return prev["commit_sha"] if prev else None
    if since == "last_sync":
        with storage.connect() as conn:
            last = storage.last_sync(conn, repo_key)
        return last["commit_sha"] if last else None
    return since  # raw rev


# ---------- EIP tools ----------

@mcp.tool()
def get_eip(number: int, repo: str = "eips") -> dict[str, Any]:
    """Return full EIP/ERC: frontmatter + markdown body.

    repo: 'eips' (default) or 'ercs'.
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
    """List EIPs with optional filters. Lightweight: number/title/status/type/category."""
    with storage.connect() as conn:
        return storage.list_eips(conn, repo=repo, status=status, type_=type, category=category)


@mcp.tool()
def search_eips(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Keyword LIKE search over EIP titles and bodies."""
    with storage.connect() as conn:
        return storage.search_eips(conn, query, limit=limit)


@mcp.tool()
def diff_eip(
    number: int,
    since: str | None = None,
    until: str | None = None,
    repo: str = "eips",
    context: int = 3,
) -> dict[str, Any]:
    """Unified git diff for an EIP between two revs.

    since: commit SHA, 'last_sync', 'previous_sync' (default), or None.
    until: commit SHA or None (defaults to HEAD).
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
        "number": number,
        "file": file_rel,
        "from": old,
        "to": new,
        "diff": patch,
        "empty": not patch.strip(),
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


# ---------- Spec tools ----------

@mcp.tool()
def list_specs(repo: str, glob: str | None = None) -> list[dict[str, Any]]:
    """List indexed spec files in a repo. Glob uses SQL LIKE semantics (`*` → `%`)."""
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
        "path": path,
        "from": old,
        "to": new,
        "diff": patch,
        "empty": not patch.strip(),
    }


# ---------- Sync tools ----------

@mcp.tool()
def sync_repo(repo: str) -> dict[str, Any]:
    """Pull a repo and reindex. repo ∈ {'eips','ercs','consensus-specs','execution-specs'}."""
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


def run() -> None:
    mcp.run(transport="stdio")
