"""Verify FTS tables are backfilled when added to a DB that already has data."""

import sqlite3

from eipmcp import storage


def test_specs_fts_backfill_on_connect(tmp_path):
    db = tmp_path / "old.db"
    # Build a DB with the specs table populated but NO specs_fts table.
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE specs (
            repo TEXT NOT NULL, path TEXT NOT NULL,
            body TEXT NOT NULL, content_sha TEXT NOT NULL,
            PRIMARY KEY (repo, path)
        );
        CREATE TABLE eips (
            repo TEXT, number INTEGER, title TEXT, status TEXT, type TEXT,
            category TEXT, author TEXT, created TEXT, requires TEXT,
            discussions TEXT, file_path TEXT, body TEXT, content_sha TEXT,
            PRIMARY KEY (repo, number)
        );
        """
    )
    conn.execute(
        "INSERT INTO specs VALUES (?, ?, ?, ?)",
        ("consensus-specs", "specs/electra/beacon-chain.md",
         "RANDAO is mixed into the state.", "sha1"),
    )
    conn.commit(); conn.close()

    # First connect through storage.connect should create specs_fts and backfill.
    with storage.connect(db) as conn:
        hits = storage.search_specs_fts(conn, "RANDAO")
    assert hits and hits[0]["path"] == "specs/electra/beacon-chain.md"


def test_eips_fts_backfill_on_connect(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE eips (
            repo TEXT, number INTEGER, title TEXT, description TEXT, status TEXT,
            type TEXT, category TEXT, author TEXT, created TEXT, requires TEXT,
            discussions TEXT, file_path TEXT, body TEXT, content_sha TEXT,
            PRIMARY KEY (repo, number)
        );
        CREATE TABLE specs (
            repo TEXT, path TEXT, body TEXT, content_sha TEXT,
            PRIMARY KEY (repo, path)
        );
        """
    )
    conn.execute(
        "INSERT INTO eips (repo, number, title, description, body, content_sha, file_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("eips", 4844, "Shard Blob Transactions", "Blob desc",
         "Introduce blob-carrying transactions.", "x" * 64, "EIPS/eip-4844.md"),
    )
    conn.commit(); conn.close()

    with storage.connect(db) as conn:
        hits = storage.search_eips(conn, "blob")
    assert hits and hits[0]["number"] == 4844
