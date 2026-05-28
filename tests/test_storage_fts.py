from eipmcp import storage


def _mk(num, title, desc, body):
    return {
        "repo": "eips", "number": num, "title": title, "description": desc,
        "status": "Final", "type": "Standards Track", "category": "Core",
        "author": "A", "created": "2020", "requires": [], "discussions": None,
        "file_path": f"EIPS/eip-{num}.md", "body": body,
        "content_sha": f"{num:064d}",
    }


def test_fts_search_ranks_and_snippets(tmp_path):
    db = tmp_path / "fts.db"
    with storage.connect(db) as conn:
        storage.upsert_eip(conn, _mk(1559, "Fee market change", "Replace gas auction",
                                     "Introduces base fee and burning."))
        storage.upsert_eip(conn, _mk(4844, "Shard blob transactions", "Blobs for rollups",
                                     "Adds blob-carrying transactions."))
        storage.upsert_eip(conn, _mk(7702, "Set EOA account code", "EOA delegation",
                                     "Lets an EOA temporarily act as a contract."))

        hits = storage.search_eips(conn, "blob")
        assert [h["number"] for h in hits][:1] == [4844]
        assert "snippet" in hits[0]
        assert hits[0]["snippet"] is not None

        # Multi-token query AND-joins:
        hits = storage.search_eips(conn, "base fee")
        assert any(h["number"] == 1559 for h in hits)


def test_fts_handles_special_chars(tmp_path):
    db = tmp_path / "fts.db"
    with storage.connect(db) as conn:
        storage.upsert_eip(conn, _mk(1, "Test", None, "alpha beta"))
        # Unbalanced quote / FTS operator chars must not crash.
        assert storage.search_eips(conn, 'alpha"') is not None
        assert storage.search_eips(conn, "alpha OR beta") is not None


def test_search_includes_description(tmp_path):
    db = tmp_path / "fts.db"
    with storage.connect(db) as conn:
        storage.upsert_eip(conn, _mk(42, "X", "uniquedescriptiontoken", "body has nothing"))
        hits = storage.search_eips(conn, "uniquedescriptiontoken")
        assert hits and hits[0]["number"] == 42


def test_refs_helpers(tmp_path):
    db = tmp_path / "r.db"
    with storage.connect(db) as conn:
        storage.replace_refs(conn, "consensus-specs", "specs/electra/beacon-chain.md",
                              [7251, 7002, 6110])
        storage.replace_refs(conn, "execution-spec-tests",
                              "tests/prague/eip7702_set_code_tx/test_x.py", [7702])
        assert storage.refs_in_source(conn, "consensus-specs",
                                       "specs/electra/beacon-chain.md") == [6110, 7002, 7251]
        rows = storage.refs_for_eip(conn, 7702)
        assert rows == [{"source_repo": "execution-spec-tests",
                         "source_path": "tests/prague/eip7702_set_code_tx/test_x.py"}]


def test_migration_adds_description(tmp_path):
    # Build an "old" DB without the description column, then re-open.
    db = tmp_path / "m.db"
    import sqlite3
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE eips (
            repo TEXT, number INTEGER, title TEXT, status TEXT, type TEXT,
            category TEXT, author TEXT, created TEXT, requires TEXT, discussions TEXT,
            file_path TEXT, body TEXT, content_sha TEXT,
            PRIMARY KEY (repo, number)
        );
        """
    )
    conn.commit(); conn.close()

    with storage.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(eips)").fetchall()}
        assert "description" in cols
