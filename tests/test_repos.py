"""Exercise the git wrapper against a temp local repo."""

import subprocess
from pathlib import Path

from eipmcp import repos


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True)


def test_diff_and_changed_files(tmp_path: Path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.md").write_text("hello\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    old = repos.head(repo)

    (repo / "a.md").write_text("hello world\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "update")
    new = repos.head(repo)

    changed = repos.changed_files(repo, old, new)
    assert ("M", "a.md") in changed

    patch = repos.diff(repo, old, new, file_rel="a.md")
    assert "-hello" in patch and "+hello world" in patch

    assert repos.file_at(repo, old, "a.md").strip() == "hello"
    assert repos.file_at(repo, new, "a.md").strip() == "hello world"
