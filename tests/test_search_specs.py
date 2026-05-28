from eipmcp import storage


def test_specs_fts_basic(tmp_path):
    db = tmp_path / "s.db"
    with storage.connect(db) as conn:
        storage.upsert_spec(
            conn, "consensus-specs", "specs/electra/beacon-chain.md",
            "RANDAO reveal is mixed into the state via mix_in_randao.", "sha1",
        )
        storage.upsert_spec(
            conn, "execution-specs", "src/ethereum/prague/transactions.py",
            "blob_versioned_hashes contain KZG commitments to blobs.", "sha2",
        )
        hits = storage.search_specs_fts(conn, "RANDAO")
        assert hits
        assert "beacon-chain.md" in hits[0]["path"]
        assert hits[0]["snippet"] and "RANDAO" in hits[0]["snippet"].upper().replace("«","").replace("»","")


def test_specs_fts_repo_filter(tmp_path):
    db = tmp_path / "s.db"
    with storage.connect(db) as conn:
        storage.upsert_spec(conn, "consensus-specs", "a.md", "blob blob blob", "1")
        storage.upsert_spec(conn, "execution-specs", "b.md", "blob blob blob", "2")
        only_cl = storage.search_specs_fts(conn, "blob", repo="consensus-specs")
        assert {h["repo"] for h in only_cl} == {"consensus-specs"}


def test_specs_fts_safe_against_operators(tmp_path):
    db = tmp_path / "s.db"
    with storage.connect(db) as conn:
        storage.upsert_spec(conn, "x", "a.md", "alpha beta", "sha")
        # FTS operator chars must not crash
        assert storage.search_specs_fts(conn, 'alpha"') is not None
        assert storage.search_specs_fts(conn, "alpha AND beta") is not None


def test_specs_fts_cleared_on_delete(tmp_path):
    db = tmp_path / "s.db"
    with storage.connect(db) as conn:
        storage.upsert_spec(conn, "x", "a.md", "uniquetoken", "sha")
        assert storage.search_specs_fts(conn, "uniquetoken")
        storage.delete_missing_specs(conn, "x", present=[])
        assert storage.search_specs_fts(conn, "uniquetoken") == []
