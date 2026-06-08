"""Flatten OpenRPC method YAML into per-method searchable spec docs."""

import hashlib
import sys
from typing import Any

import yaml

from . import crossrefs, repos, storage
from .config import RepoSpec

OPENRPC_SUFFIXES = (".yaml",)
EXAMPLE_MAX_CHARS = 200


def _schema_repr(schema: Any) -> str:
    if isinstance(schema, dict):
        if "$ref" in schema:
            return schema["$ref"].rsplit("/", 1)[-1]
        t = schema.get("type")
        if isinstance(t, list):
            return " | ".join(str(x) for x in t)        # union, e.g. "string | null"
        if t == "array" and "items" in schema:
            return f"array<{_schema_repr(schema['items'])}>"
        if t:
            return str(t)
        if "title" in schema:
            return str(schema["title"])
        if "oneOf" in schema or "anyOf" in schema:
            return "oneOf"
        return "object"
    return "object"


def _trim(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > EXAMPLE_MAX_CHARS:
            return f"<{len(value)} bytes elided>"
        return value
    if isinstance(value, list):
        trimmed = [_trim(v) for v in value[:3]]
        if len(value) > 3:
            trimmed.append(f"<… {len(value) - 3} more …>")
        return trimmed
    if isinstance(value, dict):
        items = list(value.items())[:8]
        result = {k: _trim(v) for k, v in items}
        if len(value) > 8:
            result["…"] = f"<{len(value) - 8} more fields>"
        return result
    return value


def _methods_from_doc(doc: Any) -> list[dict]:
    if isinstance(doc, list):
        return [m for m in doc if isinstance(m, dict) and "name" in m]
    if isinstance(doc, dict):
        if "methods" in doc and isinstance(doc["methods"], list):
            return [m for m in doc["methods"] if isinstance(m, dict) and "name" in m]
        if "name" in doc:
            return [doc]
    return []


def render_method(method: dict) -> str:
    """Render a single OpenRPC method dict as a markdown body (pure; FTS-friendly)."""
    name = method.get("name", "")
    parts: list[str] = [f"# {name}"]

    summary = method.get("summary")
    description = method.get("description")
    if summary:
        prose = summary
        if description and description != summary:
            prose = prose + "\n\n" + description
        parts.append(prose)
    elif description:
        parts.append(description)

    params = method.get("params") or []
    if params:
        param_lines = ["## Params"]
        for p in params:
            pname = p.get("name", "")
            req = "required" if p.get("required") else "optional"
            schema_str = _schema_repr(p.get("schema"))
            param_lines.append(f"- {pname} ({req}): {schema_str}")
        parts.append("\n".join(param_lines))

    result = method.get("result")
    if result:
        rname = result.get("name", "result")
        rschema = _schema_repr(result.get("schema"))
        parts.append(f"## Result\n{rname}: {rschema}")

    errors = method.get("errors") or []
    if errors:
        error_lines = ["## Errors"]
        for e in errors:
            error_lines.append(f"- {e.get('code')}: {e.get('message')}")
        parts.append("\n".join(error_lines))

    examples = method.get("examples") or []
    if examples:
        trimmed = _trim(examples[0])
        block = yaml.safe_dump(trimmed, sort_keys=False)
        parts.append(f"## Example\n```yaml\n{block}```")

    return "\n\n".join(parts)


def reindex_openrpc(spec: RepoSpec) -> dict[str, Any]:
    """Reindex OpenRPC method YAML files. Returns counts plus added/churned lists."""
    if not spec.openrpc_dirs:
        return {"upserted": 0, "deleted": 0, "added": [], "churned": [], "skipped": 0}
    path = repos.ensure_clone(spec)
    files = repos.walk_dirs(path, spec.openrpc_dirs, suffixes=OPENRPC_SUFFIXES)
    present_paths: list[str] = []
    upserted = 0
    added: list[str] = []
    churned: list[dict[str, Any]] = []
    skipped = 0
    with storage.connect() as conn:
        for wf in files:
            text = wf.abs_path.read_text(encoding="utf-8", errors="replace")
            try:
                doc = yaml.safe_load(text)
            except yaml.YAMLError as e:
                print(
                    f"[eipmcp] warn: skipping {wf.rel_path}: {e}",
                    file=sys.stderr,
                    flush=True,
                )
                skipped += 1
                continue
            methods = _methods_from_doc(doc)
            if not methods:
                skipped += 1
                continue
            for method in methods:
                name = method.get("name")
                if not name:
                    continue
                synthetic_path = f"{wf.rel_path}#{name}"
                try:
                    body = render_method(method)
                except Exception as e:
                    print(
                        f"[eipmcp] warn: skipping method {synthetic_path}: {e}",
                        file=sys.stderr,
                        flush=True,
                    )
                    skipped += 1
                    continue
                sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
                old = storage.get_spec(conn, spec.key, synthetic_path)
                if old is None:
                    added.append(synthetic_path)
                elif old.get("content_sha") != sha:
                    old_lines = len((old.get("body") or "").splitlines())
                    new_lines = len(body.splitlines())
                    churned.append({"path": synthetic_path, "lines_delta": new_lines - old_lines})
                storage.upsert_spec(conn, spec.key, synthetic_path, body, sha)
                refs = crossrefs.extract_refs(body, path=synthetic_path)
                storage.replace_refs(conn, spec.key, synthetic_path, refs)
                present_paths.append(synthetic_path)
                upserted += 1
        deleted = storage.delete_missing_specs(conn, spec.key, present_paths, synthetic=True)
    return {
        "upserted": upserted,
        "deleted": deleted,
        "added": added,
        "churned": churned,
        "skipped": skipped,
    }
