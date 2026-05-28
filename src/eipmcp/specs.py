"""Index spec-style (path-based, non-EIP-frontmatter) docs."""

from __future__ import annotations

import hashlib

from . import crossrefs, repos, storage
from .config import RepoSpec


SPEC_SUFFIXES = (".md", ".py", ".rst", ".txt")


def reindex_specs(spec: RepoSpec) -> dict[str, int]:
    if not spec.spec_dirs:
        return {"upserted": 0, "deleted": 0}
    path = repos.ensure_clone(spec)
    files = repos.walk_dirs(path, spec.spec_dirs, suffixes=SPEC_SUFFIXES)
    present_paths: list[str] = []
    upserted = 0
    with storage.connect() as conn:
        for wf in files:
            text = wf.abs_path.read_text(encoding="utf-8", errors="replace")
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            storage.upsert_spec(conn, spec.key, wf.rel_path, text, sha)
            refs = crossrefs.extract_refs(text, path=wf.rel_path)
            storage.replace_refs(conn, spec.key, wf.rel_path, refs)
            present_paths.append(wf.rel_path)
            upserted += 1
        deleted = storage.delete_missing_specs(conn, spec.key, present_paths)
    return {"upserted": upserted, "deleted": deleted}
