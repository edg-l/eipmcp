"""High-level: pull + reindex, with optional TTL-based auto-sync."""

import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from . import eips, openrpc, repos, specs, storage
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
    if spec.openrpc_dirs:
        print(f"[eipmcp] indexing OpenRPC methods in {key}", file=sys.stderr, flush=True)
        openrpc_stats = openrpc.reindex_openrpc(spec)
    else:
        openrpc_stats = None
    with storage.connect() as conn:
        storage.record_sync(conn, key, new, datetime.now(UTC).isoformat())
    changed = old != new
    print(
        f"[eipmcp] {key}: {old[:7]} → {new[:7]}"
        f" {'(updated)' if changed else '(no change)'}"
        f" eips={eip_stats} specs={spec_stats} openrpc={openrpc_stats}",
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
        "openrpc": openrpc_stats,
    }


def sync_all() -> list[dict[str, Any]]:
    """Sync every tracked repo. Per-repo failures are caught so one error
    doesn't block the rest; the failing repo gets {error, type} in its slot."""
    results: list[dict[str, Any]] = []
    for k in REPOS:
        try:
            results.append(sync_repo(k))
        except Exception as e:
            print(f"[eipmcp] sync of {k} failed: {e}", file=sys.stderr, flush=True)
            results.append({
                "repo": k,
                "error": str(e),
                "type": type(e).__name__,
            })
    return results


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


DEFAULT_TTL = "24h"


def stale_repos(ttl_seconds: int, include_uninitialized: bool = False) -> list[str]:
    """Repos whose last sync is older than `ttl_seconds`.

    By default, repos that have never been synced are NOT counted as stale —
    that keeps `eipmcp serve` startup instant when the user hasn't run
    `eipmcp sync` yet. Set `include_uninitialized=True` to flag them too.
    """
    if ttl_seconds <= 0:
        return []
    cutoff = datetime.now(UTC) - timedelta(seconds=ttl_seconds)
    stale: list[str] = []
    with storage.connect() as conn:
        for key in REPOS:
            last = storage.last_sync(conn, key)
            if not last:
                if include_uninitialized:
                    stale.append(key)
                continue
            try:
                ts = datetime.fromisoformat(last["synced_at"])
            except ValueError:
                stale.append(key)
                continue
            if ts < cutoff:
                stale.append(key)
    return stale


def _warn_if_uninitialized() -> None:
    with storage.connect() as conn:
        uninit = [k for k in REPOS if not storage.last_sync(conn, k)]
    if uninit:
        print(
            f"[eipmcp] note: never-synced repos: {uninit}. "
            f"Run `eipmcp sync` once to populate.",
            file=sys.stderr,
            flush=True,
        )


def auto_sync_if_stale() -> list[dict[str, Any]]:
    """Sync any stale (previously initialized) repos. TTL controlled by
    EIPMCP_SYNC_TTL; defaults to 24h. Set to 0 to disable."""
    ttl = parse_ttl(os.environ.get("EIPMCP_SYNC_TTL", DEFAULT_TTL))
    _warn_if_uninitialized()
    if ttl <= 0:
        return []
    stale = stale_repos(ttl)
    if not stale:
        return []
    print(
        f"[eipmcp] auto-sync: {len(stale)} stale repo(s) (TTL={ttl}s): {stale}",
        file=sys.stderr,
        flush=True,
    )
    return [sync_repo(k) for k in stale]
