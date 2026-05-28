"""GitHub queries (open PRs, etc.) via the local `gh` CLI for auth."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .config import GITHUB_REPO


def _gh_search_issues(query: str, per_page: int) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "gh", "api", "-X", "GET", "/search/issues",
            "-f", f"q={query}",
            "-F", f"per_page={per_page}",
        ],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def _shape(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": item["number"],
        "title": item["title"],
        "url": item["html_url"],
        "user": (item.get("user") or {}).get("login"),
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
        "labels": [lbl["name"] for lbl in item.get("labels") or []],
        "draft": item.get("draft", False),
    }


def open_prs_for_eip(number: int, repo_key: str = "eips", limit: int = 30) -> list[dict[str, Any]]:
    """Open PRs in `repo_key` that mention EIP-<number> in title or body."""
    if repo_key not in GITHUB_REPO:
        return [{"error": f"unknown repo '{repo_key}'"}]
    owner, name = GITHUB_REPO[repo_key]
    q = f'is:pr is:open repo:{owner}/{name} "EIP-{number}"'
    try:
        data = _gh_search_issues(q, per_page=limit)
    except FileNotFoundError:
        return [{"error": "gh CLI not found. Install gh (or set GITHUB_TOKEN + reimplement)."}]
    except RuntimeError as e:
        return [{"error": f"gh search failed: {e}"}]
    return [_shape(x) for x in data.get("items", [])]


def open_prs_for_path(repo_key: str, path: str, limit: int = 30) -> list[dict[str, Any]]:
    """Open PRs in `repo_key` whose title or body mentions a basename of `path`.

    GitHub's search API has no direct file-touched filter without GraphQL paging,
    so we approximate with the path's basename. For EIPs/specs that's usually
    the unique identifier (eip-7702.md, beacon-chain.md).
    """
    if repo_key not in GITHUB_REPO:
        return [{"error": f"unknown repo '{repo_key}'"}]
    owner, name = GITHUB_REPO[repo_key]
    basename = path.rsplit("/", 1)[-1]
    q = f'is:pr is:open repo:{owner}/{name} "{basename}"'
    try:
        data = _gh_search_issues(q, per_page=limit)
    except FileNotFoundError:
        return [{"error": "gh CLI not found."}]
    except RuntimeError as e:
        return [{"error": f"gh search failed: {e}"}]
    return [_shape(x) for x in data.get("items", [])]
