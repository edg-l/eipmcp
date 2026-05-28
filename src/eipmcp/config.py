"""Paths and tracked-repo configuration."""

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
}


def data_dir() -> Path:
    """Where the MCP stores cloned repos and the SQLite db."""
    override = os.environ.get("EIPMCP_DATA_DIR")
    root = Path(override) if override else Path(user_data_dir("eipmcp", "ethereum"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "repos").mkdir(exist_ok=True)
    return root


def repo_dir(key: str) -> Path:
    return data_dir() / "repos" / key


def db_path() -> Path:
    return data_dir() / "eipmcp.db"
