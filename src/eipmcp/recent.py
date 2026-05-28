"""Compute 'what changed in the last N days' across tracked repos."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from . import eips, repos, storage
from .config import REPOS

_EIP_FILE_RE = re.compile(r"(?:^|/)(?:eip|erc)-(\d+)\.md$", re.IGNORECASE)


def _eip_number_from_path(path: str) -> int | None:
    m = _EIP_FILE_RE.search(path)
    return int(m.group(1)) if m else None


def _recent_for_repo(key: str, cutoff: datetime) -> dict[str, Any]:
    spec = repos.get_repo(key)
    with storage.connect() as conn:
        anchor = storage.sync_log_before(conn, key, cutoff.isoformat())
    if not anchor:
        return {
            "repo": key,
            "note": f"no sync recorded before {cutoff.date().isoformat()}; "
                    f"can't determine baseline.",
            "changed": [],
            "total": 0,
        }
    repo_path = repos.ensure_clone(spec)
    old = anchor["commit_sha"]
    new = repos.head(repo_path)
    if old == new:
        return {
            "repo": key, "from": old, "to": new,
            "from_date": anchor["synced_at"], "changed": [], "total": 0,
        }
    changed_files = repos.changed_files(repo_path, old, new)
    enriched: list[dict[str, Any]] = []
    for status, path in changed_files:
        entry: dict[str, Any] = {"status": status, "path": path}
        n = _eip_number_from_path(path) if spec.eip_dirs else None
        if n is not None:
            entry["eip_number"] = n
            with storage.connect() as conn:
                current = storage.get_eip(conn, n, repo=key)
            if current:
                entry["title"] = current.get("title")
                entry["status_now"] = current.get("status")
            old_text = repos.file_at(repo_path, old, path)
            if old_text:
                old_row = eips.parse_eip_file(old_text, path, key)
                if old_row and old_row.get("status") != (current.get("status") if current else None):
                    entry["status_was"] = old_row.get("status")
        enriched.append(entry)
    return {
        "repo": key,
        "from": old,
        "to": new,
        "from_date": anchor["synced_at"],
        "changed": enriched,
        "total": len(enriched),
    }


def recent_changes(days: int = 7, repo: str | None = None) -> list[dict[str, Any]]:
    """Files changed in each tracked repo since `days` ago, anchored to the
    last sync recorded before that point. EIP rows get enriched with current
    status and (when changed) the previous status."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    keys = [repo] if repo else list(REPOS)
    return [_recent_for_repo(k, cutoff) for k in keys]
