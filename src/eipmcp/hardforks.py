"""Hardfork lookup: resolve fork codenames to Meta EIPs and their included EIPs."""

from __future__ import annotations

from typing import Any

from . import crossrefs, storage
from .config import HARDFORK_ALIASES


def _candidate_names(name: str) -> list[str]:
    key = name.lower().strip()
    return HARDFORK_ALIASES.get(key, [key])


def lookup(name: str) -> dict[str, Any]:
    """Return Meta EIPs matching the fork name and the EIPs they include."""
    candidates = _candidate_names(name)
    placeholders = " OR ".join(["LOWER(title) LIKE ?"] * len(candidates))
    args = [f"%{c}%" for c in candidates]
    with storage.connect() as conn:
        rows = conn.execute(
            f"SELECT repo, number, title, status, body FROM eips "
            f"WHERE type='Meta' AND ({placeholders}) ORDER BY number",
            args,
        ).fetchall()
        matches: list[dict[str, Any]] = []
        all_included: set[int] = set()
        for r in rows:
            included = crossrefs.extract_refs(r["body"], exclude=r["number"])
            matches.append(
                {
                    "number": r["number"],
                    "title": r["title"],
                    "status": r["status"],
                    "included_eips": sorted(included),
                }
            )
            all_included |= included
        enriched: list[dict[str, Any]] = []
        for n in sorted(all_included):
            row = storage.get_eip(conn, n)
            enriched.append(
                {
                    "number": n,
                    "title": row["title"] if row else None,
                    "status": row["status"] if row else None,
                    "type": row["type"] if row else None,
                    "category": row["category"] if row else None,
                    "indexed": row is not None,
                }
            )
    return {
        "query": name,
        "resolved_aliases": candidates,
        "matches": matches,
        "included_eips": enriched,
    }


def list_all() -> list[dict[str, Any]]:
    """All indexed Meta EIPs (i.e. candidates for a fork lookup)."""
    with storage.connect() as conn:
        rows = conn.execute(
            "SELECT repo, number, title, status, description FROM eips "
            "WHERE type='Meta' ORDER BY number"
        ).fetchall()
    return [dict(r) for r in rows]
