"""Tests for src/eipmcp/openrpc.py: render_method, helpers, and reindex_openrpc."""

import subprocess
from pathlib import Path

import yaml

from eipmcp import specs, storage
from eipmcp.config import RepoSpec
from eipmcp.openrpc import (
    EXAMPLE_MAX_CHARS,
    _methods_from_doc,
    render_method,
    reindex_openrpc,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=cwd)


def _make_repo(tmp_path: Path, key: str) -> Path:
    repo = tmp_path / "data" / "repos" / key
    repo.parent.mkdir(parents=True, exist_ok=True)
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    return repo


def _commit_all(repo: Path, msg: str = "update") -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", msg)


# ---------------------------------------------------------------------------
# 1. render_method basic output
# ---------------------------------------------------------------------------

def test_render_method_basic():
    method = {
        "name": "eth_getBlockByHash",
        "summary": "Returns a block by its hash.",
        "params": [
            {
                "name": "Block hash",
                "required": True,
                "schema": {"$ref": "#/components/schemas/hash32"},
            },
            {
                "name": "hydrated",
                "required": False,
                "schema": {"type": "boolean"},
            },
        ],
        "result": {
            "name": "Block",
            "schema": {"type": "object"},
        },
        "errors": [
            {"code": 4444, "message": "Pruned history unavailable"},
        ],
    }
    body = render_method(method)

    assert "# eth_getBlockByHash" in body
    assert "Returns a block by its hash." in body
    assert "Block hash" in body
    assert "hydrated" in body
    assert "(required)" in body
    assert "(optional)" in body
    assert "hash32" in body
    assert "boolean" in body
    assert "4444" in body
    assert "Pruned history unavailable" in body


# ---------------------------------------------------------------------------
# 2. render_method trims large example values
# ---------------------------------------------------------------------------

def test_render_method_trims_large_example():
    long_value = "0x" + "a" * 500
    assert len(long_value) > EXAMPLE_MAX_CHARS

    method = {
        "name": "eth_getLargeBlob",
        "examples": [
            {"name": "ex", "result": {"value": long_value}},
        ],
    }
    body = render_method(method)

    assert long_value not in body
    assert "bytes elided" in body


# ---------------------------------------------------------------------------
# 3. _methods_from_doc shapes
# ---------------------------------------------------------------------------

def test_methods_from_doc_shapes():
    m1 = {"name": "eth_a", "summary": "A"}
    m2 = {"name": "eth_b", "summary": "B"}

    # bare list of two method dicts
    result = _methods_from_doc([m1, m2])
    assert len(result) == 2

    # dict with 'methods' key
    result = _methods_from_doc({"methods": [m1, m2]})
    assert result == [m1, m2]

    # single method dict (has 'name')
    result = _methods_from_doc({"name": "eth_a", "summary": "A"})
    assert result == [{"name": "eth_a", "summary": "A"}]

    # components/schema dict without name or methods -> empty
    result = _methods_from_doc({"components": {"schemas": {"hash32": {"type": "string"}}}})
    assert result == []

    # list containing a non-dict is filtered out
    result = _methods_from_doc(["not-a-dict", m1])
    assert len(result) == 1
    assert result[0]["name"] == "eth_a"

    # list containing a dict without 'name' is filtered out
    result = _methods_from_doc([{"summary": "no name here"}, m1])
    assert len(result) == 1
    assert result[0]["name"] == "eth_a"


# ---------------------------------------------------------------------------
# 4. reindex_openrpc: first run adds, second run after file removal deletes
# ---------------------------------------------------------------------------

def test_reindex_openrpc_first_run_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path / "data"))
    repo = _make_repo(tmp_path, "execution-apis")

    eth_dir = repo / "src" / "eth"
    eth_dir.mkdir(parents=True)

    methods = [
        {
            "name": "eth_getBlockByHash",
            "summary": "Returns a block matching EIP-4844 blob commitments.",
            "params": [
                {"name": "blockHash", "required": True, "schema": {"type": "string"}},
            ],
            "result": {"name": "block", "schema": {"type": "object"}},
        },
        {
            "name": "eth_getBlockByNumber",
            "summary": "Returns a block by number.",
            "params": [
                {"name": "blockNumber", "required": True, "schema": {"type": "string"}},
            ],
            "result": {"name": "block", "schema": {"type": "object"}},
        },
    ]
    (eth_dir / "block.yaml").write_text(yaml.dump(methods))
    _commit_all(repo, "add block.yaml")

    monkeypatch.setattr("eipmcp.repos.ensure_clone", lambda spec: repo)
    spec = RepoSpec(key="execution-apis", url="x", openrpc_dirs=("src/eth",))

    out = reindex_openrpc(spec)
    assert out["upserted"] == 2
    assert set(out["added"]) == {
        "src/eth/block.yaml#eth_getBlockByHash",
        "src/eth/block.yaml#eth_getBlockByNumber",
    }
    assert out["deleted"] == 0

    # Cross-refs for the EIP-4844 mention
    db = tmp_path / "data" / "eipmcp.db"
    with storage.connect(db) as conn:
        refs = storage.refs_in_source(conn, "execution-apis", "src/eth/block.yaml#eth_getBlockByHash")
        assert 4844 in refs

    # Rewrite with only one method, re-run; the removed one should be deleted
    (eth_dir / "block.yaml").write_text(yaml.dump([methods[0]]))
    _commit_all(repo, "remove second method")

    out2 = reindex_openrpc(spec)
    assert out2["deleted"] == 1

    with storage.connect(db) as conn:
        listed_paths = [r["path"] for r in storage.list_specs(conn, "execution-apis")]
    assert "src/eth/block.yaml#eth_getBlockByNumber" not in listed_paths
    assert "src/eth/block.yaml#eth_getBlockByHash" in listed_paths


