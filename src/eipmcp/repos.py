"""Git repo management: clone, pull, diff, content-at-commit."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .config import REPOS, RepoSpec, repo_dir


class GitError(RuntimeError):
    pass


def _run(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
    stream: bool = False,
) -> str:
    """Run a git command. With `stream=True`, pipe stdout+stderr to the parent's
    stderr so the user sees progress; otherwise capture output."""
    if stream:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            stdout=sys.stderr,
            stderr=sys.stderr,
            check=False,
        )
        if check and proc.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed (rc={proc.returncode})")
        return ""
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def ensure_clone(spec: RepoSpec, shallow_depth: int | None = None) -> Path:
    """Clone if missing; return repo path. Streams git progress to stderr."""
    path = repo_dir(spec.key)
    if (path / ".git").exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[eipmcp] cloning {spec.url} → {path}", file=sys.stderr, flush=True)
    args = ["clone", "--progress", "--filter=blob:none"]
    if shallow_depth:
        args += ["--depth", str(shallow_depth)]
    args += [spec.url, str(path)]
    _run(args, stream=True)
    return path


def pull(spec: RepoSpec) -> tuple[str, str]:
    """Fetch + fast-forward to whatever upstream's default branch currently is."""
    path = ensure_clone(spec)
    old = head(path)
    print(f"[eipmcp] fetching {spec.key}", file=sys.stderr, flush=True)
    _run(["fetch", "--progress", "--prune", "origin"], cwd=path, stream=True)
    # Refresh origin/HEAD so we follow upstream if they rename the default branch
    # (e.g. execution-specs flips from forks/amsterdam to forks/glamsterdam).
    try:
        _run(["remote", "set-head", "origin", "--auto"], cwd=path)
    except GitError as e:
        print(f"[eipmcp] warn: could not refresh origin/HEAD: {e}",
              file=sys.stderr, flush=True)
    default = default_branch(path)
    _run(["reset", "--hard", f"origin/{default}"], cwd=path)
    new = head(path)
    return old, new


def head(path: Path) -> str:
    return _run(["rev-parse", "HEAD"], cwd=path).strip()


_ORIGIN_REF_PREFIX = "refs/remotes/origin/"


def default_branch(path: Path) -> str:
    """Resolve upstream's current default branch, preserving multi-segment names
    (e.g. `forks/amsterdam` for execution-specs)."""
    try:
        ref = _run(
            ["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=path
        ).strip()
        if ref.startswith(_ORIGIN_REF_PREFIX):
            return ref[len(_ORIGIN_REF_PREFIX):]
        return ref.rsplit("/", 1)[-1]  # unexpected shape, best-effort
    except GitError:
        for branch in ("master", "main"):
            try:
                _run(["rev-parse", "--verify", f"origin/{branch}"], cwd=path)
                return branch
            except GitError:
                continue
        raise


def file_at(path: Path, rev: str, file_rel: str) -> str | None:
    try:
        return _run(["show", f"{rev}:{file_rel}"], cwd=path)
    except GitError:
        return None


def diff(
    path: Path,
    old_rev: str,
    new_rev: str,
    file_rel: str | None = None,
    context: int = 3,
) -> str:
    args = ["diff", f"--unified={context}", old_rev, new_rev]
    if file_rel:
        args += ["--", file_rel]
    return _run(args, cwd=path)


def changed_files(path: Path, old_rev: str, new_rev: str) -> list[tuple[str, str]]:
    """Returns [(status, path), ...]. Status is A/M/D/R..."""
    out = _run(["diff", "--name-status", old_rev, new_rev], cwd=path)
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1]))
    return rows


@dataclass
class WalkedFile:
    rel_path: str
    abs_path: Path


def walk_dirs(
    path: Path, subdirs: Iterable[str], suffixes: tuple[str, ...] = (".md",)
) -> list[WalkedFile]:
    out: list[WalkedFile] = []
    for sub in subdirs:
        base = path / sub
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in suffixes:
                out.append(WalkedFile(rel_path=str(p.relative_to(path)), abs_path=p))
    return out


def get_repo(key: str) -> RepoSpec:
    if key not in REPOS:
        raise KeyError(f"unknown repo '{key}'. known: {list(REPOS)}")
    return REPOS[key]
