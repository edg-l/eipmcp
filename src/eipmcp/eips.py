"""Parse EIP-style markdown (YAML frontmatter) and index into SQLite."""

from __future__ import annotations

import hashlib
import re
from typing import Any

import frontmatter

from . import repos, storage
from .config import RepoSpec

_EIP_FILENAME = re.compile(r"^(?:eip|erc)-(\d+)\.md$", re.IGNORECASE)


def _parse_number_from_path(rel_path: str) -> int | None:
    name = rel_path.rsplit("/", 1)[-1]
    m = _EIP_FILENAME.match(name)
    return int(m.group(1)) if m else None


def _normalize_requires(raw: Any) -> list[int]:
    if raw is None:
        return []
    if isinstance(raw, int):
        return [raw]
    if isinstance(raw, str):
        return [int(x) for x in re.findall(r"\d+", raw)]
    if isinstance(raw, list):
        out: list[int] = []
        for item in raw:
            if isinstance(item, int):
                out.append(item)
            elif isinstance(item, str):
                out.extend(int(x) for x in re.findall(r"\d+", item))
        return out
    return []


def parse_eip_file(text: str, rel_path: str, repo_key: str) -> dict[str, Any] | None:
    number = _parse_number_from_path(rel_path)
    if number is None:
        return None
    try:
        post = frontmatter.loads(text)
    except Exception:
        return None
    meta = post.metadata or {}
    body = post.content
    return {
        "repo": repo_key,
        "number": number,
        "title": str(meta.get("title") or "").strip() or None,
        "status": str(meta.get("status") or "").strip() or None,
        "type": str(meta.get("type") or "").strip() or None,
        "category": str(meta.get("category") or "").strip() or None,
        "author": str(meta.get("author") or "").strip() or None,
        "created": str(meta.get("created") or "").strip() or None,
        "requires": _normalize_requires(meta.get("requires")),
        "discussions": str(meta.get("discussions-to") or "").strip() or None,
        "file_path": rel_path,
        "body": body,
        "content_sha": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def reindex_eips(spec: RepoSpec) -> dict[str, int]:
    """Scan repo on disk, upsert all EIP-format docs, drop ones that vanished."""
    if not spec.eip_dirs:
        return {"upserted": 0, "deleted": 0, "skipped": 0}
    path = repos.ensure_clone(spec)
    files = repos.walk_dirs(path, spec.eip_dirs, suffixes=(".md",))
    upserted = 0
    skipped = 0
    present_numbers: list[int] = []
    with storage.connect() as conn:
        for wf in files:
            text = wf.abs_path.read_text(encoding="utf-8", errors="replace")
            row = parse_eip_file(text, wf.rel_path, spec.key)
            if row is None:
                skipped += 1
                continue
            storage.upsert_eip(conn, row)
            present_numbers.append(row["number"])
            upserted += 1
        deleted = storage.delete_missing_eips(conn, spec.key, present_numbers)
    return {"upserted": upserted, "deleted": deleted, "skipped": skipped}
