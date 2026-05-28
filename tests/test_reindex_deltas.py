"""Verify the rich-shape return from reindex_eips/reindex_specs."""

import subprocess
from pathlib import Path

import pytest

from eipmcp import eips, specs
from eipmcp.config import RepoSpec


def _git(cwd: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=cwd)


@pytest.fixture
def fake_eip_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "data" / "repos" / "eips"
    repo.parent.mkdir(parents=True)
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "EIPS").mkdir()
    return repo


def _write_eip(repo: Path, number: int, status: str, body_extra: str = ""):
    (repo / "EIPS" / f"eip-{number}.md").write_text(
        f"---\neip: {number}\ntitle: Test\nstatus: {status}\n"
        f"type: Standards Track\ncategory: Core\n---\n\nBody.\n{body_extra}"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", f"eip-{number} {status}")


def test_reindex_eips_first_run_marks_added(fake_eip_repo, monkeypatch):
    monkeypatch.setattr("eipmcp.repos.ensure_clone", lambda spec: fake_eip_repo)
    _write_eip(fake_eip_repo, 9999, "Draft")
    spec = RepoSpec(key="eips", url="x", eip_dirs=("EIPS",))
    out = eips.reindex_eips(spec)
    assert out["upserted"] == 1
    assert out["added"] == [{"number": 9999, "title": "Test"}]
    assert out["status_changes"] == []
    assert out["churned"] == []


def test_reindex_eips_status_transition(fake_eip_repo, monkeypatch):
    monkeypatch.setattr("eipmcp.repos.ensure_clone", lambda spec: fake_eip_repo)
    spec = RepoSpec(key="eips", url="x", eip_dirs=("EIPS",))
    _write_eip(fake_eip_repo, 9999, "Draft")
    eips.reindex_eips(spec)
    # Now flip status
    _write_eip(fake_eip_repo, 9999, "Final", body_extra="more text\n")
    out = eips.reindex_eips(spec)
    assert out["added"] == []
    assert out["status_changes"] == [{
        "number": 9999, "title": "Test", "from": "Draft", "to": "Final"
    }]
    assert len(out["churned"]) == 1
    assert out["churned"][0]["number"] == 9999


def test_reindex_specs_first_run_marks_added(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path / "data"))
    repo = tmp_path / "data" / "repos" / "consensus-specs"
    repo.parent.mkdir(parents=True)
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "specs").mkdir()
    (repo / "specs" / "x.md").write_text("hello world\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")

    monkeypatch.setattr("eipmcp.repos.ensure_clone", lambda spec: repo)
    spec = RepoSpec(key="consensus-specs", url="x", spec_dirs=("specs",))
    out = specs.reindex_specs(spec)
    assert out["upserted"] == 1
    assert out["added"] == ["specs/x.md"]
    assert out["churned"] == []

    # Modify and reindex
    (repo / "specs" / "x.md").write_text("hello\nworld\nmore\n")
    out = specs.reindex_specs(spec)
    assert out["added"] == []
    assert len(out["churned"]) == 1
    assert out["churned"][0]["path"] == "specs/x.md"
