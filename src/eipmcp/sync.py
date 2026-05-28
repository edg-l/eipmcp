"""High-level: pull + reindex, with optional TTL-based auto-sync."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from . import eips, repos, specs, storage
from .config import REPOS


def sync_repo(key: str) -> dict[str, Any]:
    spec = repos.get_repo(key)
    print(f"[eipmcp] === {key} ===", file=sys.stderr, flush=True)
    old, new = repos.pull(spec)
    if spec.eip_dirs:
        print(f"[eipmcp] indexing EIPs in {key}", file=sys.stderr, flush=True)
        eip_stats = eips.reindex_eips(spec)
    else:
        eip_stats = None
    if spec.spec_dirs:
        print(f"[eipmcp] indexing specs in {key}", file=sys.stderr, flush=True)
        spec_stats = specs.reindex_specs(spec)
    else:
        spec_stats = None
    with storage.connect() as conn:
        storage.record_sync(conn, key, new, datetime.now(timezone.utc).isoformat())
    changed = old != new
    print(
        f"[eipmcp] {key}: {old[:7]} → {new[:7]}"
        f" {'(updated)' if changed else '(no change)'}"
        f" eips={eip_stats} specs={spec_stats}",
        file=sys.stderr,
        flush=True,
    )
    return {
        "repo": key,
        "old_head": old,
        "new_head": new,
        "changed": changed,
        "eips": eip_stats,
        "specs": spec_stats,
    }


def sync_all() -> list[dict[str, Any]]:
    return [sync_repo(k) for k in REPOS]


# ---------- TTL-based auto-sync ----------

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_ttl(value: str) -> int:
    """Parse '30m', '24h', '1d', '3600s', or bare seconds. Returns 0 on disabled/invalid."""
    s = (value or "").strip().lower()
    if not s or s == "0":
        return 0
    try:
        if s[-1] in _UNIT_SECONDS:
            return int(float(s[:-1]) * _UNIT_SECONDS[s[-1]])
        return int(s)
    except (ValueError, IndexError):
        return 0


def stale_repos(ttl_seconds: int) -> list[str]:
    """Repos whose last sync is older than `ttl_seconds` (or never synced)."""
    if ttl_seconds <= 0:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
    stale: list[str] = []
    with storage.connect() as conn:
        for key in REPOS:
            last = storage.last_sync(conn, key)
            if not last:
                stale.append(key); continue
            try:
                ts = datetime.fromisoformat(last["synced_at"])
            except ValueError:
                stale.append(key); continue
            if ts < cutoff:
                stale.append(key)
    return stale


def auto_sync_if_stale() -> list[dict[str, Any]]:
    """Sync any stale repos if EIPMCP_SYNC_TTL is set. Returns sync results (possibly [])."""
    ttl = parse_ttl(os.environ.get("EIPMCP_SYNC_TTL", "0"))
    stale = stale_repos(ttl)
    if not stale:
        return []
    print(
        f"[eipmcp] auto-sync: {len(stale)} stale repo(s) (TTL={ttl}s): {stale}",
        file=sys.stderr,
        flush=True,
    )
    return [sync_repo(k) for k in stale]
