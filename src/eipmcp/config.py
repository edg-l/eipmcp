"""Paths, tracked-repo configuration, and hardfork aliases."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir


@dataclass(frozen=True)
class RepoSpec:
    """A tracked git repo."""

    key: str           # short id used in tool args (e.g. "eips")
    url: str
    eip_dirs: tuple[str, ...] = ()   # subdirs that hold EIP-style frontmatter docs
    spec_dirs: tuple[str, ...] = ()  # subdirs that hold path-based spec docs


REPOS: dict[str, RepoSpec] = {
    "eips": RepoSpec(
        key="eips",
        url="https://github.com/ethereum/EIPs.git",
        eip_dirs=("EIPS",),
    ),
    "ercs": RepoSpec(
        key="ercs",
        url="https://github.com/ethereum/ERCs.git",
        eip_dirs=("ERCS",),
    ),
    "consensus-specs": RepoSpec(
        key="consensus-specs",
        url="https://github.com/ethereum/consensus-specs.git",
        spec_dirs=("specs", "ssz", "fork_choice", "sync"),
    ),
    "execution-specs": RepoSpec(
        key="execution-specs",
        url="https://github.com/ethereum/execution-specs.git",
        spec_dirs=("src/ethereum", "docs", "tests"),
    ),
    "execution-spec-tests": RepoSpec(
        key="execution-spec-tests",
        url="https://github.com/ethereum/execution-spec-tests.git",
        spec_dirs=("tests", "docs"),
    ),
}


# Codename aliases for `get_hardfork`. Lowercase keys. Lookup falls back to
# the literal name when not aliased (so "berlin" still works without an entry).
HARDFORK_ALIASES: dict[str, list[str]] = {
    "pectra": ["pectra", "prague", "electra"],
    "prague": ["prague", "pectra"],
    "electra": ["electra", "pectra"],
    "fusaka": ["fusaka", "fulu", "osaka"],
    "fulu": ["fulu", "fusaka"],
    "osaka": ["osaka", "fusaka"],
    "glamsterdam": ["glamsterdam", "amsterdam", "gloas"],
    "amsterdam": ["amsterdam", "glamsterdam"],
    "cancun": ["cancun", "deneb"],
    "deneb": ["deneb", "cancun"],
    "shanghai": ["shanghai", "capella"],
    "capella": ["capella", "shanghai"],
    "merge": ["merge", "paris", "bellatrix"],
    "paris": ["paris", "merge"],
    "bellatrix": ["bellatrix", "merge"],
}


# Map repo keys to (owner, name) for GitHub API lookups.
GITHUB_REPO: dict[str, tuple[str, str]] = {
    "eips": ("ethereum", "EIPs"),
    "ercs": ("ethereum", "ERCs"),
    "consensus-specs": ("ethereum", "consensus-specs"),
    "execution-specs": ("ethereum", "execution-specs"),
    "execution-spec-tests": ("ethereum", "execution-spec-tests"),
}


def data_dir() -> Path:
    override = os.environ.get("EIPMCP_DATA_DIR")
    root = Path(override) if override else Path(user_data_dir("eipmcp", "ethereum"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "repos").mkdir(exist_ok=True)
    return root


def repo_dir(key: str) -> Path:
    return data_dir() / "repos" / key


def db_path() -> Path:
    return data_dir() / "eipmcp.db"