# ---------------------------------------------------------------------------
# 5. search_specs_fts finds indexed methods
# ---------------------------------------------------------------------------

def test_search_specs_finds_method(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path / "data"))
    repo = _make_repo(tmp_path, "execution-apis")

    eth_dir = repo / "src" / "eth"
    eth_dir.mkdir(parents=True)

    methods = [
        {
            "name": "eth_getBlockByHash",
            "summary": "Returns information about a block selected by hash.",
            "params": [
                {"name": "blockHash", "required": True, "schema": {"type": "string"}},
            ],
            "result": {"name": "block", "schema": {"type": "object"}},
        },
        {
            "name": "eth_syncing",
            "summary": "Returns sync status.",
            "params": [],
            "result": {"name": "status", "schema": {"type": "object"}},
        },
    ]
    (eth_dir / "block.yaml").write_text(yaml.dump(methods))
    _commit_all(repo, "add methods")

    monkeypatch.setattr("eipmcp.repos.ensure_clone", lambda spec: repo)
    spec = RepoSpec(key="execution-apis", url="x", openrpc_dirs=("src/eth",))
    reindex_openrpc(spec)

    db = tmp_path / "data" / "eipmcp.db"
    with storage.connect(db) as conn:
        hits = storage.search_specs_fts(conn, "eth_getBlockByHash", repo="execution-apis")

    assert hits, "expected at least one FTS hit"
    paths = [h["path"] for h in hits]
    assert any("#eth_getBlockByHash" in p for p in paths)


# ---------------------------------------------------------------------------
# 6. Prose and OpenRPC rows coexist; neither indexer deletes the other's rows
# ---------------------------------------------------------------------------

def test_openrpc_and_prose_coexist(tmp_path, monkeypatch):
    monkeypatch.setenv("EIPMCP_DATA_DIR", str(tmp_path / "data"))
    repo = _make_repo(tmp_path, "execution-apis")

    # Prose file indexed by reindex_specs
    engine_dir = repo / "src" / "engine"
    engine_dir.mkdir(parents=True)
    (engine_dir / "foo.md").write_text("# Engine API\n\nSome prose about the engine API.\n")

    # OpenRPC YAML indexed by reindex_openrpc
    eth_dir = repo / "src" / "eth"
    eth_dir.mkdir(parents=True)
    methods = [
        {
            "name": "eth_blockNumber",
            "summary": "Returns the latest block number.",
            "params": [],
            "result": {"name": "blockNumber", "schema": {"type": "string"}},
        },
    ]
    (eth_dir / "block.yaml").write_text(yaml.dump(methods))
    _commit_all(repo, "init")

    monkeypatch.setattr("eipmcp.repos.ensure_clone", lambda spec: repo)
    spec = RepoSpec(
        key="execution-apis",
        url="x",
        spec_dirs=("src/engine",),
        openrpc_dirs=("src/eth",),
    )

    db = tmp_path / "data" / "eipmcp.db"

    def _assert_both_present(conn_path: Path) -> None:
        with storage.connect(conn_path) as conn:
            listed = {r["path"] for r in storage.list_specs(conn, "execution-apis")}
        assert "src/engine/foo.md" in listed, f"prose path missing; got: {listed}"
        assert any("#eth_blockNumber" in p for p in listed), f"synthetic path missing; got: {listed}"

    # First run: both indexers
    specs.reindex_specs(spec)
    reindex_openrpc(spec)
    _assert_both_present(db)

    # Second run: both indexers again; prove repeated syncs don't wipe either set
    specs.reindex_specs(spec)
    reindex_openrpc(spec)
    _assert_both_present(db)
