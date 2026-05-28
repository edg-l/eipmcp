"""High-level: pull + reindex one or all repos."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import eips, repos, specs, storage
from .config import REPOS


def sync_repo(key: str) -> dict[str, Any]:
    spec = repos.get_repo(key)
    old, new = repos.pull(spec)
    eip_stats = eips.reindex_eips(spec) if spec.eip_dirs else None
    spec_stats = specs.reindex_specs(spec) if spec.spec_dirs else None
    with storage.connect() as conn:
        storage.record_sync(conn, key, new, datetime.now(timezone.utc).isoformat())
    return {
        "repo": key,
        "old_head": old,
        "new_head": new,
        "changed": old != new,
        "eips": eip_stats,
        "specs": spec_stats,
    }


def sync_all() -> list[dict[str, Any]]:
    return [sync_repo(k) for k in REPOS]
